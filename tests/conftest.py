"""Shared test fixtures: temp SQLite DB, client, seeded users."""

import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

# Use a throwaway DB before importing the app.
_tmp_fd, _tmp_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_path}"
os.environ["JWT_SECRET"] = "test-secret-for-hifazat-suite"
os.environ["DEBUG"] = "false"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


def _make_user(email: str, name: str, account_name: str, balance: float) -> dict:
    """Create a user + account and return plain ids (never detached ORM objects)."""
    with SessionLocal() as db:
        user = models.User(email=email, name=name, password_hash=hash_password("password123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        account = models.Account(
            user_id=user.id,
            name=account_name,
            home_city="Karachi",
            home_country="Pakistan",
            balance=balance,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return {
            "user_id": user.id,
            "email": user.email,
            "account_id": account.id,
        }


@pytest.fixture(scope="session")
def demo_user(client):
    """A registered user with one account."""
    return _make_user("owner@test.pk", "Owner", "Main", 100_000.0)


@pytest.fixture(scope="session")
def other_user(client):
    """A second user, used to prove foreign resources return 404."""
    return _make_user("other@test.pk", "Other", "Their account", 50_000.0)


def auth_headers(user: dict) -> dict[str, str]:
    from app.security import create_access_token

    token = create_access_token(user["user_id"])
    return {"Authorization": f"Bearer {token}"}
