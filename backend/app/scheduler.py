"""Background scheduler for automated scanning.

Registered strategies:
  - newman  : Jeffrey Newman penny-stock sector breakout (default)
  - golden  : Chuck's generational-tech conviction thesis

Each strategy runs in its own named scheduler job so they can be
enabled/disabled independently via ACTIVE_STRATEGIES config.
"""
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
from app.strategies.newman import NewmanStrategy
from app.strategies.golden import GoldenStrategy

logger = logging.getLogger(__name__)
logger.info(f"Newman persona loaded: {newman_persona.PERSONA_NAME} v{newman_persona.PERSONA_VERSION} — {newman_persona.PERSONA_DESCRIPTION}")

# Strategy registry — add new strategies here
STRATEGY_REGISTRY = {
    "newman": NewmanStrategy,
    "golden": GoldenStrategy,
}


def get_active_strategies() -> list:
    """Return instantiated strategy objects based on ACTIVE_STRATEGIES env var.

    Defaults to newman only. Set ACTIVE_STRATEGIES=newman,golden to run both.
    """
    from app.config import get_settings
    settings = get_settings()
    active_ids = getattr(settings, "active_strategies", "newman").split(",")
    strategies = []
    for sid in active_ids:
        sid = sid.strip()
        if sid in STRATEGY_REGISTRY:
            strategies.append(STRATEGY_REGISTRY[sid]())
            logger.info(f"Strategy registered: {sid}")
        else:
            logger.warning(f"Unknown strategy id '{sid}' in ACTIVE_STRATEGIES — skipped")
    return strategies


def run_golden_scan_cycle():
    """Golden strategy scan cycle — runs full screening/scoring via GoldenScanner,
    then passes qualified candidates to GoldenExecutor for paper trade execution.
    """
    logger.info("Starting Golden strategy scan cycle...")
    from app.services.golden_scanner import GoldenScanner
    from app.services.golden_executor import GoldenExecutor
    try:
        scanner = GoldenScanner()
        result = scanner.run_scan()
        logger.info(
            f"Golden scan complete | correction={result['correction'].get('score', '?')}/100 | "
            f"universe={result['universe_size']} | "
            f"qualified={result['qualified_count']}/{result['candidates_scored']} | "
            f"duration={result['scan_duration_secs']}s"
        )
        if result["qualified"]:
            top = result["qualified"][:5]
            logger.info(
                f"Golden top candidates: "
                + ", ".join(f"{c['symbol']}({c['tier']}, {c['conviction_score']:.2f})" for c in top)
            )

            # Execute trades for qualified candidates
            db = SessionLocal()
            try:
                executor = GoldenExecutor()
                opened = executor.execute_candidates(result["qualified"], db)
                if opened:
                    logger.info(
                        f"Golden Executor: opened {len(opened)} positions — "
                        + ", ".join(f"{p.symbol}" for p in opened)
                    )
                else:
                    logger.info("Golden Executor: no new positions opened this cycle")
            except Exception as e:
                logger.error(f"Golden Executor failed: {e}", exc_info=True)
            finally:
                db.close()
        else:
            logger.info("Golden scan: no qualified candidates this cycle")
    except Exception as e:
        logger.error(f"Golden scan cycle failed: {e}", exc_info=True)


def run_scan_cycle():
    """Full scan cycle — runs at the top of every hour during market hours"""
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


def run_watchlist_refresh():
    """
    Always-on full research cycle (steps 1–4, no trade execution).
    Keeps themes, watchlist, structure flags, and breakout candidates current
    24/7 except Saturday so the pre-market queue is always populated.
    """
    logger.info("Starting watchlist refresh (steps 1–4, no trades)...")
    db = SessionLocal()
    try:
        # Step 1: theme detection
        detector = ThemeDetector()
        themes = detector.scan_all(db)

        # Step 2: watchlist build
        builder = WatchlistBuilder()
        for theme in themes:
            if theme.score > 0.1:
                builder.build_for_theme(theme, db)

        # Step 3: structure check (flags structure_clean on each item)
        checker = StructureChecker()
        checker.check_all(db)

        # Step 4: breakout scan (updates near_breakout flags — no orders placed)
        scanner = BreakoutScanner()
        breakouts = scanner.scan_all(db)

        logger.info(
            f"Watchlist refresh complete. {len(themes)} theme(s), "
            f"{len(breakouts)} breakout candidate(s) in queue."
        )
    except Exception as e:
        logger.error(f"Watchlist refresh failed: {e}")
    finally:
        db.close()


