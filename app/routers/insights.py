"""Insights router — spending analytics over the user's accounts."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/insights", tags=["insights"])

CurrentUser = Annotated[models.User, Depends(get_current_user)]


@router.get("", response_model=schemas.InsightOut)
def insights(db: Session = Depends(get_db), user: CurrentUser = None) -> schemas.InsightOut:
    account_ids = [
        aid
        for (aid,) in db.query(models.Account.id).filter(models.Account.user_id == user.id).all()
    ]
    if not account_ids:
        return schemas.InsightOut(
            total_spent=0,
            total_spent_prev=0,
            change_pct=0,
            avg_tx=0,
            top_category="",
            expense_ratio=0,
            by_category=[],
            recurring_merchants=[],
            at_risk_amount=0,
            flag_rate=0,
        )

    now = datetime.now(UTC)
    this_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    prev_start = this_start - timedelta(days=7)
    week_ago = this_start - timedelta(days=7)

    base = db.query(models.Transaction).filter(models.Transaction.account_id.in_(account_ids))

    this_week_spend = (
        base.filter(models.Transaction.occurred_at >= this_start)
        .with_entities(func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .scalar()
    )
    prev_week_spend = (
        base.filter(
            models.Transaction.occurred_at >= prev_start,
            models.Transaction.occurred_at < this_start,
        )
        .with_entities(func.coalesce(func.sum(models.Transaction.amount), 0.0))
        .scalar()
    )
    total_spent = float(this_week_spend or 0)
    prev_spent = float(prev_week_spend or 0)
    change_pct = 0.0
    if prev_spent > 0:
        change_pct = round(((total_spent - prev_spent) / prev_spent) * 100.0, 1)

    avg_tx = base.with_entities(func.coalesce(func.avg(models.Transaction.amount), 0.0)).scalar()

    # Category breakdown (current week).
    cat_rows = (
        base.filter(models.Transaction.occurred_at >= week_ago)
        .with_entities(
            models.Transaction.category,
            func.sum(models.Transaction.amount),
            func.count(models.Transaction.id),
        )
        .group_by(models.Transaction.category)
        .all()
    )
    by_category = [
        schemas.CategorySlice(category=c, total=float(t or 0), count=int(n or 0), share=0.0)
        for c, t, n in cat_rows
    ]
    cat_total = sum(s.total for s in by_category)
    for s in by_category:
        s.share = round(s.total / cat_total, 3) if cat_total else 0.0
    by_category.sort(key=lambda s: s.total, reverse=True)
    top_category = by_category[0].category if by_category else ""

    # Recurring merchants: 3+ transactions with a stable-ish amount in the profile,
    # in at least 2 distinct days over the visible history.
    limit = 500
    merchant_rows = base.order_by(models.Transaction.occurred_at.desc()).limit(limit).all()
    from collections import defaultdict

    by_merchant: dict[str, list] = defaultdict(list)
    for txn in merchant_rows:
        if txn.merchant:
            by_merchant[txn.merchant].append(txn)
    recurring: list[dict] = []
    for merchant, txns in by_merchant.items():
        if len(txns) < 3:
            continue
        days = {t.occurred_at.date() for t in txns}
        if len(days) < 2:
            continue
        amounts = [t.amount for t in txns]
        avg = sum(amounts) / len(amounts)
        recurring.append(
            {
                "merchant": merchant,
                "count": len(txns),
                "avg_amount": round(avg, 2),
                "last": txns[0].occurred_at.isoformat(),
            }
        )
    recurring.sort(key=lambda r: r["count"], reverse=True)

    # Balances → expense ratio for one representative account.
    account = db.query(models.Account).filter(models.Account.user_id == user.id).first()
    expense_ratio = 0.0
    if account and account.balance > 0:
        expense_ratio = round(total_spent / (total_spent + account.balance), 3)

    # Flag rate over visible history.
    total_n = base.with_entities(func.count(models.Transaction.id)).scalar()
    flagged_n = (
        base.filter(models.Transaction.is_flagged.is_(True))
        .with_entities(func.count(models.Transaction.id))
        .scalar()
    )
    flag_rate = round(flagged_n / total_n, 3) if total_n else 0.0

    return schemas.InsightOut(
        total_spent=round(total_spent, 2),
        total_spent_prev=round(prev_spent, 2),
        change_pct=change_pct,
        avg_tx=round(float(avg_tx or 0), 2),
        top_category=top_category,
        expense_ratio=expense_ratio,
        by_category=by_category,
        recurring_merchants=recurring[:8],
        at_risk_amount=0.0,  # populated from alerts stats endpoint
        flag_rate=flag_rate,
    )
