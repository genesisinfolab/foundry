"""Watchlist API routes"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.watchlist import WatchlistItem
from app.models.theme import Theme
from app.services.watchlist_builder import WatchlistBuilder
from app.services.structure_checker import StructureChecker
from app.services.auth import require_supabase_token, require_api_key

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("/")
def list_watchlist(active_only: bool = True, clean_only: bool = False, db: Session = Depends(get_db), _token=Depends(require_supabase_token)):
    q = db.query(WatchlistItem)
    if active_only:
        q = q.filter(WatchlistItem.active == True)
    if clean_only:
        q = q.filter(WatchlistItem.structure_clean == True)
    items = q.order_by(WatchlistItem.rank_score.desc()).all()
    return [
        {
            "id": i.id, "symbol": i.symbol, "company_name": i.company_name,
            "theme_id": i.theme_id,
            "theme_name": i.theme.name if i.theme else None,
            "price": i.price, "avg_volume": i.avg_volume,
            "float_shares": i.float_shares, "market_cap": i.market_cap,
            "structure_clean": i.structure_clean, "structure_notes": i.structure_notes,
            "near_breakout": i.near_breakout, "volume_ratio": i.volume_ratio,
            "rank_score": i.rank_score,
            "catalyst_type": i.catalyst_type, "catalyst_date": i.catalyst_date,
        }
        for i in items
    ]


@router.post("/build/{theme_id}")
def build_watchlist(theme_id: int, db: Session = Depends(get_db)):
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if not theme:
        return {"error": "Theme not found"}
    builder = WatchlistBuilder()
    items = builder.build_for_theme(theme, db)
    return {"status": "ok", "items_added": len(items)}


@router.post("/check-structure")
def check_structure(db: Session = Depends(get_db)):
    checker = StructureChecker()
    clean = checker.check_all(db)
    return {"status": "ok", "clean_count": len(clean)}


@router.post("/refresh")
def refresh_watchlist(db: Session = Depends(get_db)):
    builder = WatchlistBuilder()
    builder.refresh_watchlist(db)
    return {"status": "ok"}


@router.post("/deactivate/{symbol}")
def deactivate_symbol(symbol: str, db: Session = Depends(get_db), _auth=Depends(require_api_key)):
    """Deactivate a symbol from the watchlist (admin, requires OVERRIDE_API_KEY)."""
    items = db.query(WatchlistItem).filter(
        WatchlistItem.symbol == symbol.upper(),
        WatchlistItem.active == True
    ).all()
    if not items:
        return {"status": "not_found", "symbol": symbol.upper()}
    for item in items:
        item.active = False
    db.commit()
    return {"status": "deactivated", "symbol": symbol.upper(), "count": len(items)}
