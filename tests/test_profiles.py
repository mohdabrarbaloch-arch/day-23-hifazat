"""Tests for the online spending profile."""

from datetime import UTC, datetime, timedelta

import pytest

from app.engine.profiles import MIN_SAMPLES, Profile


@pytest.fixture
def t0():
    return datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def test_fresh_profile_is_not_warmed(t0):
    p = Profile()
    assert p.warmed is False


def test_warms_after_min_samples(t0):
    p = Profile()
    for i in range(MIN_SAMPLES):
        p.update(
            amount=100 + i,
            occurred_at=t0 + timedelta(hours=i),
            merchant="m",
            city="Karachi",
            country="Pakistan",
        )
    assert p.warmed is True


def test_first_amount_seeds_ema(t0):
    p = Profile()
    p.update(amount=500, occurred_at=t0, merchant="m", city="Karachi", country="Pakistan")
    assert p.ema_amount == 500
    assert p.tx_count == 1


def test_ema_converges_toward_latest_values(t0):
    p = Profile()
    for i in range(200):
        p.update(
            amount=100.0,
            occurred_at=t0 + timedelta(hours=i),
            merchant="m",
            city="Karachi",
            country="Pakistan",
        )
    # 200 identical observations pull the EMA to ~100
    assert p.ema_amount == pytest.approx(100.0, abs=0.6)


def test_mad_reacts_to_outlier(t0):
    p = Profile()
    for i in range(20):
        p.update(
            amount=100.0,
            occurred_at=t0 + timedelta(hours=i),
            merchant="m",
            city="Karachi",
            country="Pakistan",
        )
    before = p.ema_mad
    p.update(
        amount=5000.0,
        occurred_at=t0 + timedelta(hours=21),
        merchant="m",
        city="Karachi",
        country="Pakistan",
    )
    assert p.ema_mad > before


def test_gap_ema_tracks_cadence(t0):
    p = Profile()
    for i in range(6):
        p.update(
            amount=50.0,
            occurred_at=t0 + timedelta(hours=i * 3),
            merchant="m",
            city="Karachi",
            country="Pakistan",
        )
    # gaps are 3h; EMA of gaps should be ~3
    assert p.ema_gap_h == pytest.approx(3.0, abs=0.5)


def test_seen_cities_and_merchants_count(t0):
    p = Profile()
    p.update(amount=10, occurred_at=t0, merchant="Imtiaz", city="Karachi", country="Pakistan")
    p.update(
        amount=10,
        occurred_at=t0 + timedelta(hours=1),
        merchant="Imtiaz",
        city="Karachi",
        country="Pakistan",
    )
    p.update(
        amount=10,
        occurred_at=t0 + timedelta(hours=2),
        merchant="Careem",
        city="Lahore",
        country="Pakistan",
    )
    assert p.seen_cities["Karachi"] == 2
    assert p.seen_merchants["Imtiaz"] == 2
    assert p.seen_merchants["Careem"] == 1


def test_profile_roundtrip_via_row_values(t0):
    p = Profile()
    p.update(amount=100, occurred_at=t0, merchant="m", city="Karachi", country="Pakistan")
    values = p.to_row_values()
    assert values["ema_amount"] == 100
    assert values["seen_cities"] == {"Karachi": 1}
    restored = Profile(**{k: v for k, v in values.items() if k != "last_tx_at"})
    restored.last_tx_at = values["last_tx_at"]
    assert restored.tx_count == 1
    assert restored.last_city == "Karachi"
