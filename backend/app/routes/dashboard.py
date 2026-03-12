"""
Dashboard Routes

Serves:
  GET /dashboard/          → the single-page dashboard HTML
  GET /dashboard/events    → SSE stream (positions, metrics, reasoning, agent activity)
  GET /dashboard/api/*     → REST endpoints polled on page load
  POST /dashboard/api/override/* → human override actions
"""
import asyncio
import json
import queue
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import numpy as np
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.position import Position, PositionStatus
from app.models.alert import Alert
from app.services import agent_tracker
from app.services.reasoning_log import recent as recent_reasoning
from app.services.auth import require_api_key, require_supabase_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_STATIC = Path(__file__).resolve().parents[1] / "static"


# ── SSE stream ────────────────────────────────────────────────────────────────

async def _event_generator(request: Request) -> AsyncGenerator[str, None]:
    """Fan-out SSE: each client gets its own queue via agent_tracker.subscribe()."""
    q = agent_tracker.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = q.get_nowait()
                yield f"data: {payload}\n\n"
            except queue.Empty:
                # heartbeat keeps the connection alive through proxies / load balancers
                yield 'data: {"type":"heartbeat"}\n\n'
                await asyncio.sleep(3)
    finally:
        agent_tracker.unsubscribe(q)


@router.get("/events")
async def event_stream(request: Request):
    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


# ── Dashboard page ────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def dashboard_page():
    html = _STATIC / "dashboard.html"
    if html.exists():
        return html.read_text()
    return "<h1>Dashboard not found — run the backend setup script.</h1>"


# ── REST: agents ──────────────────────────────────────────────────────────────

@router.get("/api/agents")
def get_agents():
    return agent_tracker.get_agents()


# ── REST: positions ───────────────────────────────────────────────────────────

@router.get("/api/positions")
def get_positions(db: Session = Depends(get_db)):
    positions = db.query(Position).filter(
        Position.status == PositionStatus.OPEN
    ).order_by(Position.opened_at.desc()).all()

    result = []
    for p in positions:
        pnl_pct = float(p.unrealized_pnl_pct or 0) * 100
        result.append({
            "id":              p.id,
            "symbol":          p.symbol,
            "qty":             p.qty,
            "entry":           round(float(p.avg_entry_price or 0), 4),
            "current":         round(float(p.current_price or 0), 4),
            "pnl_pct":         round(pnl_pct, 2),
            "pnl_usd":         round(float(p.unrealized_pnl or 0), 2),
            "stop":            round(float(p.stop_loss_price or 0), 4),
            "pyramid_level":   p.pyramid_level,
            "theme_id":        p.theme_id,
            "opened_at":       p.opened_at.isoformat() if p.opened_at else None,
        })
    return result


# ── REST: metrics ─────────────────────────────────────────────────────────────

