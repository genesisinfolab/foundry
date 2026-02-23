"""Positions API routes"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.position import Position, PositionStatus
from app.services.risk_manager import RiskManager
from app.services.trade_executor import TradeExecutor

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("/")
def list_positions(status: str = "open", db: Session = Depends(get_db)):
    q = db.query(Position)
    if status == "open":
        q = q.filter(Position.status == PositionStatus.OPEN)
    elif status == "closed":
        q = q.filter(Position.status.in_([PositionStatus.CLOSED, PositionStatus.STOPPED_OUT]))
    positions = q.order_by(Position.opened_at.desc()).all()
    return [
        {
            "id": p.id, "symbol": p.symbol, "theme_id": p.theme_id,
            "status": p.status, "qty": p.qty,
            "avg_entry_price": p.avg_entry_price, "current_price": p.current_price,
            "market_value": p.market_value,
            "unrealized_pnl": p.unrealized_pnl, "unrealized_pnl_pct": p.unrealized_pnl_pct,
            "realized_pnl": p.realized_pnl,
            "pyramid_level": p.pyramid_level, "stop_loss_price": p.stop_loss_price,
            "opened_at": p.opened_at.isoformat() if p.opened_at else None,
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
            "actions": [
                {"type": a.action_type, "qty": a.qty, "price": a.price,
                 "reason": a.reason, "at": a.created_at.isoformat()}
                for a in p.actions
            ],
        }
        for p in positions
    ]


@router.get("/summary")
def portfolio_summary(db: Session = Depends(get_db)):
    rm = RiskManager()
    return rm.get_portfolio_summary(db)


@router.post("/check-risk")
def check_risk(db: Session = Depends(get_db)):
    rm = RiskManager()
    actions = rm.check_all_positions(db)
    return {"status": "ok", "actions_taken": actions}
