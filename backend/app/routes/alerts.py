"""Alerts API routes"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.alert import Alert
from app.services.auth import require_supabase_token

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/")
def list_alerts(limit: int = 50, unread_only: bool = False, db: Session = Depends(get_db), _token=Depends(require_supabase_token)):
    q = db.query(Alert)
    if unread_only:
        q = q.filter(Alert.acknowledged == False)
    alerts = q.order_by(Alert.created_at.desc()).limit(limit).all()
    return [
        {
            "id": a.id, "type": a.alert_type, "symbol": a.symbol,
            "theme_name": a.theme_name, "title": a.title,
            "message": a.message, "severity": a.severity,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/{alert_id}/ack")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db), _token=Depends(require_supabase_token)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        return {"error": "Alert not found"}
    alert.acknowledged = True
    db.commit()
    return {"status": "ok"}


@router.post("/ack-all")
def acknowledge_all(db: Session = Depends(get_db), _token=Depends(require_supabase_token)):
    db.query(Alert).filter(Alert.acknowledged == False).update({"acknowledged": True})
    db.commit()
    return {"status": "ok"}
