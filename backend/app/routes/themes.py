"""Theme API routes"""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.theme import Theme
from app.services.theme_detector import ThemeDetector
from app.services.auth import require_supabase_token

router = APIRouter(prefix="/api/themes", tags=["themes"])


@router.get("/")
def list_themes(db: Session = Depends(get_db), _token=Depends(require_supabase_token)):
    themes = db.query(Theme).order_by(Theme.score.desc()).all()
    return [
        {
            "id": t.id, "name": t.name, "status": t.status,
            "score": t.score, "news_score": t.news_score,
            "social_score": t.social_score, "etf_score": t.etf_score,
            "keywords": t.keywords, "related_etfs": t.related_etfs,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in themes
    ]


@router.get("/{theme_id}")
def get_theme(theme_id: int, db: Session = Depends(get_db), _token=Depends(require_supabase_token)):
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if not theme:
        return {"error": "Theme not found"}
    return {
        "id": theme.id, "name": theme.name, "status": theme.status,
        "score": theme.score, "news_score": theme.news_score,
        "social_score": theme.social_score, "etf_score": theme.etf_score,
        "keywords": theme.keywords, "related_etfs": theme.related_etfs,
        "sources": [
            {"type": s.source_type, "source": s.source_name,
             "headline": s.headline, "url": s.url, "sentiment": s.sentiment}
            for s in theme.sources[-20:]
        ],
    }


@router.post("/scan")
def trigger_scan(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    detector = ThemeDetector()
    themes = detector.scan_all(db)
    return {"status": "ok", "themes_found": len(themes)}
