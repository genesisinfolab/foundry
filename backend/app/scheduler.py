"""Background scheduler for automated scanning — Newman persona baseline"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.services.theme_detector import ThemeDetector
from app.services.watchlist_builder import WatchlistBuilder
from app.services.structure_checker import StructureChecker
from app.services.breakout_scanner import BreakoutScanner
from app.services.trade_executor import TradeExecutor
from app.services.risk_manager import RiskManager
from app.services.notifier import notify_scan_summary
from app.services import newman_persona

logger = logging.getLogger(__name__)
logger.info(f"Newman persona loaded: {newman_persona.PERSONA_NAME} v{newman_persona.PERSONA_VERSION} — {newman_persona.PERSONA_DESCRIPTION}")


def run_scan_cycle():
    """Full scan cycle — runs every 30 minutes during market hours"""
    logger.info("Starting scheduled scan cycle...")
    db = SessionLocal()
    try:
        # Theme detection
        detector = ThemeDetector()
        themes = detector.scan_all(db)

        # Build watchlists for hot themes
        builder = WatchlistBuilder()
        for theme in themes:
            if theme.score > 0.1:
                builder.build_for_theme(theme, db)

        # Structure check
        checker = StructureChecker()
        checker.check_all(db)

        # Breakout scan
        scanner = BreakoutScanner()
        breakouts = scanner.scan_all(db)

        # Execute on breakouts
        executor = TradeExecutor()
        from app.models.watchlist import WatchlistItem
        for b in breakouts:
            item = db.query(WatchlistItem).filter(
                WatchlistItem.symbol == b["symbol"],
                WatchlistItem.active == True,
            ).first()
            if item:
                executor.shotgun_entry(item, db)

        trades_placed = len(breakouts)  # each breakout → one shotgun entry attempt
        notify_scan_summary(len(themes), len(breakouts), trades_placed)
        logger.info(f"Scan cycle complete. {len(themes)} themes, {len(breakouts)} breakouts, {trades_placed} orders.")
    except Exception as e:
        logger.error(f"Scan cycle failed: {e}")
    finally:
        db.close()


def run_risk_check():
    """Risk check — runs every 5 minutes during market hours"""
    db = SessionLocal()
    try:
        # Check positions for stop-loss / profit-taking
        rm = RiskManager()
        rm.check_all_positions(db)

        # Check pyramiding opportunities
        executor = TradeExecutor()
        from app.models.position import Position, PositionStatus
        for pos in db.query(Position).filter(Position.status == PositionStatus.OPEN).all():
            executor.check_pyramid(pos, db)
    except Exception as e:
        logger.error(f"Risk check failed: {e}")
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()

    # Full scan every 30 min (Mon-Fri, 9:30 AM - 3:30 PM ET)
    scheduler.add_job(
        run_scan_cycle,
        "cron",
        day_of_week="mon-fri",
        hour="9-15",
        minute="0,30",
        timezone="US/Eastern",
        id="scan_cycle",
    )

    # Risk check every 5 min during market hours (through 4:00 PM ET close)
    scheduler.add_job(
        run_risk_check,
        "cron",
        day_of_week="mon-fri",
        hour="9-16",
        minute="*/5",
        timezone="US/Eastern",
        id="risk_check",
    )

    return scheduler