def run_research_cycle():
    """
    Research-only cycle — runs Sunday and pre/post market.
    Does NOT execute trades (markets closed / pre-open data aggregation).
    Steps: theme detection → watchlist → structure → breakout scan (flags only).
    Results stored in DB so the Monday morning scan starts with fresh signals.
    """
    logger.info("Starting research cycle (no trade execution)...")
    db = SessionLocal()
    try:
        detector = ThemeDetector()
        themes = detector.scan_all(db)

        builder = WatchlistBuilder()
        for theme in themes:
            if theme.score > 0.1:
                builder.build_for_theme(theme, db)

        checker = StructureChecker()
        checker.check_all(db)

        # Breakout scan updates near_breakout flags in DB — no trades placed
        scanner = BreakoutScanner()
        breakouts = scanner.scan_all(db)

        logger.info(
            f"Research cycle complete. {len(themes)} themes, "
            f"{len(breakouts)} breakout candidate(s) flagged for Monday open."
        )
    except Exception as e:
        logger.error(f"Research cycle failed: {e}")
    finally:
        db.close()


def run_scan_with_health():
    """Wrapper: full scan cycle followed immediately by health check."""
    from app.services.health_check import run as health_run
    from app.services.notifier import notify_health_check
    run_scan_cycle()
    try:
        results = health_run()
        fails = [r for r in results if r["status"] == "FAIL"]
        warns = [r for r in results if r["status"] == "WARN"]
        overall = results[-1]["status"] if results else "UNKNOWN"
        fail_details = [r["detail"][:80] for r in fails[:3]]
        warn_details = [r["detail"][:80] for r in warns[:2]]
        notify_health_check(overall, len(fails), len(warns), fail_details, warn_details)
    except Exception as e:
        logger.error(f"Post-scan health check failed: {e}")


def create_scheduler() -> BackgroundScheduler:
    # NOTE: APScheduler state is in-memory only. On Fly.io with auto_stop_machines="stop",
    # the VM can be stopped between requests and all scheduled jobs restart from scratch on
    # next wake — causing missed scan cycles. Set min_machines_running = 1 in fly.toml
    # [http_service] so the VM stays alive through market hours.
    logger.info("Scheduler created — APScheduler in-memory. min_machines_running=1 required in fly.toml to avoid missed cycles.")
    scheduler = BackgroundScheduler()

    # Full scan + trade execution at top of every hour during market hours (Mon–Fri)
    scheduler.add_job(
        run_scan_with_health,
        "cron",
        day_of_week="mon-fri",
        hour="9-16",
        minute="0",
        timezone="US/Eastern",
        id="scan_cycle",
    )

    # Aftermarket final scan — 8 PM ET, Mon–Fri
    # One last signal check after extended trading closes for the night.
    scheduler.add_job(
        run_scan_with_health,
        "cron",
        day_of_week="mon-fri",
        hour="20",
        minute="0",
        timezone="US/Eastern",
        id="aftermarket_scan",
    )

    # Risk check every 5 min during market hours (Mon–Fri)
    scheduler.add_job(
        run_risk_check,
        "cron",
        day_of_week="mon-fri",
        hour="9-16",
        minute="*/5",
        timezone="US/Eastern",
        id="risk_check",
    )

    # Research-only scan on Sunday (no trades — aggregates signals for Monday open)
    # Runs at 10 AM, 1 PM, and 4 PM ET so data is fresh before Monday pre-market
    scheduler.add_job(
        run_research_cycle,
        "cron",
        day_of_week="sun",
        hour="10,13,16",
        minute="0",
        timezone="US/Eastern",
        id="research_sunday",
    )

    # Pre-market research Mon–Fri: 7 AM ET refresh before market open
    scheduler.add_job(
        run_research_cycle,
        "cron",
        day_of_week="mon-fri",
        hour="7",
        minute="0",
        timezone="US/Eastern",
        id="research_premarket",
    )

    # Always-on watchlist refresh (steps 1+2) — Sun–Fri, every 3 hours during
    # off-hours (midnight, 3AM, 6AM, 5PM, 8PM, 11PM).  Keeps theme and watchlist
    # data current outside market hours.  Saturday is intentionally excluded.
    scheduler.add_job(
        run_watchlist_refresh,
        "cron",
        day_of_week="sun,mon,tue,wed,thu,fri",
        hour="0,3,6,17,20,23",
        minute="0",
        timezone="US/Eastern",
        id="watchlist_refresh",
    )

    # Golden strategy: research scan runs daily at 8 AM and 6 PM ET (stub — no trades)
    # Registers early so the job exists when the full scanner is implemented.
    # Set ACTIVE_STRATEGIES=newman,golden to also run the full golden scan cycle.
    scheduler.add_job(
        run_golden_scan_cycle,
        "cron",
        day_of_week="mon-fri",
        hour="8,18",
        minute="30",
        timezone="US/Eastern",
        id="golden_scan",
    )

    active = get_active_strategies()
    logger.info(
        f"Scheduler initialized | active strategies: {[s.strategy_id for s in active]} | "
        f"registered jobs: {[j.id for j in scheduler.get_jobs()]}"
    )

    return scheduler