@router.get("/api/metrics")
def get_metrics(db: Session = Depends(get_db)):
    from app.integrations.alpaca_client import AlpacaClient

    all_pos   = db.query(Position).all()
    open_pos  = [p for p in all_pos if p.status == PositionStatus.OPEN]
    closed    = [p for p in all_pos if p.status in (
        PositionStatus.CLOSED, PositionStatus.STOPPED_OUT
    )]

    # Per-trade P&L percentages
    pnl_pcts: list[float] = []
    for p in closed:
        if p.cost_basis and p.cost_basis > 0:
            pnl_pcts.append(float(p.realized_pnl or 0) / float(p.cost_basis) * 100)

    wins   = [x for x in pnl_pcts if x > 0]
    losses = [x for x in pnl_pcts if x <= 0]

    total   = len(pnl_pcts)
    win_rate = round(len(wins) / total * 100, 1) if total else 0
    avg_win  = round(float(np.mean(wins)),   2) if wins   else 0.0
    avg_loss = round(float(np.mean(losses)), 2) if losses else 0.0
    expectancy    = round((win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss), 2)
    gross_wins    = sum(wins)
    gross_losses  = abs(sum(losses)) or 1.0
    profit_factor = round(gross_wins / gross_losses, 2)

    # Sequential equity curve (5% risk per trade)
    try:
        _dash_acct = AlpacaClient().get_account()
        equity = float(_dash_acct.get("portfolio_value", 100_000))
    except Exception:
        equity = 100_000.0
    peak   = equity
    max_dd = 0.0
    equity_curve = [{"label": "Start", "value": equity}]
    for p in sorted(closed, key=lambda x: x.closed_at or datetime.min.replace(tzinfo=timezone.utc)):
        if p.cost_basis and p.cost_basis > 0:
            pct = float(p.realized_pnl or 0) / float(p.cost_basis)
            equity += equity * 0.05 * pct * 100 / 100
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd
        equity_curve.append({
            "label": p.closed_at.strftime("%m/%d") if p.closed_at else "?",
            "value": round(equity, 2),
        })

    try:
        account       = AlpacaClient().get_account()
        portfolio_val = account.get("portfolio_value")
        cash          = account.get("cash")
        daily_pnl     = account.get("daily_pnl")
    except Exception:
        portfolio_val = daily_pnl = cash = None

    # Yesterday and month P&L from closed positions in DB
    from datetime import date, timedelta
    today_date     = datetime.now(timezone.utc).date()
    yesterday_date = today_date - timedelta(days=1)
    month_start    = today_date.replace(day=1)

    def _close_date(p) -> date | None:
        if not p.closed_at:
            return None
        if p.closed_at.tzinfo is None:
            return p.closed_at.date()
        return p.closed_at.astimezone(timezone.utc).date()

    yesterday_pnl = round(sum(
        float(p.realized_pnl or 0)
        for p in closed if _close_date(p) == yesterday_date
    ), 2)

    month_pnl = round(sum(
        float(p.realized_pnl or 0)
        for p in closed if (_close_date(p) or date.min) >= month_start
    ), 2)

    return {
        "total_closed":    total,
        "open_positions":  len(open_pos),
        "win_rate":        win_rate,
        "wins":            len(wins),
        "losses":          len(losses),
        "avg_win":         avg_win,
        "avg_loss":        avg_loss,
        "expectancy":      expectancy,
        "profit_factor":   profit_factor,
        "max_drawdown":    round(max_dd, 1),
        "portfolio_value": portfolio_val,
        "daily_pnl":       daily_pnl,
        "yesterday_pnl":   yesterday_pnl,
        "month_pnl":       month_pnl,
        "cash":            cash,
        "equity_curve":    equity_curve,
    }


# ── REST: go/no-go ────────────────────────────────────────────────────────────

@router.get("/api/go-no-go")
def get_go_no_go(db: Session = Depends(get_db)):
    """Evaluate pre-flight criteria for flipping from paper to live money."""
    from app.services.go_no_go import evaluate
    from dataclasses import asdict
    report = evaluate(db)
    return {
        "verdict":      report.verdict,
        "blockers":     report.blockers,
        "evaluated_at": report.evaluated_at,
        "criteria": [
            {
                "id":        c.id,
                "label":     c.label,
                "category":  c.category,
                "threshold": c.threshold,
                "actual":    c.actual,
                "passed":    c.passed,
                "blocker":   c.blocker,
                "note":      c.note,
            }
            for c in report.criteria
        ],
    }


# ── REST: reasoning log ───────────────────────────────────────────────────────

@router.get("/api/reasoning")
def get_reasoning(limit: int = 50):
    return recent_reasoning(limit)


# ── REST: alerts ──────────────────────────────────────────────────────────────

@router.get("/api/alerts")
def get_alerts(limit: int = 30, db: Session = Depends(get_db)):
    alerts = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":          a.id,
            "type":        a.alert_type,
            "symbol":      a.symbol,
            "title":       a.title,
            "message":     a.message,
            "severity":    a.severity,
            "acknowledged": a.acknowledged,
            "created_at":  a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


