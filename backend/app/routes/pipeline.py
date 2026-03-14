"""Pipeline API — run the full Newman strategy end-to-end"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.theme import Theme, ThemeStatus
from app.models.watchlist import WatchlistItem
from app.services.theme_detector import ThemeDetector
from app.services.watchlist_builder import WatchlistBuilder
from app.services.structure_checker import StructureChecker
from app.services.breakout_scanner import BreakoutScanner
from app.services.trade_executor import TradeExecutor
from app.services.risk_manager import RiskManager
from app.services.auth import require_api_key
from app.services.notifier import notify_scan_summary, notify_health_check, _send

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/notify-test")
def test_notification(_auth=Depends(require_api_key)):
    """Send a test WhatsApp notification. Use to verify the notification path is working."""
    import datetime
    from app.config import get_settings
    s = get_settings()
    msg = f"FOUNDRY TEST — notification path verified at {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    sent = _send(msg)
    return {
        "sent": sent,
        "whatsapp_number_configured": bool(s.whatsapp_number),
        "ultramsg_configured": bool(s.ultramsg_instance_id and s.ultramsg_token),
        "callmebot_configured": bool(s.callmebot_api_key),
        "message": "Check your WhatsApp — if sent=true, the notification path is working." if sent else "All notification methods failed. Check Fly.io secrets: WHATSAPP_NUMBER, CALLMEBOT_API_KEY or ULTRAMSG_INSTANCE_ID + ULTRAMSG_TOKEN.",
    }


@router.post("/run-scanner")
def run_scanner(db: Session = Depends(get_db), _auth=Depends(require_api_key)):
    """Run breakout scanner only."""
    scanner   = BreakoutScanner()
    breakouts = scanner.scan_all(db)
    return {"step": "breakout_scan", "breakouts": len(breakouts), "signals": breakouts}


@router.post("/run-golden")
def run_golden(db: Session = Depends(get_db), _auth=Depends(require_api_key)):
    """Run Golden strategy scan cycle — sector screening, conviction scoring, and execution."""
    from app.services.golden_scanner import GoldenScanner
    from app.services.golden_executor import GoldenExecutor

    scanner = GoldenScanner()
    result = scanner.run_scan()

    opened = []
    if result["qualified"]:
        executor = GoldenExecutor()
        positions = executor.execute_candidates(result["qualified"], db)
        opened = [
            {"symbol": p.symbol, "qty": p.qty, "price": p.avg_entry_price, "strategy": "golden"}
            for p in positions
        ]

    return {
        "step": "golden_scan",
        "correction_score": result["correction"].get("score", 0),
        "correcting_sectors": result.get("correcting_sectors", []),
        "universe_size": result["universe_size"],
        "candidates_scored": result["candidates_scored"],
        "qualified_count": result["qualified_count"],
        "qualified_top5": [
            {"symbol": c["symbol"], "tier": c["tier"], "score": c["conviction_score"], "price": c["price"]}
            for c in result["qualified"][:5]
        ],
        "positions_opened": opened,
        "scan_duration_secs": result["scan_duration_secs"],
    }


@router.post("/run-risk")
def run_risk(db: Session = Depends(get_db), _auth=Depends(require_api_key)):
    """Run risk manager check on all open positions."""
    rm      = RiskManager()
    actions = rm.check_all_positions(db)
    return {"step": "risk_management", "actions": len(actions), "detail": actions}


@router.post("/run-full")
def run_full_pipeline(db: Session = Depends(get_db), _auth=Depends(require_api_key)):
    """Execute the complete Newman strategy pipeline"""
    results = {"steps": []}

    # Step 1: Theme Detection
    detector = ThemeDetector()
    themes = detector.scan_all(db)
    results["steps"].append({"step": "theme_detection", "themes_found": len(themes)})

    # Step 2: Watchlist Building (for hot/emerging themes)
    builder = WatchlistBuilder()
    total_items = 0
    active_themes = [t for t in themes if t.score > 0.1]  # Process any theme with signal
    for theme in active_themes:
        items = builder.build_for_theme(theme, db)
        total_items += len(items)
    results["steps"].append({"step": "watchlist_build", "items_added": total_items, "themes_processed": len(active_themes)})

    # Step 3: Share Structure Check
    checker = StructureChecker()
    clean = checker.check_all(db)
    results["steps"].append({"step": "structure_check", "clean_count": len(clean)})

    # Step 4: Breakout Scan
    scanner = BreakoutScanner()
    breakouts = scanner.scan_all(db)
    results["steps"].append({"step": "breakout_scan", "breakouts": len(breakouts)})

    # Step 5: Execute trades for breakout stocks
    executor = TradeExecutor()
    entries = 0
    for b in breakouts:
        item = db.query(WatchlistItem).filter(
            WatchlistItem.symbol == b["symbol"],
            WatchlistItem.active == True,
        ).first()
        if item:
            pos = executor.shotgun_entry(item, db)
            if pos:
                entries += 1
    results["steps"].append({"step": "trade_execution", "entries": entries})

    # Step 6: Check existing positions for pyramiding
    pyramids = 0
    from app.models.position import Position, PositionStatus
    open_positions = db.query(Position).filter(Position.status == PositionStatus.OPEN).all()
    for pos in open_positions:
        action = executor.check_pyramid(pos, db)
        if action:
            pyramids += 1
    results["steps"].append({"step": "pyramid_check", "pyramids": pyramids})

    # Step 7: Risk management
    rm = RiskManager()
    risk_actions = rm.check_all_positions(db)
    results["steps"].append({"step": "risk_management", "actions": len(risk_actions)})

    results["summary"] = rm.get_portfolio_summary(db)

    # ── Notifications ────────────────────────────────────────────────────────
    notify_scan_summary(len(active_themes), entries, entries)

    try:
        from app.services.health_check import run as health_run
        health_results = health_run()
        fails = [r for r in health_results if r["status"] == "FAIL"]
        warns = [r for r in health_results if r["status"] == "WARN"]
        overall = health_results[-1]["status"] if health_results else "UNKNOWN"
        fail_details = [r["detail"][:80] for r in fails[:3]]
        warn_details = [r["detail"][:80] for r in warns[:2]]
        notify_health_check(overall, len(fails), len(warns), fail_details, warn_details)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Post-pipeline health check failed: {e}")

    return results
