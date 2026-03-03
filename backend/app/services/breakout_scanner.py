"""
Breakout Scanner — Step 4 of Newman Strategy

Signal: trendline resistance break (peak detection over 252 bars)
Gate:   SPY bull regime (20-bar change > +2%)
Filter: conviction score ≥ 2 (chart + structure + sector + catalyst)

This replaces the previous 20-day high / linear regression approach,
which detected "went up lately" instead of "broke out of a year-long
decline" — a fundamentally different stock at a different lifecycle stage.

The detection logic is intentionally identical to the proven backtest
signal in backtest/backtest.py so live behaviour matches tested behaviour.
"""
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert
from app.integrations.alpaca_client import AlpacaClient
from app.services.reasoning_log import write_reasoning
from app.services import agent_tracker

logger = logging.getLogger(__name__)

# Bars lookback for trendline detection.
# 365 calendar days → ~252 trading-day bars, matching the backtest default.
_TRENDLINE_LOOKBACK  = 252
_VOL_AVG_BARS        = 20
# 550 calendar days ≈ 380 trading days — provides a safe margin above the
# 277-bar minimum (252 + 20 + 5).  The prior 400-day fetch returned exactly
# 274 bars for most symbols, causing every scan_single() call to fail the
# min_required check silently and skip all symbols.
_BREAKOUT_FETCH_DAYS = 550

# Catalyst corner: news headline keywords that signal a genuine event catalyst
_CATALYST_KEYWORDS = [
    'approval', 'approved', 'fda', 'contract', 'patent', 'breakthrough',
    'partnership', 'acquisition', 'deal', 'award', 'grant', 'legalization',
    'license', 'regulatory', 'clinical trial', 'phase 3', 'phase 2',
    'earnings beat', 'revenue beat', 'upgraded', 'buyout', 'merger',
    'government', 'ipo', 'listing', 'strategic',
]


# ── Signal functions (identical logic to backtest/backtest.py) ────────────────