# ── Override commands ─────────────────────────────────────────────────────────

@router.post("/api/override/close/{symbol}")
def close_position(symbol: str, db: Session = Depends(get_db), _auth=Depends(require_api_key)):
    """Emergency close a single position."""
    from app.integrations.alpaca_client import AlpacaClient
    from app.services.audit_log import write_pretrade

    pos = db.query(Position).filter(
        Position.symbol == symbol.upper(),
        Position.status == PositionStatus.OPEN,
    ).first()
    if not pos:
        return {"error": f"No open position for {symbol}"}

    write_pretrade(
        event="manual_override",
        symbol=pos.symbol,
        side="sell",
        qty=pos.qty,
        price=float(pos.current_price or 0),
        paper=True,
        extra={"source": "dashboard_override"},
    )
    try:
        AlpacaClient().close_position(pos.symbol)
        pos.status    = PositionStatus.CLOSED
        pos.closed_at = datetime.now(timezone.utc)
        db.commit()
        agent_tracker.reasoning(
            symbol=pos.symbol, agent="dashboard",
            corners={}, conviction=0,
            action="manual_close",
            notes="Closed via dashboard override",
        )
        return {"status": "ok", "symbol": pos.symbol}
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/override/stop-all")
def stop_all(db: Session = Depends(get_db), _auth=Depends(require_api_key)):
    """Emergency close all open positions and pause the engine."""
    from app.integrations.alpaca_client import AlpacaClient
    from app.services import kill_switch

    kill_switch.pause(reason="Dashboard STOP ALL")

    positions = db.query(Position).filter(Position.status == PositionStatus.OPEN).all()
    results = []
    client = AlpacaClient()
    for pos in positions:
        try:
            client.close_position(pos.symbol)
            pos.status    = PositionStatus.CLOSED
            pos.closed_at = datetime.now(timezone.utc)
            results.append({"symbol": pos.symbol, "status": "closed"})
        except Exception as e:
            results.append({"symbol": pos.symbol, "status": "error", "error": str(e)})
    db.commit()
    return {"closed": results, "engine_paused": True}


@router.post("/api/override/resume")
def resume_engine(_auth=Depends(require_api_key)):
    """Re-enable new entries after a STOP ALL / PAUSE."""
    from app.services import kill_switch
    kill_switch.resume()
    return {"engine_paused": False}


@router.get("/api/kill-switch")
def get_kill_switch():
    """Current kill switch state."""
    from app.services import kill_switch
    return kill_switch.status()


# ── REST: ticker tape ─────────────────────────────────────────────────────────

_TAPE_INDICES = ["SPY", "QQQ", "IWM", "DIA"]

@router.get("/api/ticker-tape")
def get_ticker_tape(db: Session = Depends(get_db)):
    """
    Return major indices + top watchlist tickers for the live ticker strip.
    Major indices always come first; then up-to-8 active watchlist symbols
    ranked by near_breakout status then rank_score.
    """
    from app.integrations.alpaca_client import AlpacaClient
    from app.models.watchlist import WatchlistItem

    watchlist = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.active == True)
        .order_by(
            WatchlistItem.near_breakout.desc(),
            WatchlistItem.rank_score.desc(),
        )
        .limit(10)
        .all()
    )
    watch_syms = [w.symbol for w in watchlist if w.symbol not in _TAPE_INDICES][:8]
    all_symbols = _TAPE_INDICES + watch_syms

    try:
        snaps = AlpacaClient().get_snapshots_batch(all_symbols)
        return [
            {**snaps[sym], "is_index": sym in _TAPE_INDICES}
            for sym in all_symbols
            if sym in snaps and (snaps[sym]["price"] > 0 or snaps[sym]["prev_close"] > 0)
        ]
    except Exception as e:
        logger.warning(f"Ticker tape fetch failed: {e}")
        return []


# ── REST: scanner state (DB-backed, no dependency on today's log file) ────────

