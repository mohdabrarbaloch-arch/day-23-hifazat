"""Pydantic schemas (request/response models)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── auth ──────────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    is_demo: bool


class LoginResult(BaseModel):
    token: TokenOut
    created_at: datetime | None = None


# ── accounts ─────────────────────────────────────────────────────────
class AccountIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    account_type: str = Field(default="checking", max_length=40)
    bank: str = Field(default="", max_length=120)
    currency: str = Field(default="PKR", max_length=3, pattern=r"^[A-Z]{3}$")
    home_city: str = Field(default="Karachi", max_length=120)
    home_country: str = Field(default="Pakistan", max_length=120)
    balance: float = Field(default=0.0, ge=-1_000_000_000, le=1_000_000_000)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    account_type: str
    bank: str
    currency: str
    balance: float
    home_city: str
    home_country: str
    created_at: datetime


# ── transactions ──────────────────────────────────────────────────────
class TransactionIn(BaseModel):
    amount: float = Field(gt=0, le=100_000_000)
    category: str = Field(default="other", max_length=60)
    merchant: str = Field(default="", max_length=160)
    city: str = Field(default="", max_length=120)
    country: str = Field(default="", max_length=120)
    channel: str = Field(default="card", max_length=40)
    occurred_at: datetime | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    amount: float
    category: str
    merchant: str
    city: str
    country: str
    channel: str
    occurred_at: datetime
    risk_score: float
    is_flagged: bool
    reasons: list[dict]
    alert_id: int | None


# ── alerts ─────────────────────────────────────────────────────────────
class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    transaction_id: int | None
    severity: str
    score: float
    summary: str
    reasons: list[dict]
    status: str
    outcome: str | None
    created_at: datetime
    updated_at: datetime


class AlertActionIn(BaseModel):
    action: str = Field(pattern=r"^(acknowledge|resolve)$")
    outcome: str | None = Field(default=None, pattern=r"^(false_positive|confirmed_fraud)$")


class AlertStatsOut(BaseModel):
    open: int
    acknowledged: int
    resolved: int
    confirmed_fraud: int
    false_positive: int
    at_risk_amount: float


# ── insights ──────────────────────────────────────────────────────────
class CategorySlice(BaseModel):
    category: str
    total: float
    count: int
    share: float  # 0..1


class InsightOut(BaseModel):
    total_spent: float
    total_spent_prev: float
    change_pct: float
    avg_tx: float
    top_category: str
    expense_ratio: float  # spend/(spend+balance), 0..1
    by_category: list[CategorySlice]
    recurring_merchants: list[dict]
    at_risk_amount: float
    flag_rate: float  # 0..1