def detect_resistance_break(bars: list[dict], lookback: int = 252) -> tuple[bool, float]:
    """
    Return (broke_out, resistance_level).

    Draws a trendline through the spike highs of the prior `lookback` bars
    (NOT including today's bar) and checks if today's close is >1% above it.

    This is Newman's actual entry signal: a stock that has been in a
    multi-year decline breaks above the resistance line formed by its
    previous spike highs, confirmed by volume.

    No look-ahead: the detection window is bars[-lookback-1:-1], which
    excludes today's bar (bars[-1]).
    """
    if len(bars) < lookback + 1:
        return False, 0.0

    window = bars[-lookback - 1:-1]          # strictly BEFORE today
    highs  = np.array([b["high"] for b in window])

    neighborhood = max(2, min(5, lookback // 10))
    peaks = [
        idx for idx in range(neighborhood, len(highs) - neighborhood)
        if highs[idx] == max(highs[idx - neighborhood: idx + neighborhood + 1])
    ]

    if len(peaks) < 2:
        return False, 0.0

    recent_peaks = peaks[-min(6, len(peaks)):]
    peak_x = np.array(recent_peaks, dtype=float)
    peak_y = highs[recent_peaks]

    slope, intercept = np.polyfit(peak_x, peak_y, 1)
    resistance = slope * len(window) + intercept

    today_close = bars[-1]["close"]
    broke_out   = today_close > resistance * 1.01   # 1% clearance
    return broke_out, max(resistance, 0.0)


def score_conviction(
    bars: list[dict],
    avg_vol_20: float,
    trendline_break: bool,
    vol_surge_multiplier: float = 2.5,
    bars_per_year: int = 252,
) -> tuple[int, dict]:
    """
    Return (score, corners_detail_dict).

    Corners (0–4):
      chart:     trendline resistance break confirmed
      structure: volume ≥ 2.5× 20-bar average (surge confirms the break)
      sector:    close within 20% of 1-year high (in active breakout territory)
      catalyst:  reserved — always False until catalyst feed is wired (Step 3)

    Returns both the integer score and the per-corner dict so the dashboard
    reasoning tab can display individual pass/fail dots.
    """
    i      = len(bars) - 1
    latest = bars[i]

    chart     = trendline_break
    structure = avg_vol_20 > 0 and latest["volume"] >= vol_surge_multiplier * avg_vol_20
    lookback_1y = max(0, i - bars_per_year)
    high_1y   = max(b["high"] for b in bars[lookback_1y: i + 1])
    sector    = high_1y > 0 and latest["close"] >= high_1y * 0.80
    # Catalyst corner starts False; caller (scan_single) upgrades it via
    # _check_catalyst() when a trendline break is detected — keeping this
    # function free of I/O so it remains fast and testable in isolation.
    catalyst = False

    # Coerce to plain Python bool so downstream json.dumps() (agent_tracker,
    # reasoning_log) never encounters numpy.bool_ serialization errors.
    corners = {
        "chart":     bool(chart),
        "structure": bool(structure),
        "sector":    bool(sector),
        "catalyst":  bool(catalyst),
    }
    return sum(corners.values()), corners


def spy_is_bull(spy_bars: list[dict], period: int = 20, threshold: float = 0.02) -> bool:
    """
    True if SPY's 20-bar change is > +2% (bull regime).
    Same gate used in the backtest to avoid fighting a declining market.
    """
    if len(spy_bars) < period + 1:
        return True   # not enough data — don't block
    closes = [b["close"] for b in spy_bars]
    change = (closes[-1] - closes[-period]) / closes[-period] if closes[-period] > 0 else 0
    return change > threshold


# ── Scanner class ─────────────────────────────────────────────────────────────

class BreakoutScanner:
    def __init__(self):
        self.alpaca   = AlpacaClient()
        self.settings = get_settings()
        self._min_corners = 2   # minimum conviction score to flag a breakout

    def _check_catalyst(self, symbol: str) -> bool:
        """
        Query Finnhub company news for the last 48 hours.
        Returns True if any headline/summary contains a catalyst keyword.
        Only called when a trendline break is already detected (limits API calls).
        """
        try:
            from app.integrations.finnhub_client import FinnhubClient
            today     = date.today()
            from_date = (today - timedelta(days=2)).isoformat()
            to_date   = today.isoformat()
            news = FinnhubClient().company_news(symbol, from_date, to_date)
            for article in news:
                text = (
                    article.get("headline", "") + " " + article.get("summary", "")
                ).lower()
                if any(kw in text for kw in _CATALYST_KEYWORDS):
                    logger.debug(
                        f"{symbol}: catalyst found — {article.get('headline', '')[:80]}"
                    )
                    return True
        except Exception as e:
            logger.debug(f"{symbol}: catalyst check skipped — {e}")
        return False

    def scan_all(self, db: Session) -> list[dict]:
        """Scan all clean watchlist items for trendline breakout signals."""
        items = db.query(WatchlistItem).filter(
            WatchlistItem.active == True,
            WatchlistItem.structure_clean == True,
        ).all()

        if not items:
            logger.info("Breakout scan: no clean watchlist items")
            return []

        # ── Deduplicate by symbol — keep highest rank_score row per symbol ────
        # After the M2M migration each symbol has one row, but guard against any
        # stale duplicates that may exist.  Without deduplication a duplicate
        # wastes one Alpaca bar fetch + one Claude step-4 call per scan cycle.
        seen: dict[str, WatchlistItem] = {}
        for item in items:
            if item.symbol not in seen or (item.rank_score or 0) > (seen[item.symbol].rank_score or 0):
                seen[item.symbol] = item
        items = list(seen.values())
        logger.info(f"Breakout scan: {len(items)} unique symbols after deduplication")

        # ── SPY regime gate ───────────────────────────────────────────────────
        bull = True
        try:
            spy_bars = self.alpaca.get_bars("SPY", days=60)
            bull     = spy_is_bull(spy_bars)
            regime   = "bull" if bull else "bear/neutral"
            logger.info(f"SPY regime: {regime}")
        except Exception as e:
            logger.warning(f"SPY fetch failed ({e}) — regime gate disabled")

        # ── Batch bar fetch (one API call for all symbols) ────────────────────
        symbols = [item.symbol for item in items]
        agent_tracker.spawn("breakout_scanner",
            f"Fetching {_BREAKOUT_FETCH_DAYS}d bars for {len(symbols)} symbols")
        logger.info(f"Breakout scan: fetching {_BREAKOUT_FETCH_DAYS} days for {len(symbols)} symbols…")
        try:
            bars_cache = self.alpaca.get_bars_batch(symbols, days=_BREAKOUT_FETCH_DAYS)
        except Exception as e:
            logger.error(f"Batch bar fetch failed: {e} — falling back to individual fetches")
            bars_cache = {}

        # ── Scan each symbol ──────────────────────────────────────────────────
        breakouts = []
        for idx, item in enumerate(items, 1):
            agent_tracker.update("breakout_scanner",
                f"Scanning {item.symbol} ({idx}/{len(items)})")
            try:
                result = self.scan_single(
                    item, db,
                    bars_cache=bars_cache.get(item.symbol),
                    spy_bull=bull,
                )
                if result and result.get("triggered"):
                    breakouts.append(result)
            except Exception as e:
                logger.warning(f"Breakout scan failed for {item.symbol}: {e}")

        db.commit()
        agent_tracker.complete("breakout_scanner",
            f"{len(breakouts)} signal(s) from {len(items)} stocks | regime={'bull' if bull else 'neutral/bear'}")
        logger.info(f"Breakout scan: {len(breakouts)} signals from {len(items)} stocks")
        return breakouts

    def scan_single(
        self,
        item: WatchlistItem,
        db: Session,
        bars_cache: list[dict] | None = None,
        spy_bull: bool = True,
    ) -> Optional[dict]:
        """
        Scan one stock for a Newman trendline resistance breakout.

        Entry requires ALL of:
          1. SPY in bull regime (20-bar change > +2%)
          2. Trendline break (today's close > resistance × 1.01)
          3. Conviction score ≥ 2 (chart + structure + sector corners)
        """
        bars = bars_cache if bars_cache is not None else \
               self.alpaca.get_bars(item.symbol, days=_BREAKOUT_FETCH_DAYS)

        min_required = _TRENDLINE_LOOKBACK + _VOL_AVG_BARS + 5
        if len(bars) < min_required:
            logger.debug(f"{item.symbol}: only {len(bars)} bars (need {min_required}) — skip")
            # Log the skip so the reasoning tab and scanner feed always show activity,
            # even when a symbol lacks sufficient bar history.
            write_reasoning(
                agent="breakout_scanner",
                event="scan",
                symbol=item.symbol,
                action="skip",
                corners={"chart": False, "structure": False, "sector": False, "catalyst": False},
                conviction=0,
                notes=f"Insufficient bar history: {len(bars)} bars available, {min_required} required for trendline detection.",
            )
            return None

        closes   = [b["close"] for b in bars]
        volumes  = [b["volume"] for b in bars]

        current_price  = closes[-1]
        avg_vol_20     = float(np.mean(volumes[-_VOL_AVG_BARS:]))
        current_vol    = volumes[-1]
        vol_ratio      = current_vol / avg_vol_20 if avg_vol_20 > 0 else 0

        # ── Core signal: trendline resistance break ───────────────────────────
        trendline_break, resistance = detect_resistance_break(
            bars, lookback=_TRENDLINE_LOOKBACK
        )

        # ── Conviction score ──────────────────────────────────────────────────
        conviction, corners = score_conviction(
            bars, avg_vol_20, trendline_break,
            vol_surge_multiplier=self.settings.volume_surge_multiplier,
        )

        # ── Catalyst corner — only query Finnhub when chart break detected ────
        # This keeps total API calls low: Finnhub is only hit for real candidates.
        # Persists catalyst_type="news" to the WatchlistItem so trade_executor
        # can read corners["catalyst"] from DB rather than hardcoding False.
        if trendline_break and not corners["catalyst"]:
            catalyst_hit = self._check_catalyst(item.symbol)
            if catalyst_hit:
                corners["catalyst"] = True
                conviction = sum(corners.values())
                item.catalyst_type  = "news"
                item.catalyst_notes = "Catalyst keyword found in Finnhub news (48h)"
            else:
                # Explicitly clear stale catalyst flag from a prior scan
                item.catalyst_type  = None
                item.catalyst_notes = None

        # ── Gate checks ───────────────────────────────────────────────────────
        regime_ok  = spy_bull
        signal_ok  = trendline_break and conviction >= self._min_corners
        triggered  = regime_ok and signal_ok

        # ── Build human-readable signal list for the alert message ────────────
        # Built before the Claude block so it can be passed as context.
        signals: list[str] = []
        if trendline_break:
            signals.append(
                f"Trendline break: ${current_price:.2f} > resistance ${resistance:.2f} "
                f"(+{(current_price / resistance - 1) * 100:.1f}% clearance)"
            )
        else:
            signals.append(f"No trendline break (resistance est. ${resistance:.2f})")

        if corners["structure"]:
            signals.append(f"Volume surge: {vol_ratio:.1f}× avg ({current_vol:,} vs {avg_vol_20:,.0f})")
        else:
            signals.append(f"Volume normal: {vol_ratio:.1f}× avg (need {self.settings.volume_surge_multiplier}×)")

        if corners["sector"]:
            signals.append("Near 1-year high — in active breakout territory")

        if corners["catalyst"]:
            signals.append("Catalyst: recent news event detected (Finnhub)")

        if not regime_ok:
            signals.append("SPY regime: neutral/bear — entry blocked")

        signals.append(f"Conviction: {conviction}/4")

        # ── Claude step-4 commentary — informational only, does not gate ─────────
        # Called when a trendline break is detected so the dashboard shows
        # Claude's view on every candidate, not just symbols that reach entry.
        # The binding Claude veto is at step 5 (trade_executor.shotgun_entry).
        claude_note = ""
        if trendline_break and conviction >= 1:
            try:
                from app.services.claude_gate import evaluate_trade as _cl_eval
                _cl = _cl_eval(
                    symbol=item.symbol,
                    corners=corners,
                    conviction=conviction,
                    theme=item.theme.name if item.theme else "",
                    price=float(current_price),
                    signals=signals,
                )
                decision = "GO" if _cl["approve"] else "NO-GO"
                claude_note = (
                    f"Claude ({_cl['confidence']}): {decision} — {_cl['reasoning']}"
                    + (f" | Risk: {_cl['risk_note']}" if _cl.get("risk_note") else "")
                )
                # Write a separate reasoning record so it appears as its own card
                write_reasoning(
                    agent="claude_gate",
                    event="step4_review",
                    symbol=item.symbol,
                    action="entry" if _cl["approve"] else "claude_veto",
                    corners=corners,
                    conviction=conviction,
                    notes=claude_note,
                )
            except Exception as _ce:
                logger.debug(f"Claude step-4 review skipped for {item.symbol}: {_ce}")

        # ── Update watchlist item ─────────────────────────────────────────────
        item.volume_ratio   = round(vol_ratio, 2)
        # near_breakout reflects the TECHNICAL signal only (trendline break + conviction).
        # The SPY regime gate is intentionally excluded here so the pre-market queue
        # shows genuine candidates even when the market is temporarily in a bear regime.
        # The regime gate is re-applied at execution time in trade_executor.shotgun_entry().
        item.near_breakout  = signal_ok
        item.breakout_level = round(resistance, 4)
        item.price          = current_price
        item.updated_at     = datetime.now(timezone.utc)

        # ── Reasoning log + dashboard broadcast ──────────────────────────────
        action = "entry" if triggered else ("skip" if not trendline_break else "hold")
        full_notes = " | ".join(signals)
        if claude_note:
            full_notes += f" || {claude_note}"
        write_reasoning(
            agent="breakout_scanner",
            event="scan",
            symbol=item.symbol,
            action=action,
            corners=corners,
            conviction=conviction,
            notes=full_notes,
        )

        # ── Create alert if breakout triggered ────────────────────────────────
        if triggered:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            existing = db.query(Alert).filter(
                Alert.symbol == item.symbol,
                Alert.alert_type == "breakout",
                Alert.created_at >= today_start,
            ).first()
            if not existing:
                alert = Alert(
                    alert_type="breakout",
                    symbol=item.symbol,
                    theme_name=item.theme.name if item.theme else None,
                    title=f"Trendline Break: {item.symbol} ({conviction}/4 conviction)",
                    message="\n".join(signals),
                    severity="action",
                )
                db.add(alert)
                db.commit()
                logger.info(f"BREAKOUT {item.symbol}: conviction {conviction}/4 | {'; '.join(signals[:2])}")

        return {
            "symbol":       item.symbol,
            "triggered":    triggered,
            "trendline_break": trendline_break,
            "resistance":   round(resistance, 4),
            "conviction":   conviction,
            "corners":      corners,
            "price":        current_price,
            "volume_ratio": round(vol_ratio, 2),
            "signals":      signals,
            "spy_bull":     spy_bull,
        }
