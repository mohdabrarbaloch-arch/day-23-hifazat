"""Authentication router."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..limiter import limiter
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

rate_limiter: Limiter = limiter

CurrentUser = Annotated[models.User, Depends(get_current_user)]


@router.post("/register", response_model=schemas.TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)) -> schemas.TokenOut:
    email = payload.email.lower().strip()
    existing = db.scalar(select(models.User).where(models.User.email == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = models.User(
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return schemas.TokenOut(
        access_token=create_access_token(user.id),
        user=schemas.UserOut.model_validate(user),
    )


@router.post("/login", response_model=schemas.LoginResult)
@limiter.limit("10/minute")
def login(
    request: Request, payload: schemas.LoginIn, db: Session = Depends(get_db)
) -> schemas.LoginResult:
    user = db.scalar(select(models.User).where(models.User.email == payload.email.lower().strip()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return schemas.LoginResult(
        token=schemas.TokenOut(
            access_token=create_access_token(user.id),
            user=schemas.UserOut.model_validate(user),
        )
    )


@router.get("/me", response_model=schemas.UserOut)
def me(user: CurrentUser = None) -> schemas.UserOut:
    return schemas.UserOut.model_validate(user)
