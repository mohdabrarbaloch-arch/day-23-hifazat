"""Seven deterministic anomaly rules.

Each rule is a pure function of (transaction, profile, account context) and
returns a severity in [0, 1]. The scorer weighs them into a composite score.
Rule outputs are also serialised into the alert's `reasons` so the user sees
exactly what fired.
"""

from __future__ import annotations

from dataclasses import dataclass

from .profiles import Profile, as_aware_utc
from .travel import is_rapid_geo_change, lookup_city

# Cities with known coordinates used for geo reasoning (name, country) -> (lat, lon).
PK_CITIES: dict[tuple[str, str], tuple[float, float]] = {
    ("Karachi", "Pakistan"): (24.8607, 67.0011),
    ("Lahore", "Pakistan"): (31.5204, 74.3587),
    ("Islamabad", "Pakistan"): (33.6844, 73.0479),
    ("Rawalpindi", "Pakistan"): (33.5651, 73.0169),
    ("Peshawar", "Pakistan"): (34.0151, 71.5249),
    ("Quetta", "Pakistan"): (30.1798, 66.9750),
    ("Multan", "Pakistan"): (30.1575, 71.5249),
    ("Faisalabad", "Pakistan"): (31.4504, 73.1350),
    ("Hyderabad", "Pakistan"): (25.3960, 68.3578),
    ("Sialkot", "Pakistan"): (32.4945, 74.5229),
}

# A few international anchors for travel-rule tests.
WORLD_CITIES: dict[tuple[str, str], tuple[float, float]] = {
    ("Dubai", "UAE"): (25.2048, 55.2708),
    ("London", "UK"): (51.5074, -0.1278),
    ("New York", "US"): (40.7128, -74.0060),
    ("Istanbul", "Turkey"): (41.0082, 28.9784),
}

CITIES: dict[tuple[str, str], tuple[float, float]] = {**PK_CITIES, **WORLD_CITIES}


@dataclass
class RuleResult:
    """Output of one rule evaluation."""

    key: str
    label: str
    severity: float  # 0..1
    detail: str


def rule_amount_spike(tx: dict, profile: Profile) -> RuleResult | None:
    """Amount far above the profile's robust scale."""
    if not profile.warmed:
        return None
    amount = tx["amount"]
    mean = profile.mean()
    if mean <= 0:
        return None
    # A perfectly uniform history gives MAD = 0, which would make every
    # deviation infinitely anomalous. Fall back to a 10% band so the rule
    # still needs a genuinely large jump.
    mad = profile.mad() if profile.mad() > 0 else mean * 0.10
    if amount > mean + 8 * mad and amount >= 3 * mean:
        severity = min(1.0, 0.35 + 0.65 * ((amount - mean) / (4 * mean)))
        return RuleResult(
            key="amount_spike",
            label="Unusual amount",
            severity=severity,
            detail=(
                f"Rs {amount:,.0f} vs your usual ~Rs {mean:,.0f} "
                f"(mean absolute deviation Rs {mad:,.0f})"
            ),
        )
    return None


def rule_rapid_geo(tx: dict, profile: Profile) -> RuleResult | None:
    """Two far-apart cities within hours — impossible travel for a human.

    Hard floor: when proven, this never scores below 0.82.
    """
    if profile.last_tx_at is None or not profile.last_city or not tx.get("city"):
        return None
    hours = (
        as_aware_utc(tx["occurred_at"]) - as_aware_utc(profile.last_tx_at)
    ).total_seconds() / 3600.0
    if is_rapid_geo_change(
        profile.last_city,
        profile.last_country or "",
        tx.get("city", ""),
        tx.get("country", ""),
        hours,
        CITIES,
    ):
        return RuleResult(
            key="rapid_geo",
            label="Impossible travel",
            severity=0.95,
            detail=(
                f"Transaction in {tx['city']} only {hours:.1f}h after a "
                f"transaction in {profile.last_city} ({max(hours, 0.1):.0f}h gap)"
            ),
        )
    return None