@router.get("/api/scanner")
def get_scanner(db: Session = Depends(get_db)):
    """
    Live scanner state read directly from the DB.

    Returns all structure-clean watchlist items, sorted by near_breakout status
    then conviction. This endpoint always has data regardless of whether a scan
    has run today — it reflects the last saved state from any previous scan.

    The dashboard scanner feed uses this on page load, then updates via SSE
    when new scan events are broadcast.
    """
    from app.models.watchlist import WatchlistItem

    items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.active == True, WatchlistItem.structure_clean == True)
        .order_by(WatchlistItem.near_breakout.desc(), WatchlistItem.rank_score.desc())
        .limit(50)
        .all()
    )
    result = []
    for item in items:
        chart     = bool(item.near_breakout)
        structure = bool(item.structure_clean)
        sector    = item.theme is not None
        catalyst  = bool(item.catalyst_type)
        conviction = sum([chart, structure, sector, catalyst])
        vol_ratio  = round(float(item.volume_ratio or 0), 1)
        resistance = round(float(item.breakout_level or 0), 2)
        theme_name = item.theme.name if item.theme else "—"
        notes = (
            f"Vol {vol_ratio}× avg"
            + (f" | Resistance ${resistance}" if resistance else "")
            + f" | Theme: {theme_name}"
            + (f" | Catalyst: {item.catalyst_type}" if item.catalyst_type else "")
        )
        result.append({
            "symbol":        item.symbol,
            "agent":         "breakout_scanner",
            "action":        "entry" if item.near_breakout else "hold",
            "corners":       {"chart": chart, "structure": structure, "sector": sector, "catalyst": catalyst},
            "conviction":    conviction,
            "price":         round(float(item.price or 0), 4),
            "volume_ratio":  vol_ratio,
            "breakout_level": resistance,
            "notes":         notes,
            "theme":         theme_name,
            "ts":            item.updated_at.isoformat() if item.updated_at else None,
        })
    return result


# ── REST: pipeline view (all watchlist items with stage tags) ──────────────────

@router.get("/api/pipeline")
def get_pipeline(db: Session = Depends(get_db)):
    """
    Full pipeline view: every active watchlist item with its stage label.

    Stage progression:
      watching   → on watchlist, not yet structure-checked
      structured → passed structure check (clean float, volume, price)
      candidate  → structure clean + near_breakout flagged
      triggered  → near_breakout AND conviction >= 2 (ready to trade)
    """
    from app.models.watchlist import WatchlistItem

    items = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.active == True)
        .order_by(WatchlistItem.near_breakout.desc(), WatchlistItem.structure_clean.desc(),
                  WatchlistItem.rank_score.desc())
        .all()
    )
    result = []
    for item in items:
        chart     = bool(item.near_breakout)
        structure = bool(item.structure_clean)
        sector    = item.theme is not None
        catalyst  = bool(item.catalyst_type)
        conviction = sum([chart, structure, sector, catalyst])

        if chart and conviction >= 2:
            stage = "triggered"
        elif chart:
            stage = "candidate"
        elif structure:
            stage = "structured"
        else:
            stage = "watching"

        result.append({
            "symbol":        item.symbol,
            "company_name":  item.company_name or "",
            "theme":         item.theme.name if item.theme else "—",
            "price":         round(float(item.price or 0), 4),
            "breakout_level": round(float(item.breakout_level or 0), 4),
            "volume_ratio":  round(float(item.volume_ratio or 0), 2),
            "conviction":    conviction,
            "stage":         stage,
            "structure_clean": structure,
            "near_breakout": chart,
            "catalyst_type": item.catalyst_type,
            "updated_at":    item.updated_at.isoformat() if item.updated_at else None,
            "corners":       {"chart": chart, "structure": structure,
                              "sector": sector, "catalyst": catalyst},
        })
    return result


# ── REST: pre-market queue ────────────────────────────────────────────────────

