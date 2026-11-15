"""Tests for the seven anomaly rules and the composite scorer."""

from datetime import UTC, datetime, timedelta

import pytest

from app.engine.profiles import Profile
from app.engine.rules import (
    rule_amount_spike,
    rule_geo_travel,
    rule_high_frequency,
    rule_new_payee,
    rule_off_hours,
    rule_rapid_geo,
    rule_velocity,
)
from app.engine.scorer import RAPID_GEO_FLOOR, score_transaction, severity_label
from app.engine.travel import haversine_km, is_rapid_geo_change

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def warm_profile(amount=1000.0, city="Karachi", n=20, gap_h=6):
    p = Profile()
    for i in range(n):
        p.update(
            amount=amount,
            occurred_at=T0 + timedelta(hours=i * gap_h),
            merchant="Imtiaz",
            city=city,
            country="Pakistan",
        )
    return p


def tx(amount=1000.0, city="Karachi", country="Pakistan", merchant="Imtiaz", at=None):
    return {
        "amount": amount,
        "city": city,
        "country": country,
        "merchant": merchant,
        "occurred_at": at or (T0 + timedelta(hours=200)),
    }


# ── travel math ────────────────────────────────────────────────────────
def test_haversine_karachi_lahore():
    km = haversine_km(24.8607, 67.0011, 31.5204, 74.3587)
    assert 1000 < km < 1300  # ~1,100 km


def test_haversine_same_point_is_zero():
    assert haversine_km(24.86, 67.0, 24.86, 67.0) == pytest.approx(0.0, abs=1e-6)


def test_rapid_geo_same_city_never_fires():
    cities = {("Karachi", "Pakistan"): (24.86, 67.0)}
    assert is_rapid_geo_change("Karachi", "Pakistan", "Karachi", "Pakistan", 1.0, cities) is False


def test_rapid_geo_unknown_city_never_accuses():
    cities = {("Karachi", "Pakistan"): (24.86, 67.0)}
    assert is_rapid_geo_change("Karachi", "Pakistan", "Atlantis", "Nowhere", 1.0, cities) is False


# ── individual rules ───────────────────────────────────────────────────
def test_amount_spike_fires_on_huge_amount():
    p = warm_profile(amount=1000.0)
    result = rule_amount_spike(tx(amount=50_000.0), p)
    assert result is not None
    assert result.key == "amount_spike"
    assert 0 < result.severity <= 1


def test_amount_spike_silent_on_normal_amount():
    p = warm_profile(amount=1000.0)
    assert rule_amount_spike(tx(amount=1100.0), p) is None


def test_amount_spike_silent_when_cold():
    p = Profile()  # not warmed
    assert rule_amount_spike(tx(amount=999_999.0), p) is None


def test_rapid_geo_fires_karachi_then_lahore():
    p = warm_profile(city="Karachi")
    # last tx was at T0 + 19*6h; put the new one 2h later in Lahore
    last = p.last_tx_at
    result = rule_rapid_geo(tx(city="Lahore", at=last + timedelta(hours=2)), p)
    assert result is not None
    assert result.key == "rapid_geo"
    assert result.severity >= 0.9


def test_rapid_geo_silent_after_long_gap():
    p = warm_profile(city="Karachi")
    last = p.last_tx_at
    # 48h later is plenty of time to travel
    assert rule_rapid_geo(tx(city="Lahore", at=last + timedelta(hours=48)), p) is None


def test_geo_travel_fires_first_visit_far_city():
    p = warm_profile(city="Karachi")

    class Acct:
        home_city = "Karachi"
        home_country = "Pakistan"

    result = rule_geo_travel(tx(city="Islamabad"), p, account=Acct())
    assert result is not None
    assert result.key == "geo_travel"


def test_geo_travel_silent_for_known_city():
    p = warm_profile(city="Karachi")

    class Acct:
        home_city = "Karachi"
        home_country = "Pakistan"

    assert rule_geo_travel(tx(city="Karachi"), p, account=Acct()) is None


def test_velocity_fires_on_burst():
    p = warm_profile(amount=1000.0, gap_h=6)  # ~4000/day expected
    result = rule_velocity(tx(), p, recent_24h=40_000.0)
    assert result is not None
    assert result.key == "velocity"


def test_velocity_silent_on_normal_day():
    p = warm_profile(amount=1000.0, gap_h=6)
    assert rule_velocity(tx(), p, recent_24h=4000.0) is None


def test_high_frequency_fires_on_burst_gap():
    p = warm_profile(amount=1000.0, gap_h=6)
    last = p.last_tx_at
    result = rule_high_frequency(tx(at=last + timedelta(minutes=20)), p)
    assert result is not None
    assert result.key == "high_frequency"


def test_new_payee_fires_on_first_large_payment():
    p = warm_profile(amount=1000.0)
    result = rule_new_payee(tx(amount=5000.0, merchant="Unknown Corp"), p)
    assert result is not None
    assert result.key == "new_payee"


def test_new_payee_silent_for_known_merchant():
    p = warm_profile(amount=1000.0)
    assert rule_new_payee(tx(amount=5000.0, merchant="Imtiaz"), p) is None


def test_off_hours_fires_at_2am():
    p = warm_profile(amount=1000.0)
    at = (T0 + timedelta(hours=200)).replace(hour=2, minute=0)
    result = rule_off_hours(tx(amount=3000.0, at=at), p)
    assert result is not None
    assert result.key == "off_hours"


def test_off_hours_silent_at_noon():
    p = warm_profile(amount=1000.0)
    at = (T0 + timedelta(hours=200)).replace(hour=12, minute=0)
    assert rule_off_hours(tx(amount=3000.0, at=at), p) is None


# ── scorer ─────────────────────────────────────────────────────────────
def test_scorer_clean_transaction_not_flagged():
    p = warm_profile(amount=1000.0)
    result = score_transaction(tx(amount=1050.0), p, threshold=40)
    assert result.flagged is False
    assert result.score < 40


def test_scorer_impossible_travel_has_hard_floor():
    p = warm_profile(city="Karachi")
    last = p.last_tx_at
    result = score_transaction(tx(city="Lahore", at=last + timedelta(hours=1)), p, threshold=40)
    assert result.flagged is True
    assert result.score >= RAPID_GEO_FLOOR


def test_scorer_reasons_are_serialisable_and_weighted():
    p = warm_profile(amount=1000.0)
    result = score_transaction(tx(amount=80_000.0, merchant="New Co"), p, threshold=40)
    assert result.reasons
    for reason in result.reasons:
        assert set(reason) == {"key", "label", "severity", "detail", "weight"}
        assert 0 <= reason["severity"] <= 1
        assert reason["weight"] > 0


def test_scorer_at_risk_amount_only_when_flagged():
    p = warm_profile(amount=1000.0)
    clean = score_transaction(tx(amount=1000.0), p, threshold=40)
    assert clean.at_risk_amount == 0.0
    flagged = score_transaction(tx(amount=90_000.0, merchant="New Co"), p, threshold=40)
    assert flagged.at_risk_amount == 90_000.0


def test_severity_labels_band_correctly():
    assert severity_label(0.95) == "critical"
    assert severity_label(0.80) == "high"
    assert severity_label(0.65) == "medium"
    assert severity_label(0.30) == "low"
