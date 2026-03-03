"""
Public Routes — no authentication required.

GET /api/public/stats  → aggregate performance stats for the public homepage
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from app.database import get_db
from app.models.position import Position, PositionStatus

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/stats")
def get_public_stats(db: Session = Depends(get_db)):
    """Aggregate performance stats — safe to expose publicly."""
    all_pos = db.query(Position).all()
    open_pos = [p for p in all_pos if p.status == PositionStatus.OPEN]
    closed = [p for p in all_pos if p.status in (
        PositionStatus.CLOSED, PositionStatus.STOPPED_OUT
    )]

    # Win rate
    pnl_pcts: list[float] = []
    for p in closed:
        if p.cost_basis and float(p.cost_basis) > 0:
            pnl_pcts.append(float(p.realized_pnl or 0) / float(p.cost_basis) * 100)

    total = len(pnl_pcts)
    wins = [x for x in pnl_pcts if x > 0]
    win_rate = round(len(wins) / total * 100, 1) if total else 0.0

    # Average hold days
    hold_days: list[float] = []
    for p in closed:
        if p.opened_at and p.closed_at:
            opened = p.opened_at if p.opened_at.tzinfo else p.opened_at.replace(tzinfo=timezone.utc)
            closed_at = p.closed_at if p.closed_at.tzinfo else p.closed_at.replace(tzinfo=timezone.utc)
            hold_days.append((closed_at - opened).total_seconds() / 86400)
    avg_hold = round(sum(hold_days) / len(hold_days), 1) if hold_days else 0.0

    # Total realized P&L as a percentage of total cost basis
    total_pnl = sum(float(p.realized_pnl or 0) for p in closed)
    total_cost = sum(float(p.cost_basis or 0) for p in closed if p.cost_basis)
    total_pnl_pct = round(total_pnl / total_cost * 100, 1) if total_cost > 0 else 0.0

    # System status: check kill switch
    from app.services import kill_switch
    system_status = "paused" if kill_switch.is_paused() else "running"

    return {
        "total_closed_trades": total,
        "win_rate_pct": win_rate,
        "avg_hold_days": avg_hold,
        "total_realized_pnl_pct": total_pnl_pct,
        "open_positions": len(open_pos),
        "system_status": system_status,
    }
