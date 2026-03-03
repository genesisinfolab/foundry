"""
Alpha Intel Routes

REST API for managing external alpha sources and their insights.

  GET    /api/alpha/sources            — list all sources
  POST   /api/alpha/sources            — add a new source
  PATCH  /api/alpha/sources/{id}       — update name / toggle active
  DELETE /api/alpha/sources/{id}       — remove source + all insights

  GET    /api/alpha/insights           — recent insights (all sources, newest first)
  GET    /api/alpha/insights/{source_id} — insights for one source

  POST   /api/alpha/scan/{source_id}   — trigger immediate scan of a source
  POST   /api/alpha/scan-text          — submit raw text for instant Claude analysis
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alpha import AlphaSource, AlphaInsight

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alpha", tags=["alpha"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SourceCreate(BaseModel):
    name: str
    source_type: str   # youtube | url | rss | text
    url: str = ""


class SourceUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
    auto_approve: bool | None = None


class TextSubmit(BaseModel):
    label: str = "Manual Input"
    content: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_source(s: AlphaSource) -> dict:
    return {
        "id":           s.id,
        "name":         s.name,
        "source_type":  s.source_type,
        "url":          s.url or "",
        "active":       s.active,
        "auto_approve": s.auto_approve,
        "last_fetched": s.last_fetched.isoformat() if s.last_fetched else None,
        "created_at":   s.created_at.isoformat() if s.created_at else None,
    }


def _serialize_insight(i: AlphaInsight) -> dict:
    try:
        tickers = json.loads(i.tickers or "[]")
    except Exception:
        tickers = []
    return {
        "id":              i.id,
        "source_id":       i.source_id,
        "source_name":     i.source.name if i.source else "—",
        "source_type":     i.source.source_type if i.source else "text",
        "video_title":     i.video_title or "",
        "tickers":         tickers,
        "analysis":        i.analysis or "",
        "sentiment":       i.sentiment or "neutral",
        "content_preview": i.content_preview or "",
        "raw_length":      i.raw_length or 0,
        "created_at":      i.created_at.isoformat() if i.created_at else None,
    }


# ── Sources ───────────────────────────────────────────────────────────────────

@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    sources = db.query(AlphaSource).order_by(AlphaSource.created_at.desc()).all()
    return [_serialize_source(s) for s in sources]


@router.post("/sources", status_code=201)
def add_source(body: SourceCreate, db: Session = Depends(get_db)):
    allowed = ("youtube", "url", "rss", "text")
    if body.source_type not in allowed:
        raise HTTPException(400, f"source_type must be one of {allowed}")
    if body.source_type != "text" and not body.url:
        raise HTTPException(400, "url is required for youtube / url / rss sources")

    source = AlphaSource(
        name        = body.name,
        source_type = body.source_type,
        url         = body.url,
        active      = True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _serialize_source(source)


@router.patch("/sources/{source_id}")
def update_source(source_id: int, body: SourceUpdate, db: Session = Depends(get_db)):
    source = db.query(AlphaSource).filter(AlphaSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "Source not found")
    if body.name is not None:
        source.name = body.name
    if body.active is not None:
        source.active = body.active
    if body.auto_approve is not None:
        source.auto_approve = body.auto_approve
    db.commit()
    return _serialize_source(source)


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.query(AlphaSource).filter(AlphaSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "Source not found")
    db.delete(source)
    db.commit()
    return {"status": "deleted", "id": source_id}


# ── Insights ──────────────────────────────────────────────────────────────────

@router.get("/insights")
def list_insights(limit: int = 20, db: Session = Depends(get_db)):
    insights = (
        db.query(AlphaInsight)
        .order_by(AlphaInsight.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_insight(i) for i in insights]


@router.get("/insights/{source_id}")
def source_insights(source_id: int, limit: int = 10, db: Session = Depends(get_db)):
    insights = (
        db.query(AlphaInsight)
        .filter(AlphaInsight.source_id == source_id)
        .order_by(AlphaInsight.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_insight(i) for i in insights]


# ── Scan triggers ─────────────────────────────────────────────────────────────

@router.post("/scan/{source_id}")
def scan_source(source_id: int, db: Session = Depends(get_db)):
    """Trigger an immediate fetch + Claude analysis for a registered source."""
    source = db.query(AlphaSource).filter(AlphaSource.id == source_id).first()
    if not source:
        raise HTTPException(404, "Source not found")
    if source.source_type == "text":
        raise HTTPException(400, "Text sources cannot be scanned — use /scan-text instead")

    from app.services.alpha_scanner import scan_source as _scan
    insight = _scan(source, db)
    if insight is None:
        raise HTTPException(500, "Scan failed — check server logs for details")
    return _serialize_insight(insight)


@router.post("/scan-text")
def scan_text(body: TextSubmit, db: Session = Depends(get_db)):
    """Submit raw text (article paste, manual notes, stream recap) for instant analysis."""
    if not body.content or len(body.content.strip()) < 50:
        raise HTTPException(400, "Content too short — need at least 50 characters")

    from app.services.alpha_scanner import scan_text as _scan_text
    insight = _scan_text(body.label, body.content.strip(), db)
    if insight is None:
        raise HTTPException(500, "Text analysis failed — check server logs")
    return _serialize_insight(insight)
