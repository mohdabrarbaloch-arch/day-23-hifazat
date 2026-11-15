"""Account management router."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user, get_owned_account_or_404

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

CurrentUser = Annotated[models.User, Depends(get_current_user)]


@router.get("", response_model=list[schemas.AccountOut])
def list_accounts(db: Session = Depends(get_db), user: CurrentUser = None) -> list[models.Account]:
    accounts = (
        db.query(models.Account)
        .filter(models.Account.user_id == user.id)
        .order_by(models.Account.id)
        .all()
    )
    return accounts


@router.post("", response_model=schemas.AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: schemas.AccountIn,
    db: Session = Depends(get_db),
    user: CurrentUser = None,
) -> models.Account:
    if db.query(models.Account).filter(models.Account.user_id == user.id).count() >= 6:
        raise HTTPException(status_code=400, detail="Account limit reached (6)")
    account = models.Account(user_id=user.id, **payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/{account_id}", response_model=schemas.AccountOut)
def get_account(
    account_id: int, db: Session = Depends(get_db), user: CurrentUser = None
) -> models.Account:
    return get_owned_account_or_404(db, account_id, user)
