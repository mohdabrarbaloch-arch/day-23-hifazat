"""SQLAlchemy models for Hifazat."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    accounts: Mapped[list["Account"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[str] = mapped_column(String(40), default="checking")
    bank: Mapped[str] = mapped_column(String(120), default="")
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    home_city: Mapped[str] = mapped_column(String(120), default="Karachi")
    home_country: Mapped[str] = mapped_column(String(120), default="Pakistan")

    # ── online profile (anomaly engine state) ─────────────────────────
    ema_amount: Mapped[float] = mapped_column(Float, default=0.0)
    ema_mad: Mapped[float] = mapped_column(Float, default=0.0)
    ema_gap_h: Mapped[float] = mapped_column(Float, default=0.0)
    tx_count: Mapped[int] = mapped_column(Integer, default=0)
    last_tx_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    seen_cities: Mapped[dict] = mapped_column(JSON, default=dict)
    seen_merchants: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped[User] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="other")
    merchant: Mapped[str] = mapped_column(String(160), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    country: Mapped[str] = mapped_column(String(120), default="")
    channel: Mapped[str] = mapped_column(String(40), default="card")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # engine outputs
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)

    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)

    account: Mapped[Account] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("ix_tx_user_time", "account_id", "occurred_at"),  # type: ignore[arg-type]
    )


class Alert(Base):
    __tablename__ = "alerts"

    STATUSES = ("open", "acknowledged", "resolved")
    OUTCOMES = ("false_positive", "confirmed_fraud")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True, nullable=False)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="low")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(String(500), default="")
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    transaction: Mapped[Transaction | None] = relationship(
        foreign_keys=[transaction_id], uselist=False
    )
    account: Mapped[Account] = relationship(foreign_keys=[account_id])

    __table_args__ = (
        UniqueConstraint("transaction_id", name="uq_alert_tx"),
        Index("ix_alerts_user_status", "user_id", "status"),
    )
