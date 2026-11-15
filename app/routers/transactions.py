"""Transactions router — the anomaly engine entry point.

Each transaction is scored against the account's online profile, the profile
is updated in the same DB transaction, and flagged transactions raise an alert
and are pushed in real time over the WebSocket hub.
"""

from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, get_owned_account_or_404
from ..engine.profiles import apply_profile, as_aware_utc, profile_from_row
from ..engine.scorer import score_transaction, severity_label
from ..engine.ws_hub import hub

router = APIRouter(prefix="/api", tags=["transactions"])

CurrentUser = Annotated[models.User, Depends(get_current_user)]


def _alert_summary(score: float, reasons: list[dict]) -> str:
    """Lead the alert with the reason a human should act on first.

    Reasons arrive in rule order, and a large amount usually fires before the
    thing that actually explains the alert. A big spend is alarming; the same
    card being used in two cities an hour apart is evidence. So impossible
    travel leads whenever it is present, and otherwise we rank by
    weight x severity.
    """
    if not reasons:
        return f"Risk score {score:.0f}/100 with no specific rule match"

    for reason in reasons:
        if reason.get("key") == "rapid_geo":
            return f"{reason['label']} — {reason['detail']}"

    ranked = sorted(
        reasons,
        key=lambda r: r.get("weight", 0) * r.get("severity", 0),
        reverse=True,
    )
    top = ranked[0]
    return f"{top['label']} — {top['detail']}"


def process_transaction(
    db: Session,
    account: models.Account,
    tx_data: dict,
) -> tuple[models.Transaction, models.Alert | None]:
    """Score a transaction, persist it plus profile+alert atomically.

    Returns (transaction, alert_or_none).
    """
    profile = profile_from_row(account)
    occurred_at = as_aware_utc(tx_data["occurred_at"])

    # Rolling 24h spend (for the velocity rule), computed before insert.
    since = occurred_at
    from datetime import timedelta

    window_start = since - timedelta(hours=24)
    row = db.execute(
        select(func.coalesce(func.sum(models.Transaction.amount), 0.0)).where(
            models.Transaction.account_id == account.id,
            models.Transaction.occurred_at >= window_start,
        )
    ).scalar_one()
    recent_24h = float(row or 0.0)

    tx = models.Transaction(account_id=account.id, **tx_data)

    result = score_transaction(
        {
            "amount": tx.amount,
            "merchant": tx.merchant,
            "city": tx.city,
            "country": tx.country,
            "occurred_at": occurred_at,
        },
        profile,
        threshold=float(get_settings().risk_threshold),
        recent_24h=recent_24h,
        account=account,
    )

    tx.risk_score = result.score
    tx.is_flagged = result.flagged
    tx.reasons = result.reasons

    db.add(tx)
    db.flush()  # give tx.id to the alert

    alert = None
    if result.flagged:
        alert = models.Alert(
            user_id=account.user_id,
            account_id=account.id,
            transaction_id=tx.id,
            severity=severity_label(result.score / 100.0),
            score=result.score,
            summary=_alert_summary(result.score, result.reasons),
            reasons=result.reasons,
        )
        db.add(alert)
        db.flush()
        tx.alert_id = alert.id

    # Update the online profile with this transaction.
    profile.update(
        amount=tx.amount,
        occurred_at=occurred_at,
        merchant=tx.merchant,
        city=tx.city,
        country=tx.country,
    )
    apply_profile(account, profile)
    account.balance -= tx.amount  # spends reduce the balance

    db.commit()
    db.refresh(tx)
    if alert is not None:
        db.refresh(alert)

    if alert is not None:
        hub.publish(
            account.user_id,
            {
                "type": "new_alert",
                "alert": {
                    "id": alert.id,
                    "account_id": alert.account_id,
                    "severity": alert.severity,
                    "score": alert.score,
                    "summary": alert.summary,
                    "reasons": alert.reasons,
                    "status": alert.status,
                    "created_at": alert.created_at.isoformat(),
                },
            },
        )

    return tx, alert


@router.post(
    "/accounts/{account_id}/transactions",
    response_model=schemas.TransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    account_id: int,
    payload: schemas.TransactionIn,
    db: Session = Depends(get_db),
    user: CurrentUser = None,
) -> models.Transaction:
    account = get_owned_account_or_404(db, account_id, user)
    data = payload.model_dump()
    if data.get("occurred_at") is None:
        from datetime import datetime

        data["occurred_at"] = datetime.now(UTC)
    tx, _ = process_transaction(db, account, data)
    return tx


@router.get("/accounts/{account_id}/transactions", response_model=list[schemas.TransactionOut])
def list_transactions(
    account_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: CurrentUser = None,
) -> list[models.Transaction]:
    account = get_owned_account_or_404(db, account_id, user)
    rows = (
        db.query(models.Transaction)
        .filter(models.Transaction.account_id == account.id)
        .order_by(models.Transaction.occurred_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows


@router.get("/transactions", response_model=list[schemas.TransactionOut])
def list_all_user_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: CurrentUser = None,
) -> list[models.Transaction]:
    account_ids = [
        aid
        for (aid,) in db.query(models.Account.id).filter(models.Account.user_id == user.id).all()
    ]
    if not account_ids:
        return []
    rows = (
        db.query(models.Transaction)
        .filter(models.Transaction.account_id.in_(account_ids))
        .order_by(models.Transaction.occurred_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows
