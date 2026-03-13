"""
Trade Executor — Steps 5-6 of Newman Strategy

Handles:
- Shotgun entries (small starter positions across theme)
- Pyramiding into winners
- All trades via Alpaca paper trading
"""
import logging
import threading
import time

# Semaphore caps concurrent "immediately-wrong" watcher threads so
# rapid-fire entries don't create an unbounded thread pool.
_WATCHER_SEM = threading.Semaphore(10)
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.position import Position, PositionAction, PositionStatus
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert
from app.integrations.alpaca_client import AlpacaClient
from app.services.risk_manager import calculate_atr
from app.services.notifier import notify_trade, notify_entry, notify_exit, notify_pyramid, notify_stop
from app.services.newman_persona import score_corners, position_size_for_corners
from app.services.audit_log import write_pretrade
from app.services.reasoning_log import write_reasoning
from app.services import agent_tracker

logger = logging.getLogger(__name__)

_WATCH_MINUTES   = 5     # how long to monitor post-entry (Test A: 15→5)
_WATCH_POLL_SECS = 30    # price poll interval during watch window (Test A: 60→30)


def _watch_immediately_wrong(
    symbol: str,
    position_id: int,
    entry_price: float,
    atr: float,
    paper: bool,
) -> None:
    """
    Background daemon thread: poll price for _WATCH_MINUTES after entry.
    If price drops more than 1×ATR below entry, exit immediately.

    Newman: "If I bought at 30.1 and it went to 30.0, I hit the bid and was out."
    This is his primary exit — fires in the first minutes, not after a 5% loss.

    Uses its own SQLAlchemy session (threads cannot share sessions).
    """
    from app.database import SessionLocal
    from app.integrations.alpaca_client import AlpacaClient
    from app.models.position import Position, PositionAction, PositionStatus
    from app.models.alert import Alert

    threshold   = entry_price - (2.0 * atr)   # 2×ATR below entry (Test A: was 1×ATR)
    deadline    = time.monotonic() + _WATCH_MINUTES * 60
    alpaca      = AlpacaClient()
    agent_name  = f"immediately_wrong:{symbol}"

    agent_tracker.spawn(agent_name,
        f"{symbol}: watching {_WATCH_MINUTES}min | exit if < ${threshold:.3f} (2×ATR=${atr:.3f})")
    logger.info(f"WATCH START {symbol}: entry=${entry_price:.3f} threshold=${threshold:.3f} ATR={atr:.3f} (2×ATR)")

    while time.monotonic() < deadline:
        time.sleep(_WATCH_POLL_SECS)

        remaining = max(0, (deadline - time.monotonic()) / 60)
        try:
            snapshot = alpaca.get_snapshot(symbol)
            current  = snapshot.get("latest_trade_price") or 0
            if not current or current <= 0:
                continue

            agent_tracker.update(agent_name,
                f"{symbol}: ${current:.3f} | threshold ${threshold:.3f} | {remaining:.0f}min left")

            if current >= threshold:
                continue   # still OK — keep watching

            # ── Immediately wrong: price broke below threshold ────────────────
            logger.info(f"IMMEDIATELY WRONG {symbol}: ${current:.3f} < ${threshold:.3f} — exiting")
            agent_tracker.update(agent_name, f"{symbol}: IMMEDIATELY WRONG @ ${current:.3f} — closing")

            db = SessionLocal()
            try:
                pos = db.query(Position).filter(
                    Position.id == position_id,
                    Position.status == PositionStatus.OPEN,
                ).first()

                if not pos:
                    logger.info(f"WATCH {symbol}: position already closed, skipping")
                    break

                write_pretrade(
                    event="immediately_wrong",
                    symbol=symbol,
                    side="sell",
                    qty=pos.qty,
                    price=current,
                    stop_price=threshold,
                    pnl_pct=(current - entry_price) / entry_price,
                    paper=paper,
                    extra={
                        "entry_price":    entry_price,
                        "atr":            round(atr, 4),
                        "threshold":      round(threshold, 4),
                        "minutes_held":   round(_WATCH_MINUTES - remaining, 1),
                        "trigger":        "immediately_wrong",
                    },
                )

                write_reasoning(
                    agent="immediately_wrong_watch",
                    event="immediately_wrong",
                    symbol=symbol,
                    action="exit",
                    corners={"chart": False, "structure": False,
                             "sector": False, "catalyst": False},
                    conviction=0,
                    notes=(
                        f"Price ${current:.3f} crossed below entry−2×ATR threshold ${threshold:.3f} "
                        f"within {_WATCH_MINUTES - remaining:.0f} minutes of entry. "
                        f"Newman rule: exit immediately when direction is wrong from the start."
                    ),
                )

                try:
                    order = alpaca.close_position(symbol)
                    order_id = order.get("order_id")
                except Exception as e:
                    logger.error(f"IMMEDIATELY WRONG close order failed for {symbol}: {e}")
                    break

                pnl = (current - entry_price) * pos.qty
                pos.status       = PositionStatus.STOPPED_OUT
                pos.realized_pnl = pnl
                pos.closed_at    = datetime.now(timezone.utc)

                db.add(PositionAction(
                    position=pos,
                    action_type="immediately_wrong",
                    qty=pos.qty,
                    price=current,
                    reason=(
                        f"Immediately wrong: ${current:.3f} < entry−2×ATR "
                        f"(${entry_price:.3f} − 2×${atr:.3f} = ${threshold:.3f})"
                    ),
                    alpaca_order_id=order_id,
                ))

                db.add(Alert(
                    alert_type="immediately_wrong",
                    symbol=symbol,
                    title=f"Immediately Wrong Exit: {symbol}",
                    message=(
                        f"Exited {pos.qty} shares @ ${current:.3f} within {_WATCH_MINUTES - remaining:.0f}min. "
                        f"P&L: ${pnl:.2f} ({(current - entry_price) / entry_price:.2%})"
                    ),
                    severity="warning",
                ))
                db.commit()

                from app.services.notifier import notify_stop
                notify_stop(symbol, current, (current - entry_price) / entry_price)

            finally:
                db.close()

            break   # exit loop after closing

        except Exception as e:
            logger.warning(f"WATCH {symbol} poll error: {e}")

    agent_tracker.complete(agent_name,
        f"{symbol}: watch complete ({_WATCH_MINUTES}min elapsed)")


class TradeExecutor:
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.settings = get_settings()

    def shotgun_entry(self, item: WatchlistItem, db: Session) -> Optional[Position]:
        """
        Place a small starter position (Newman's 'shotgun' approach).
        Buy a small amount to have skin in the game.
        """
        s = self.settings

        # ── Kill switch: PAUSE / STOP ALL blocks new entries ─────────────────
        from app.services import kill_switch
        if kill_switch.is_paused():
            ks = kill_switch.status()
            logger.info(
                f"BLOCKED {item.symbol}: engine paused — {ks.get('reason', 'manual override')}"
            )
            return None

        # Check if we already have an open position
        existing = db.query(Position).filter(
            Position.symbol == item.symbol,
            Position.status == PositionStatus.OPEN,
        ).first()
        if existing:
            logger.info(f"Already have position in {item.symbol}")
            return existing

        # ── Stopped-out cooldown (Newman rule: exit, forget it, move on) ──
        # Block re-entry for COOLDOWN_HOURS after a stop-out on the same ticker.
        # IMPORTANT: use a fresh session here — the background _watch_immediately_wrong
        # thread commits STOPPED_OUT via its own SessionLocal. The shared `db` session
        # passed from the scan cycle may have cached state that predates that commit,
        # causing the cooldown check to silently pass and allowing re-entry (the LPBBU loop).
        cooldown_hours = getattr(self.settings, "stopped_out_cooldown_hours", 24)
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
        from app.database import SessionLocal as _SL
        _cddb = _SL()
        try:
            recent_stop = _cddb.query(Position).filter(
                Position.symbol == item.symbol,
                Position.status == PositionStatus.STOPPED_OUT,
                Position.closed_at >= cooldown_cutoff,
            ).first()
        finally:
            _cddb.close()
        if recent_stop:
            hours_ago = (datetime.now(timezone.utc) - recent_stop.closed_at).total_seconds() / 3600
            logger.info(
                f"COOLDOWN: {item.symbol} stopped out {hours_ago:.1f}h ago — "
                f"blocked for {cooldown_hours}h. Skipping entry."
            )
            return None

        # Check account buying power
        account = self.alpaca.get_account()
        if account["cash"] < s.starter_position_usd:
            logger.warning(f"Insufficient cash for starter: ${account['cash']:.2f}")
            return None

        if not item.price or item.price <= 0:
            return None

        # Corners evaluation — catalyst_type written by breakout_scanner when
        # Finnhub finds a qualifying headline within 48h of the trendline break.
        corners_eval = {
            "chart":     bool(item.near_breakout),
            "structure": bool(item.structure_clean),
            "sector":    item.theme is not None,
            "catalyst":  bool(item.catalyst_type),
        }
        conviction = sum(corners_eval.values())

        # ── Newman sizing: scale position with conviction ──────────────────────
        # 1-2 corners = nibble ($2,500 starter)
        # 3 corners   = half position ($5,000)
        # 4 corners   = full position ($10,000, then pyramid from there)
        from app.services.newman_persona import position_size_for_corners
        position_usd = position_size_for_corners(conviction, s.starter_position_usd)
        if position_usd == 0 or account["cash"] < position_usd:
            logger.info(f"Skipping {item.symbol}: conviction={conviction} position_usd=${position_usd:.0f} cash=${account['cash']:.0f}")
            return None
        qty = int(position_usd / item.price)
        if qty < 1:
            return None

        # ── Build signal list from item's DB state for Claude context ──────────
        # The breakout scanner writes these fields after each scan_single() run.
        # Passing them here gives Claude quantitative context at execution time.
        entry_signals: list[str] = []
        if item.near_breakout and item.breakout_level:
            clearance = (item.price / item.breakout_level - 1) * 100 if item.breakout_level > 0 else 0
            entry_signals.append(
                f"Trendline break: ${item.price:.2f} > resistance ${item.breakout_level:.2f} "
                f"(+{clearance:.1f}% clearance)"
            )
        if item.volume_ratio:
            entry_signals.append(f"Volume ratio: {item.volume_ratio:.1f}× average")
        if item.catalyst_type:
            entry_signals.append(f"Catalyst: {item.catalyst_notes or item.catalyst_type}")
        if item.theme:
            entry_signals.append(f"Theme: {item.theme.name}")
        entry_signals.append(f"Conviction: {conviction}/4")

        # ── Claude gate — second quality check before placing any order ────────
        # Only called when conviction >= 1 to avoid wasting API calls.
        # A Claude failure always defaults to approve=True (never blocks a trade).
        try:
            from app.services.claude_gate import evaluate_trade as _claude_eval
            if conviction >= 1:
                _cl = _claude_eval(
                    symbol=item.symbol,
                    corners=corners_eval,
                    conviction=conviction,
                    theme=item.theme.name if item.theme else "",
                    price=float(item.price),
                    signals=entry_signals,
                )
                # Log Claude's view regardless of decision
                write_reasoning(
                    agent="claude_gate",
                    event="trade_review",
                    symbol=item.symbol,
                    action="entry" if _cl["approve"] else "claude_veto",
                    corners=corners_eval,
                    conviction=conviction,
                    notes=(
                        f"Claude: {'GO' if _cl['approve'] else 'NO-GO'} "
                        f"({_cl['confidence']}) — {_cl['reasoning']}"
                        + (f" | Risk: {_cl['risk_note']}" if _cl.get('risk_note') else "")
                    ),
                )
                if not _cl["approve"]:
                    logger.info(f"CLAUDE VETO {item.symbol}: {_cl['reasoning']}")
                    return None
        except Exception as _ce:
            logger.warning(f"Claude gate error for {item.symbol}: {_ce} — proceeding")

        agent_tracker.spawn("trade_executor", f"Shotgun entry: {item.symbol}")
        write_reasoning(
            agent="trade_executor",
            event="shotgun_entry",
            symbol=item.symbol,
            action="entry",
            corners=corners_eval,
            conviction=conviction,
            notes=f"Theme: {item.theme.name if item.theme else 'none'} | "
                  f"Cash: ${account['cash']:,.0f} | Size: ${position_usd:.0f} ({conviction}/4 corners) | Qty: {qty}",
        )

        # Pre-trade audit — written before order fires
        write_pretrade(
            event="shotgun_entry",
            symbol=item.symbol,
            side="buy",
            qty=qty,
            price=item.price,
            stop_price=item.price * (1 + s.stop_loss_pct),  # floor stop; ATR stop set post-fill
            theme=item.theme.name if item.theme else "",
            cash=account["cash"],
            paper=s.alpaca_paper,
            checks=["no_existing_position", "cooldown_clear", "sufficient_cash", "qty_ge_1"],
        )

        # Place order
        try:
            order = self.alpaca.place_market_order(item.symbol, qty, "buy")
        except Exception as e:
            logger.error(f"Order failed for {item.symbol}: {e}")
            return None

        # Get actual fill price from Alpaca (paper fills are near-instant)
        fill_price = item.price
        try:
            time.sleep(1)  # brief wait for fill
            alpaca_positions = {p["symbol"]: p for p in self.alpaca.get_positions()}
            if item.symbol in alpaca_positions:
                fill_price = alpaca_positions[item.symbol]["avg_entry_price"]
                qty = int(alpaca_positions[item.symbol]["qty"])
                logger.info(f"Actual fill price for {item.symbol}: ${fill_price:.3f} (watchlist was ${item.price:.3f})")
        except Exception as e:
            logger.warning(f"Could not fetch fill price for {item.symbol}, using watchlist price: {e}")

        # ATR-based stop: 1.5x ATR below fill price, floor at stop_loss_pct
        stop_price = fill_price * (1 + s.stop_loss_pct)
        atr = 0.0
        try:
            bars = self.alpaca.get_bars(item.symbol, days=20)
            if len(bars) >= 15:
                from app.services.risk_manager import calculate_atr
                atr = calculate_atr(bars)
                if atr > 0:
                    atr_stop = fill_price - (1.5 * atr)
                    stop_price = max(atr_stop, fill_price * (1 + s.stop_loss_pct))
                    logger.info(f"ATR stop for {item.symbol}: ${stop_price:.2f} (ATR={atr:.2f}, floor=${fill_price * (1 + s.stop_loss_pct):.2f})")
        except Exception as e:
            logger.warning(f"ATR stop calculation failed for {item.symbol}: {e}")

        # Record position
        position = Position(
            symbol=item.symbol,
            theme_id=item.theme_id,
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
        )
        db.add(position)

        # Record action
        action = PositionAction(
            position=position,
            action_type="buy",
            qty=qty,
            price=item.price,
            reason=f"Shotgun entry for theme: {item.theme.name if item.theme else 'unknown'}",
            alpaca_order_id=order.get("order_id"),
        )
        db.add(action)

        # Create alert
        alert = Alert(
            alert_type="trade_entry",
            symbol=item.symbol,
            title=f"🎯 Shotgun Entry: {item.symbol}",
            message=f"Bought {qty} shares @ ${fill_price:.2f} = ${qty * fill_price:.2f} | Stop: ${stop_price:.2f}",
            severity="info",
        )
        db.add(alert)

        db.commit()

        # Score corners for this entry (used in WhatsApp notification)
        corners = score_corners(
            chart_breakout=item.near_breakout or False,
            structure_clean=item.structure_clean or False,
            sector_active=item.theme is not None,
            catalyst_present=bool(item.catalyst_type),
        )

        agent_tracker.complete("trade_executor",
            f"Entry filled: {item.symbol} {qty}sh @ ${fill_price:.2f}")

        notify_entry(
            symbol=item.symbol,
            qty=qty,
            price=fill_price,
            stop=stop_price,
            theme=item.theme.name if item.theme else "",
            corners=corners,
        )
        logger.info(f"ENTRY: {item.symbol} — {qty} shares @ ${fill_price:.2f} (stop ${stop_price:.2f}) [{corners}/4 corners]")

        # ── Launch immediately-wrong watch ────────────────────────────────────
        # Daemon thread: monitors price for _WATCH_MINUTES. If it drops > 1×ATR
        # below fill price it exits immediately — Newman's primary exit mechanism.
        # Uses ATR computed above; falls back to 2% of fill price if ATR is zero.
        effective_atr = atr if atr > 0 else fill_price * 0.02

        def _bounded_watch(*args, **kwargs):
            with _WATCHER_SEM:
                _watch_immediately_wrong(*args, **kwargs)

        watch_thread = threading.Thread(
            target=_bounded_watch,
            args=(item.symbol, position.id, fill_price, effective_atr, s.alpaca_paper),
            daemon=True,
            name=f"watch:{item.symbol}",
        )
        watch_thread.start()
        logger.info(f"WATCH {item.symbol}: 15-min immediately-wrong monitor started "
                    f"(threshold ${fill_price - effective_atr:.3f})")

        return position

    def check_pyramid(self, position: Position, db: Session) -> Optional[PositionAction]:
        """
        Check if we should pyramid into a winning position.
        Newman: scale in if up 3%+ with continued volume.
        """
        s = self.settings

        if position.pyramid_level >= s.max_pyramid_levels:
            return None

        # Get current data
        try:
            snapshot = self.alpaca.get_snapshot(position.symbol)
            current_price = snapshot.get("latest_trade_price", 0)
        except Exception:
            return None

        if not current_price or current_price <= 0:
            return None

        # Calculate P&L
        pnl_pct = (current_price - position.avg_entry_price) / position.avg_entry_price
        position.current_price = current_price
        position.unrealized_pnl_pct = pnl_pct
        position.unrealized_pnl = (current_price - position.avg_entry_price) * position.qty

        # Pyramid tiers: 3% profit = tier 1, 8% = tier 2, 15% = tier 3
        pyramid_thresholds = [0.03, 0.08, 0.15, 0.25]
        next_level = position.pyramid_level + 1
        if next_level > len(pyramid_thresholds):
            return None

        threshold = pyramid_thresholds[position.pyramid_level]
        if pnl_pct < threshold:
            db.commit()
            return None

        # Check theme exposure limits
        account = self.alpaca.get_account()
        portfolio_value = account["portfolio_value"]

        # Position size per tier: 2%, 5%, 10%, 10% of portfolio
        tier_sizes = [0.02, 0.05, 0.10, 0.10]
        add_usd = portfolio_value * tier_sizes[min(position.pyramid_level, len(tier_sizes) - 1)]

        # Check max single position limit
        current_value = position.qty * current_price
        if (current_value + add_usd) / portfolio_value > s.max_single_position_pct:
            logger.info(f"Max position limit reached for {position.symbol}")
            db.commit()
            return None

        # Calculate shares to add
        add_qty = int(add_usd / current_price)
        if add_qty < 1:
            db.commit()
            return None

        agent_tracker.spawn("trade_executor", f"Pyramid L{next_level}: {position.symbol}")
        write_reasoning(
            agent="trade_executor",
            event="pyramid",
            symbol=position.symbol,
            action="pyramid",
            corners={"chart": True, "structure": pnl_pct >= threshold,
                     "sector": True, "catalyst": False},
            conviction=next_level,
            notes=f"Level {next_level} | P&L {pnl_pct:.1%} | Adding {add_qty} shares @ ${current_price:.2f}",
        )

        # Pre-trade audit — written before order fires
        write_pretrade(
            event="pyramid",
            symbol=position.symbol,
            side="buy",
            qty=add_qty,
            price=current_price,
            pnl_pct=pnl_pct,
            pyramid_level=next_level,
            portfolio_value=portfolio_value,
            position_current_value=position.qty * current_price,
            paper=s.alpaca_paper,
            checks=["pyramid_level_under_max", "price_above_threshold", "under_max_single_position"],
        )

        # Place pyramid order
        try:
            order = self.alpaca.place_market_order(position.symbol, add_qty, "buy")
        except Exception as e:
            logger.error(f"Pyramid order failed for {position.symbol}: {e}")
            db.commit()
            return None

        # Update position
        total_cost = position.cost_basis + (add_qty * current_price)
        total_qty = position.qty + add_qty
        position.avg_entry_price = total_cost / total_qty
        position.qty = total_qty
        position.cost_basis = total_cost
        position.pyramid_level = next_level
        position.market_value = total_qty * current_price

        # Record action
        action = PositionAction(
            position=position,
            action_type="pyramid",
            qty=add_qty,
            price=current_price,
            reason=f"Pyramid level {next_level}: {pnl_pct:.1%} gain, adding ${add_usd:.0f}",
            alpaca_order_id=order.get("order_id"),
        )
        db.add(action)

        alert = Alert(
            alert_type="pyramid",
            symbol=position.symbol,
            title=f"📈 Pyramid L{next_level}: {position.symbol}",
            message=f"Added {add_qty} shares @ ${current_price:.2f}. Total: {total_qty} shares, P&L: {pnl_pct:.1%}",
            severity="info",
        )
        db.add(alert)

        db.commit()
        notify_pyramid(
            symbol=position.symbol,
            level=next_level,
            add_qty=add_qty,
            price=current_price,
            total_qty=total_qty,
            pnl_pct=pnl_pct * 100,
        )
        logger.info(f"PYRAMID L{next_level}: {position.symbol} +{add_qty} @ ${current_price:.2f}, P&L {pnl_pct:.1%}")
        return action
