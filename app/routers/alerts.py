"""Alerts router — list, act, stats."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

CurrentUser = Annotated[models.User, Depends(get_current_user)]


def _get_owned_alert_or_404(db: Session, alert_id: int, user: models.User) -> models.Alert:
    """404 for foreign alerts — no existence leak, consistent with accounts."""
    alert = db.get(models.Alert, alert_id)
    if alert is None or alert.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.get("", response_model=list[schemas.AlertOut])
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: CurrentUser = None,
) -> list[models.Alert]:
    query = db.query(models.Alert).filter(models.Alert.user_id == user.id)
    if status_filter in models.Alert.STATUSES:
        query = query.filter(models.Alert.status == status_filter)
    rows = query.order_by(models.Alert.created_at.desc()).offset(offset).limit(limit).all()
    return rows


@router.get("/stats", response_model=schemas.AlertStatsOut)
def alert_stats(db: Session = Depends(get_db), user: CurrentUser = None) -> schemas.AlertStatsOut:
    rows = (
        db.query(models.Alert.status, models.Alert.outcome, func.count(models.Alert.id))
        .filter(models.Alert.user_id == user.id)
        .group_by(models.Alert.status, models.Alert.outcome)
        .all()
    )
    counts = {"open": 0, "acknowledged": 0, "resolved": 0}
    confirmed = false_pos = 0
    for status_, outcome, count in rows:
        if status_ in counts:
            counts[status_] = count
        if status_ == "resolved" and outcome == "confirmed_fraud":
            confirmed = count
        if status_ == "resolved" and outcome == "false_positive":
            false_pos = count
    # At-risk amount = sum of flagged amounts on unresolved open/acknowledged alerts.
    at_risk = (
        db.query(func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .join(models.Alert, models.Alert.transaction_id == models.Transaction.id)
        .filter(
            models.Alert.user_id == user.id,
            models.Alert.status.in_(["open", "acknowledged"]),
        )
        .scalar()
    )
    return schemas.AlertStatsOut(
        open=counts["open"],
        acknowledged=counts["acknowledged"],
        resolved=counts["resolved"],
        confirmed_fraud=confirmed,
        false_positive=false_pos,
        at_risk_amount=float(at_risk or 0.0),
    )


@router.post("/{alert_id}/action", response_model=schemas.AlertOut)
def alert_action(
    alert_id: int,
    payload: schemas.AlertActionIn,
    db: Session = Depends(get_db),
    user: CurrentUser = None,
) -> models.Alert:
    alert = _get_owned_alert_or_404(db, alert_id, user)

    if payload.action == "acknowledge":
        if alert.status == "open":
            alert.status = "acknowledged"
        # acknowledging twice is a no-op, not an error
    elif payload.action == "resolve":
        if payload.outcome is None:
            raise HTTPException(status_code=400, detail="outcome is required for resolve")
        alert.status = "resolved"
        alert.outcome = payload.outcome

    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert
