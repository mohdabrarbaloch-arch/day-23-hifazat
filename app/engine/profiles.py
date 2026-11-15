"""Online per-account spending profiles.

The profile is a small set of exponentially-weighted statistics updated with
every transaction inside the same DB transaction as the transaction insert, so
concurrent requests never race on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# Smoothing factors. alpha=0.15 weights recent observations ~3x more than
# observations ~20 transactions back; a good middle ground for personal
# spending where habits drift over weeks, not days.
ALPHA = 0.15

# Gate: amount stats only start to mean something after this many
# transactions. Below it, mean-based rules stay silent.
MIN_SAMPLES = 5


@dataclass
class Profile:
    """Mutable online stats for one account."""

    ema_amount: float = 0.0
    ema_mad: float = 0.0
    ema_gap_h: float = 0.0
    tx_count: int = 0
    last_tx_at: datetime | None = None
    last_city: str | None = None
    last_country: str | None = None
    last_amount: float | None = None
    seen_cities: dict[str, int] = field(default_factory=dict)
    seen_merchants: dict[str, int] = field(default_factory=dict)

    @property
    def warmed(self) -> bool:
        """True once amount stats are trustworthy."""
        return self.tx_count >= MIN_SAMPLES

    def mean(self) -> float:
        return self.ema_amount

    def mad(self) -> float:
        return self.ema_mad

    def expected_gap_hours(self) -> float:
        return self.ema_gap_h

    def update(
        self,
        *,
        amount: float,
        occurred_at: datetime,
        merchant: str,
        city: str,
        country: str,
    ) -> None:
        """Fold one transaction into the profile (pure math, no DB)."""
        # Amount + MAD, robust scale via mean absolute deviation.
        if self.tx_count == 0:
            self.ema_amount = amount
            self.ema_mad = 0.0
        else:
            diff = abs(amount - self.ema_amount)
            self.ema_mad = (1 - ALPHA) * self.ema_mad + ALPHA * diff
            self.ema_amount = (1 - ALPHA) * self.ema_amount + ALPHA * amount

        # Cadence gap in hours (datetime-aware).
        if self.last_tx_at is not None:
            last = as_aware_utc(self.last_tx_at)
            current = as_aware_utc(occurred_at)
            gap_h = (current - last).total_seconds() / 3600.0
            if self.tx_count <= 1:
                self.ema_gap_h = gap_h
            else:
                self.ema_gap_h = (1 - ALPHA) * self.ema_gap_h + ALPHA * gap_h

        self.tx_count += 1
        self.last_tx_at = occurred_at
        self.last_city = city
        self.last_country = country
        self.last_amount = amount
        self.seen_cities[city] = self.seen_cities.get(city, 0) + 1
        key = merchant or "(unknown)"
        self.seen_merchants[key] = self.seen_merchants.get(key, 0) + 1

    def to_row_values(self) -> dict:
        """Values to persist back onto the account row."""
        return {
            "ema_amount": self.ema_amount,
            "ema_mad": self.ema_mad,
            "ema_gap_h": self.ema_gap_h,
            "tx_count": self.tx_count,
            "last_tx_at": self.last_tx_at,
            "last_city": self.last_city,
            "last_country": self.last_country,
            "last_amount": self.last_amount,
            "seen_cities": self.seen_cities,
            "seen_merchants": self.seen_merchants,
        }


def as_aware_utc(value: datetime | None) -> datetime | None:
    """Coerce a datetime to timezone-aware UTC.

    SQLite drops tzinfo on round-trip, so a value read back from the DB is
    naive even though it was stored as UTC. Every subtraction in the engine
    must be aware-vs-aware, so we normalise at the boundary.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def profile_from_row(account) -> Profile:
    """Hydrate a Profile from an ORM Account row."""
    return Profile(
        ema_amount=account.ema_amount,
        ema_mad=account.ema_mad,
        ema_gap_h=account.ema_gap_h,
        tx_count=account.tx_count,
        last_tx_at=as_aware_utc(account.last_tx_at),
        last_city=account.last_city,
        last_country=account.last_country,
        last_amount=account.last_amount,
        seen_cities=dict(account.seen_cities or {}),
        seen_merchants=dict(account.seen_merchants or {}),
    )


def apply_profile(account, profile: Profile) -> None:
    """Persist a Profile back onto an ORM Account row."""
    for key, value in profile.to_row_values().items():
        setattr(account, key, value)


def now_utc() -> datetime:
    return datetime.now(UTC)
