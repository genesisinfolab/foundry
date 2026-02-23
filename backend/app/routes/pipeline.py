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

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/run-full")
def run_full_pipeline(db: Session = Depends(get_db)):
    """Execute the complete Newman strategy pipeline"""
    results = {"steps": []}

    # Step 1: Theme Detection
    detector = ThemeDetector()
    themes = detector.scan_all(db)
    results["steps"].append({"step": "theme_detection", "themes_found": len(themes)})

    # Step 2: Watchlist Building (for hot/emerging themes)
    builder = WatchlistBuilder()
    total_items = 0
    active_themes = [t for t in themes if t.status in (ThemeStatus.HOT, ThemeStatus.EMERGING)]
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
    return results
