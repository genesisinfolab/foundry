"""
Golden Executor — Trade execution engine for Golden strategy.

Handles:
- Placing market orders for qualified Golden candidates
- Position sizing based on conviction tiers (high/medium/exploratory)
- Stop loss placement per Golden's wide thesis-driven risk parameters
- Duplicate position detection
- Max positions enforcement
- Full audit trail (reasoning_log, pretrade audit, WhatsApp notifications)

Follows the same patterns as Newman's TradeExecutor but with Golden-specific
position sizing, risk management, and entry logic.
"""
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.position import Position, PositionAction, PositionStatus
from app.models.alert import Alert
from app.integrations.alpaca_client import AlpacaClient
from app.strategies.golden import GoldenStrategy
from app.services.notifier import notify_entry
from app.services.audit_log import write_pretrade
from app.services.reasoning_log import write_reasoning
from app.services import agent_tracker

logger = logging.getLogger(__name__)

# Golden-specific limits
_MAX_GOLDEN_POSITIONS = 10  # max concurrent Golden positions


class GoldenExecutor:
    """
    Executes trades for Golden strategy qualified candidates.

    Takes scored candidates from GoldenScanner.run_scan() and places
    paper trades via Alpaca. Each candidate dict must have:
      - symbol: str
      - conviction_score: float (0.0-1.0)
      - tier: str (high/medium/exploratory)
      - price: float
      - breakdown: dict with scoring factors
      - checks: dict with pass/fail flags
    """

    def __init__(self):
        self.alpaca = AlpacaClient()
        self.strategy = GoldenStrategy()
        self.settings = get_settings()

    def execute_candidates(self, candidates: list[dict], db: Session) -> list[Position]:
        """
        Process a list of qualified candidates from the scanner.

        Returns list of Position objects for successfully opened positions.
        """
        if not candidates:
            logger.info("Golden Executor: no candidates to execute")
            return []

        # Kill switch check
        from app.services import kill_switch
        if kill_switch.is_paused():
            ks = kill_switch.status()
            logger.info(
                f"Golden Executor BLOCKED: engine paused — {ks.get('reason', 'manual override')}"
            )
            return []

        # Check how many Golden positions are already open
        open_golden = db.query(Position).filter(
            Position.status == PositionStatus.OPEN,
            Position.strategy == "golden",
        ).count()

        if open_golden >= _MAX_GOLDEN_POSITIONS:
            logger.info(
                f"Golden Executor: max positions reached ({open_golden}/{_MAX_GOLDEN_POSITIONS})"
            )
            return []

        slots_available = _MAX_GOLDEN_POSITIONS - open_golden

        # Get account info once
        try:
            account = self.alpaca.get_account()
        except Exception as e:
            logger.error(f"Golden Executor: failed to get account info: {e}")
            return []

        portfolio_value = account["portfolio_value"]
        available_cash = account["cash"]

        logger.info(
            f"Golden Executor: {len(candidates)} candidates | "
            f"{open_golden}/{_MAX_GOLDEN_POSITIONS} positions open | "
            f"${available_cash:,.0f} cash | ${portfolio_value:,.0f} portfolio"
        )

        opened = []
        for candidate in candidates[:slots_available]:
            try:
                position = self._execute_single(candidate, account, db)
                if position:
                    opened.append(position)
                    # Update available cash after each entry
                    available_cash -= position.cost_basis
                    account["cash"] = available_cash
            except Exception as e:
                logger.error(
                    f"Golden Executor: failed to execute {candidate['symbol']}: {e}",
                    exc_info=True,
                )

        if opened:
            logger.info(
                f"Golden Executor: opened {len(opened)} positions — "
                + ", ".join(f"{p.symbol}({p.qty}sh@${p.avg_entry_price:.2f})" for p in opened)
            )

        return opened

    def _execute_single(
        self,
        candidate: dict,
        account: dict,
        db: Session,
    ) -> Optional[Position]:
        """
        Execute a single Golden candidate entry.

        Returns Position if successful, None if skipped/failed.
        """
        symbol = candidate["symbol"]
        conviction_score = candidate["conviction_score"]
        tier = candidate["tier"]
        price = candidate["price"]
        breakdown = candidate.get("breakdown", {})

        agent_tracker.spawn("golden_executor", f"Evaluating: {symbol} ({tier}, {conviction_score:.3f})")

        # ── Duplicate check ──────────────────────────────────────────────────
        existing = db.query(Position).filter(
            Position.symbol == symbol,
            Position.status == PositionStatus.OPEN,
        ).first()
        if existing:
            logger.info(f"Golden: already have open position in {symbol} (strategy={getattr(existing, 'strategy', 'unknown')})")
            agent_tracker.complete("golden_executor", f"{symbol}: skipped — existing position")
            return None

        # ── Stopped-out cooldown (Golden: 72h) ──────────────────────────────
        risk = self.strategy.get_risk_parameters()
        cooldown_hours = risk.stopped_out_cooldown_hours
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)

        # Use a fresh session to avoid stale cache (same pattern as Newman)
        from app.database import SessionLocal as _SL
        _cddb = _SL()
        try:
            recent_stop = _cddb.query(Position).filter(
                Position.symbol == symbol,
                Position.status == PositionStatus.STOPPED_OUT,
                Position.closed_at >= cooldown_cutoff,
            ).first()
        finally:
            _cddb.close()

        if recent_stop:
            hours_ago = (datetime.now(timezone.utc) - recent_stop.closed_at).total_seconds() / 3600
            logger.info(
                f"Golden COOLDOWN: {symbol} stopped out {hours_ago:.1f}h ago — "
                f"blocked for {cooldown_hours}h"
            )
            write_reasoning(
                agent="golden_executor",
                event="cooldown_skip",
                symbol=symbol,
                action="skip",
                conviction=round(conviction_score * 4),
                notes=f"Stopped out {hours_ago:.1f}h ago, cooldown={cooldown_hours}h. Tier: {tier}",
            )
            agent_tracker.complete("golden_executor", f"{symbol}: cooldown — stopped out {hours_ago:.1f}h ago")
            return None

        # ── Position sizing ──────────────────────────────────────────────────
        portfolio_value = account["portfolio_value"]
        position_usd = self.strategy.position_size_usd(conviction_score, portfolio_value)

        if position_usd <= 0:
            logger.info(f"Golden: {symbol} conviction too low for entry (score={conviction_score:.3f}, tier={tier})")
            agent_tracker.complete("golden_executor", f"{symbol}: skipped — conviction too low")
            return None

        if account["cash"] < position_usd:
            logger.info(
                f"Golden: insufficient cash for {symbol} — need ${position_usd:.0f}, have ${account['cash']:.0f}"
            )
            write_reasoning(
                agent="golden_executor",
                event="insufficient_cash",
                symbol=symbol,
                action="skip",
                conviction=round(conviction_score * 4),
                notes=f"Need ${position_usd:.0f}, have ${account['cash']:.0f}. Tier: {tier}",
            )
            agent_tracker.complete("golden_executor", f"{symbol}: skipped — insufficient cash")
            return None

        # ── Price validation ─────────────────────────────────────────────────
        if not self.strategy.price_passes(price, conviction_score):
            logger.info(f"Golden: {symbol} price ${price:.2f} doesn't pass filter (conviction={conviction_score:.3f})")
            agent_tracker.complete("golden_executor", f"{symbol}: skipped — price filter")
            return None

        qty = int(position_usd / price)
        if qty < 1:
            logger.info(f"Golden: {symbol} qty < 1 at ${price:.2f} for ${position_usd:.0f}")
            agent_tracker.complete("golden_executor", f"{symbol}: skipped — qty < 1")
            return None

        # ── Stop loss calculation ────────────────────────────────────────────
        # Golden uses wide thesis-driven stops (-25%) as a floor,
        # but also respects ATR-based stops if available
        stop_loss_pct = risk.stop_loss_pct  # -0.25
        stop_price = price * (1 + stop_loss_pct)  # e.g., $10 * 0.75 = $7.50

        # Try ATR-based stop (tighter than 25% if ATR warrants it)
        atr = 0.0
        try:
            bars = self.alpaca.get_bars(symbol, days=20)
            if len(bars) >= 15:
                from app.services.risk_manager import calculate_atr
                atr = calculate_atr(bars)
                if atr > 0:
                    # Golden uses 3×ATR stop (wider than Newman's 1.5×ATR)
                    atr_stop = price - (3.0 * atr)
                    # Use ATR stop only if it's tighter than the thesis stop
                    stop_price = max(atr_stop, price * (1 + stop_loss_pct))
                    logger.info(
                        f"Golden ATR stop for {symbol}: ${stop_price:.2f} "
                        f"(ATR={atr:.2f}, 3×ATR=${3*atr:.2f}, floor=${price * (1 + stop_loss_pct):.2f})"
                    )
        except Exception as e:
            logger.warning(f"Golden ATR stop calculation failed for {symbol}: {e}")

        # ── Reasoning log (pre-trade) ────────────────────────────────────────
        write_reasoning(
            agent="golden_executor",
            event="golden_entry",
            symbol=symbol,
            action="entry",
            corners={
                "chart": False,  # Golden doesn't use chart breakouts
                "structure": breakdown.get("13f", 0) > 0,
                "sector": breakdown.get("sector", 0) > 0,
                "catalyst": breakdown.get("correction", 0) >= 0.4,
            },
            conviction=round(conviction_score * 4),
            notes=(
                f"Tier: {tier} | Score: {conviction_score:.3f} | "
                f"Size: ${position_usd:.0f} ({position_usd/portfolio_value:.1%} of portfolio) | "
                f"Qty: {qty} @ ${price:.2f} | Stop: ${stop_price:.2f} ({stop_loss_pct:.0%}) | "
                f"Cash: ${account['cash']:,.0f} | "
                f"Breakdown: {breakdown}"
            ),
        )

        # ── Pre-trade audit ──────────────────────────────────────────────────
        write_pretrade(
            event="golden_entry",
            symbol=symbol,
            side="buy",
            qty=qty,
            price=price,
            stop_price=stop_price,
            theme="golden",
            cash=account["cash"],
            portfolio_value=portfolio_value,
            paper=self.settings.alpaca_paper,
            checks=[
                "no_existing_position",
                "cooldown_clear",
                "sufficient_cash",
                "price_passes",
                "qty_ge_1",
                f"conviction_{tier}",
                "max_positions_clear",
            ],
            extra={
                "strategy": "golden",
                "conviction_score": round(conviction_score, 3),
                "tier": tier,
                "breakdown": breakdown,
            },
        )

        # ── Place order ──────────────────────────────────────────────────────
        try:
            order = self.alpaca.place_market_order(symbol, qty, "buy")
        except Exception as e:
            logger.error(f"Golden: order failed for {symbol}: {e}")
            write_reasoning(
                agent="golden_executor",
                event="order_failed",
                symbol=symbol,
                action="error",
                conviction=round(conviction_score * 4),
                notes=f"Order placement failed: {e}",
            )
            agent_tracker.complete("golden_executor", f"{symbol}: ORDER FAILED — {e}")
            return None

        # ── Get actual fill price ────────────────────────────────────────────
        fill_price = price
        try:
            time.sleep(1)  # brief wait for paper fill
            alpaca_positions = {p["symbol"]: p for p in self.alpaca.get_positions()}
            if symbol in alpaca_positions:
                fill_price = alpaca_positions[symbol]["avg_entry_price"]
                qty = int(alpaca_positions[symbol]["qty"])
                logger.info(
                    f"Golden: actual fill for {symbol}: ${fill_price:.3f} "
                    f"(scanner price was ${price:.3f})"
                )
        except Exception as e:
            logger.warning(f"Golden: could not fetch fill price for {symbol}: {e}")

        # Recalculate stop with actual fill price
        stop_price = fill_price * (1 + stop_loss_pct)
        if atr > 0:
            atr_stop = fill_price - (3.0 * atr)
            stop_price = max(atr_stop, fill_price * (1 + stop_loss_pct))

        # ── Record position in DB ────────────────────────────────────────────
        position = Position(
            symbol=symbol,
            theme_id=None,  # Golden doesn't use Newman's theme system
            status=PositionStatus.OPEN,
            side="buy",
            avg_entry_price=fill_price,
            current_price=fill_price,
            qty=qty,
            market_value=qty * fill_price,
            cost_basis=qty * fill_price,
            pyramid_level=0,
            stop_loss_price=stop_price,
            alpaca_order_id=order.get("order_id"),
            strategy="golden",
        )
        db.add(position)

        # Record action
        action = PositionAction(
            position=position,
            action_type="buy",
            qty=qty,
            price=fill_price,
            reason=(
                f"Golden {tier} entry | Score: {conviction_score:.3f} | "
                f"13F: {breakdown.get('13f', 0):.2f} | ARK: {breakdown.get('ark', 0):.2f} | "
                f"Correction: {breakdown.get('correction', 0):.2f}"
            ),
            alpaca_order_id=order.get("order_id"),
        )
        db.add(action)

        # Create alert
        alert = Alert(
            alert_type="golden_entry",
            symbol=symbol,
            title=f"🥇 Golden Entry: {symbol} ({tier})",
            message=(
                f"Bought {qty} shares @ ${fill_price:.2f} = ${qty * fill_price:,.2f} | "
                f"Stop: ${stop_price:.2f} | Conviction: {conviction_score:.3f} ({tier})"
            ),
            severity="info",
        )
        db.add(alert)

        db.commit()

        # ── Notifications ────────────────────────────────────────────────────
        # Map conviction to 0-4 scale for notify_entry's corners param
        corners_count = round(conviction_score * 4)

        agent_tracker.complete(
            "golden_executor",
            f"Entry filled: {symbol} {qty}sh @ ${fill_price:.2f} ({tier})"
        )

        notify_entry(
            symbol=symbol,
            qty=qty,
            price=fill_price,
            stop=stop_price,
            theme=f"Golden ({tier})",
            corners=corners_count,
        )

        logger.info(
            f"GOLDEN ENTRY: {symbol} — {qty} shares @ ${fill_price:.2f} "
            f"(stop ${stop_price:.2f}) [{tier}, {conviction_score:.3f}]"
        )

        return position