def rule_geo_travel(tx: dict, profile: Profile, account=None) -> RuleResult | None:
    """First-ever visit to a far-from-home city."""
    if not profile.warmed:
        return None
    city = tx.get("city", "")
    country = tx.get("country", "")
    if not city:
        return None
    if profile.seen_cities.get(city, 0) > 0:
        return None
    home = (account.home_city if account is not None else None) or "Karachi"
    home_c = (account.home_country if account is not None else None) or "Pakistan"
    coord_city = lookup_city(city, country, CITIES)
    coord_home = lookup_city(home, home_c, CITIES)
    if coord_city is None or coord_home is None:
        return None
    from .travel import haversine_km

    km = haversine_km(*coord_city, *coord_home)
    if km < 1000:
        return None
    severity = min(1.0, 0.35 + 0.5 * (km / 6000.0))
    return RuleResult(
        key="geo_travel",
        label="Unexpected travel",
        severity=severity,
        detail=f"First transaction ever in {city} ({km:,.0f} km from {home})",
    )


def rule_velocity(tx: dict, profile: Profile, recent_24h: float | None = None) -> RuleResult | None:
    """Spend within the last 24h crossing 4x the expected daily volume."""
    if not profile.warmed or profile.mean() <= 0:
        return None
    expected_daily = profile.mean() * (24.0 / max(profile.expected_gap_hours(), 0.5))
    if recent_24h is None:
        return None
    if expected_daily <= 0:
        return None
    ratio = recent_24h / expected_daily
    if ratio >= 4.0:
        severity = min(1.0, 0.3 + 0.7 * ((ratio - 4.0) / 8.0))
        return RuleResult(
            key="velocity",
            label="Spending burst",
            severity=severity,
            detail=(
                f"Rs {recent_24h:,.0f} in the last 24h vs an expected ~Rs {expected_daily:,.0f}/day"
            ),
        )
    return None


def rule_high_frequency(tx: dict, profile: Profile) -> RuleResult | None:
    """A burst of transactions much faster than this account's cadence."""
    if profile.tx_count < 2 or profile.last_tx_at is None:
        return None
    gap_h = (
        as_aware_utc(tx["occurred_at"]) - as_aware_utc(profile.last_tx_at)
    ).total_seconds() / 3600.0
    expected = profile.expected_gap_hours()
    if expected <= 0 or gap_h <= 0 or gap_h > 2:
        return None
    ratio = expected / gap_h
    if ratio >= 3.0:
        severity = min(1.0, 0.3 + 0.7 * ((ratio - 3.0) / 10.0))
        return RuleResult(
            key="high_frequency",
            label="Unusual frequency",
            severity=severity,
            detail=(
                f"This is {ratio:.0f}x faster than the account's usual "
                f"one transaction every {expected:.1f}h"
            ),
        )
    return None


def rule_new_payee(tx: dict, profile: Profile) -> RuleResult | None:
    """First-ever merchant with a large amount."""
    if not profile.warmed:
        return None
    merchant = tx.get("merchant", "").strip()
    if not merchant:
        return None
    if profile.seen_merchants.get(merchant, 0) > 0:
        return None
    mean = profile.mean()
    if mean <= 0 or tx["amount"] < 2 * mean:
        return None
    severity = min(1.0, 0.3 + 0.6 * (tx["amount"] / (8 * mean)))
    return RuleResult(
        key="new_payee",
        label="New payee, large amount",
        severity=severity,
        detail=f"First-ever payment to {merchant} for Rs {tx['amount']:,.0f}",
    )


def rule_off_hours(tx: dict, profile: Profile) -> RuleResult | None:
    """00:00–05:00 spend above 1.5x the mean — common cash-out window."""
    if not profile.warmed:
        return None
    hour = tx["occurred_at"].hour
    if hour >= 5:  # 00:00..04:59
        return None
    mean = profile.mean()
    if mean <= 0 or tx["amount"] < 1.5 * mean:
        return None
    severity = min(1.0, 0.25 + 0.5 * (tx["amount"] / (6 * mean)))
    return RuleResult(
        key="off_hours",
        label="Late-night spend",
        severity=severity,
        detail=f"Transaction at {hour:02d}:00 local time, amount above the usual mean",
    )
