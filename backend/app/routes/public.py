"""
Public Routes — no authentication required.

GET /api/public/stats         → aggregate performance stats for the public homepage
GET /api/public/equity-curve  → daily cumulative realized PnL % curve
GET /api/public/summary       → LLM-generated daily performance summary (cached 15 min)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
import logging

from app.database import get_db
from app.models.position import Position, PositionStatus
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public"])

# ---------------------------------------------------------------------------
# Module-level summary cache
# ---------------------------------------------------------------------------
_summary_cache: dict = {
    "summary": None,
    "generated_at": None,
    "cached": False,
}
_SUMMARY_TTL_SECONDS = 15 * 60  # 15 minutes


# ---------------------------------------------------------------------------
# GET /api/public/stats
# ---------------------------------------------------------------------------
@router.get("/stats")
def get_public_stats(db: Session = Depends(get_db)):
    """Aggregate performance stats — safe to expose publicly."""
    settings = get_settings()

    all_pos = db.query(Position).all()
    open_pos = [p for p in all_pos if p.status == PositionStatus.OPEN]
    closed = [p for p in all_pos if p.status in (
        PositionStatus.CLOSED, PositionStatus.STOPPED_OUT
    )]

    # Win rate
    pnl_pcts: list[float] = []
    for p in closed:
        if p.cost_basis and float(p.cost_basis) > 0:
            pnl_pcts.append(float(p.realized_pnl or 0) / float(p.cost_basis) * 100)

    total = len(pnl_pcts)
    wins = [x for x in pnl_pcts if x > 0]
    win_rate = round(len(wins) / total * 100, 1) if total else 0.0

    # Average hold days
    hold_days: list[float] = []
    for p in closed:
        if p.opened_at and p.closed_at:
            opened = p.opened_at if p.opened_at.tzinfo else p.opened_at.replace(tzinfo=timezone.utc)
            closed_at = p.closed_at if p.closed_at.tzinfo else p.closed_at.replace(tzinfo=timezone.utc)
            hold_days.append((closed_at - opened).total_seconds() / 86400)
    avg_hold = round(sum(hold_days) / len(hold_days), 1) if hold_days else 0.0

    # Total realized P&L as a percentage of total cost basis
    total_pnl = sum(float(p.realized_pnl or 0) for p in closed)
    total_cost = sum(float(p.cost_basis or 0) for p in closed if p.cost_basis)
    total_pnl_pct = round(total_pnl / total_cost * 100, 1) if total_cost > 0 else 0.0

    # System status: check kill switch
    from app.services import kill_switch
    system_status = "paused" if kill_switch.is_paused() else "running"

    # Current US/Eastern time
    eastern_now = datetime.now(ZoneInfo("America/New_York"))
    tz_abbr = eastern_now.strftime("%Z")  # "EST" or "EDT" automatically
    est_time = eastern_now.strftime(f"%-I:%M %p {tz_abbr}")

    return {
        "total_closed_trades": total,
        "win_rate_pct": win_rate,
        "avg_hold_days": avg_hold,
        "total_realized_pnl_pct": total_pnl_pct,
        "open_positions": len(open_pos),
        "system_status": system_status,
        "trading_mode": settings.trading_mode,
        "est_time": est_time,
    }


# ---------------------------------------------------------------------------
# GET /api/public/equity-curve
# ---------------------------------------------------------------------------
@router.get("/equity-curve")
def get_equity_curve(db: Session = Depends(get_db)):
    """Daily cumulative equity curve — Alpaca portfolio history (primary) or dollar-normalized fallback."""
    from datetime import date, timedelta
    from app.integrations.alpaca_client import AlpacaClient

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    # --- Primary: Alpaca portfolio history ---
    try:
        client = AlpacaClient()
        data_points = client.get_portfolio_history(days=60)
        if data_points:
            # Trim leading flat-zero days (pre-trading period — no activity yet)
            first_active = next(
                (i for i, p in enumerate(data_points) if p["equity_pct"] != 0.0),
                None,
            )
            if first_active is not None and first_active > 0:
                # Keep one zero anchor point so chart starts from 0%
                data_points = data_points[max(0, first_active - 1):]

            # Extend to today if the last point is in the past
            if data_points[-1]["date"] < today_str:
                data_points.append({
                    "date": today_str,
                    "equity_pct": data_points[-1]["equity_pct"],
                })
            return {
                "data_points": data_points,
                "last_updated": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "alpaca",
            }
    except Exception as e:
        logger.warning(f"Alpaca equity curve failed, using fallback: {e}")

    # --- Fallback: dollar-normalized from Position table ---
    # Try to get actual starting capital from Alpaca, fall back to $100k
    try:
        _acct = AlpacaClient().get_account()
        STARTING_CAPITAL = float(_acct.get("portfolio_value", 100_000))
    except Exception:
        STARTING_CAPITAL = 100_000.0
    all_pos = db.query(Position).all()

    daily_pnl_dollars: dict[str, float] = defaultdict(float)
    for p in all_pos:
        if p.status not in (PositionStatus.CLOSED, PositionStatus.STOPPED_OUT):
            continue
        date_field = p.closed_at if p.closed_at else p.opened_at
        if date_field is None:
            continue
        date_str_pos = date_field.strftime("%Y-%m-%d")
        daily_pnl_dollars[date_str_pos] += float(p.realized_pnl or 0)

    if not daily_pnl_dollars:
        return {
            "data_points": [],
            "last_updated": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "positions_empty",
        }

    sorted_dates = sorted(daily_pnl_dollars.keys())
    data_points_fb = []
    cumulative = 0.0
    for ds in sorted_dates:
        cumulative += daily_pnl_dollars[ds] / STARTING_CAPITAL * 100
        data_points_fb.append({"date": ds, "equity_pct": round(cumulative, 4)})

    # Carry forward to today
    if data_points_fb and data_points_fb[-1]["date"] < today_str:
        data_points_fb.append({
            "date": today_str,
            "equity_pct": data_points_fb[-1]["equity_pct"],
        })

    return {
        "data_points": data_points_fb,
        "last_updated": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "positions_normalized",
    }


# ---------------------------------------------------------------------------
# GET /api/public/summary
# ---------------------------------------------------------------------------
@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """LLM-generated daily performance summary, cached for 15 minutes."""
    now_utc = datetime.now(timezone.utc)

    # Return cached result if still fresh
    if (
        _summary_cache["summary"] is not None
        and _summary_cache["generated_at"] is not None
        and (now_utc - _summary_cache["generated_at"]).total_seconds() < _SUMMARY_TTL_SECONDS
    ):
        return {
            "summary": _summary_cache["summary"],
            "generated_at": _summary_cache["generated_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cached": True,
        }

    # --- Gather stats ---
    settings = get_settings()
    all_pos = db.query(Position).all()
    open_pos = [p for p in all_pos if p.status == PositionStatus.OPEN]
    closed = [p for p in all_pos if p.status in (
        PositionStatus.CLOSED, PositionStatus.STOPPED_OUT
    )]

    # Today's trades (closed today in UTC)
    today_str = now_utc.strftime("%Y-%m-%d")
    today_closed = [
        p for p in closed
        if p.closed_at and p.closed_at.strftime("%Y-%m-%d") == today_str
    ]

    # Today's realized PnL %
    today_pnl_pct = 0.0
    today_pnl_parts = []
    for p in today_closed:
        if p.cost_basis and float(p.cost_basis) > 0:
            pct = float(p.realized_pnl or 0) / float(p.cost_basis) * 100
            today_pnl_parts.append(pct)
    if today_pnl_parts:
        today_pnl_pct = sum(today_pnl_parts)

    # All-time win rate
    all_pnl_pcts = []
    for p in closed:
        if p.cost_basis and float(p.cost_basis) > 0:
            all_pnl_pcts.append(float(p.realized_pnl or 0) / float(p.cost_basis) * 100)
    total_trades = len(all_pnl_pcts)
    wins = [x for x in all_pnl_pcts if x > 0]
    win_rate = round(len(wins) / total_trades * 100, 1) if total_trades else 0.0

    n_trades_today = len(today_closed)
    m_open = len(open_pos)

    # Build fallback summary (no LLM)
    def _fallback_summary() -> str:
        direction = "positive" if today_pnl_pct >= 0 else "negative"
        return (
            f"Today: {n_trades_today} trade(s) closed, "
            f"{m_open} position(s) open. "
            f"Realized P&L: {today_pnl_pct:+.2f}% ({direction}). "
            f"All-time win rate: {win_rate}%. "
            f"System operating in {settings.trading_mode} mode."
        )

    summary_text: str

    # --- Attempt LLM call ---
    api_key = settings.anthropic_api_key
    if api_key:
        prompt = (
            f"Today's performance data:\n"
            f"- Trades today: {n_trades_today}\n"
            f"- Open positions: {m_open}\n"
            f"- Today's realized P&L: {today_pnl_pct:+.2f}%\n"
            f"- Win rate (all time): {win_rate}%\n"
            f"- System: {settings.trading_mode} trading, reinforcement learning validation, human oversight\n\n"
            f"Write a daily performance note."
        )
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                system=(
                    "You are a terse quantitative analyst writing a daily performance note "
                    "for a systematic equity trading strategy. Be precise, professional, and "
                    "brief — 2-3 sentences max. No emojis. No hype."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            summary_text = message.content[0].text
        except Exception as exc:
            logger.warning("Anthropic API call failed, using fallback summary: %s", exc)
            summary_text = _fallback_summary()
    else:
        summary_text = _fallback_summary()

    # Update cache
    _summary_cache["summary"] = summary_text
    _summary_cache["generated_at"] = now_utc
    _summary_cache["cached"] = False

    return {
        "summary": summary_text,
        "generated_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cached": False,
    }