@router.get("/api/queue")
def get_queue(db: Session = Depends(get_db)):
    """
    Pre-market candidate queue: watchlist items that have a confirmed trendline
    breakout signal (near_breakout=True) and are waiting for market open.

    Corners are reconstructed from the DB state that the breakout scanner wrote:
      chart     = near_breakout (scanner only sets this True when trendline broke)
      structure = structure_clean
      sector    = theme attached
      catalyst  = catalyst_type set (scanner persists "news" when Finnhub hit)
    """
    from app.models.watchlist import WatchlistItem

    items = (
        db.query(WatchlistItem)
        .filter(
            WatchlistItem.active == True,
            WatchlistItem.near_breakout == True,
        )
        .order_by(WatchlistItem.rank_score.desc(), WatchlistItem.updated_at.desc())
        .limit(30)
        .all()
    )

    result = []
    for item in items:
        chart     = bool(item.near_breakout)
        structure = bool(item.structure_clean)
        sector    = item.theme is not None
        catalyst  = bool(item.catalyst_type)
        conviction = sum([chart, structure, sector, catalyst])
        result.append({
            "symbol":          item.symbol,
            "company_name":    item.company_name or "",
            "price":           round(float(item.price or 0), 4),
            "breakout_level":  round(float(item.breakout_level or 0), 4),
            "volume_ratio":    round(float(item.volume_ratio or 0), 2),
            "conviction":      conviction,
            "corners": {
                "chart":     chart,
                "structure": structure,
                "sector":    sector,
                "catalyst":  catalyst,
            },
            "theme":           item.theme.name if item.theme else None,
            "catalyst_type":   item.catalyst_type,
            "catalyst_notes":  item.catalyst_notes,
            "updated_at":      item.updated_at.isoformat() if item.updated_at else None,
        })
    return result


# ── REST: news feed (ThemeSource articles with URLs) ─────────────────────────

@router.get("/api/news")
def get_news(limit: int = 40, db: Session = Depends(get_db)):
    """
    Recent news articles that influenced theme scores.
    Only returns records that have both a headline and a URL so the dashboard
    can show clickable headlines.
    """
    from app.models.theme import ThemeSource, Theme
    sources = (
        db.query(ThemeSource)
        .filter(
            ThemeSource.headline.isnot(None),
            ThemeSource.url.isnot(None),
        )
        .order_by(ThemeSource.created_at.desc())
        .limit(limit)
        .all()
    )
    # Batch-load themes to avoid N+1 queries
    theme_ids = {s.theme_id for s in sources if s.theme_id}
    theme_map  = {}
    if theme_ids:
        themes = db.query(Theme).filter(Theme.id.in_(theme_ids)).all()
        theme_map = {t.id: t.name for t in themes}

    return [
        {
            "id":         s.id,
            "headline":   s.headline,
            "url":        s.url,
            "source":     s.source_name,
            "sentiment":  round(float(s.sentiment or 0), 3),
            "theme":      theme_map.get(s.theme_id),
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sources
    ]


# ── REST: themes ──────────────────────────────────────────────────────────────

@router.get("/api/themes")
def get_themes(db: Session = Depends(get_db)):
    """Active themes with scores for the theme heatmap."""
    from app.models.theme import Theme, ThemeStatus
    themes = (
        db.query(Theme)
        .order_by(Theme.score.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id":          t.id,
            "name":        t.name,
            "score":       round(float(t.score or 0), 3),
            "news_score":  round(float(t.news_score  or 0), 3),
            "social_score":round(float(t.social_score or 0), 3),
            "etf_score":   round(float(t.etf_score   or 0), 3),
            "status":      (t.status.value if hasattr(t.status, "value") else t.status) or "cooling",
            "updated_at":  t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in themes
    ]


# ── REST: account (proxied to /api/account for dashboard) ─────────────────────

@router.get("/api/account")
def get_dashboard_account(_token=Depends(require_supabase_token)):
    """Alpaca account data — dashboard calls /dashboard/api/account, backend serves it here."""
    from app.integrations.alpaca_client import AlpacaClient
    return AlpacaClient().get_account()
