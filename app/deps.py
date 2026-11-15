"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal, get_db
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


async def decode_user_from_ws(websocket) -> models.User | None:
    """Authenticate a WebSocket via ?token= query param (browsers cannot set headers on WS).

    Reads the token, resolves the user; returns None when invalid.
    """
    token = websocket.query_params.get("token")
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        return None
    with SessionLocal() as db:
        return db.get(models.User, user_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_owned_account_or_404(db: Session, account_id: int, user: models.User) -> models.Account:
    """Return the account only if it belongs to the user; 404 otherwise.

    Using 404 (not 403) on foreign resources avoids leaking that the
    resource exists.
    """
    account = db.get(models.Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account
