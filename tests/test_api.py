"""API integration tests: auth, ownership, transactions, alerts, insights."""

from datetime import UTC, datetime, timedelta

from tests.conftest import auth_headers


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_and_login_flow(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "newbie@test.pk", "name": "Newbie", "password": "password123"},
    )
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "newbie@test.pk"

    r2 = client.post("/api/auth/login", json={"email": "newbie@test.pk", "password": "password123"})
    assert r2.status_code == 200
    assert r2.json()["token"]["access_token"]


def test_duplicate_email_conflicts(client):
    payload = {"email": "dupe@test.pk", "name": "Dupe", "password": "password123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_wrong_password_rejected(client):
    client.post(
        "/api/auth/register",
        json={"email": "pw@test.pk", "name": "Pw", "password": "password123"},
    )
    r = client.post("/api/auth/login", json={"email": "pw@test.pk", "password": "wrongpass"})
    assert r.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/accounts").status_code == 401


def test_me_returns_current_user(client, demo_user):
    r = client.get("/api/auth/me", headers=auth_headers(demo_user))
    assert r.status_code == 200
    assert r.json()["email"] == "owner@test.pk"


def test_foreign_account_returns_404(client, demo_user, other_user):
    """Ownership check must not leak existence — 404, not 403."""
    r = client.get(f"/api/accounts/{other_user['account_id']}", headers=auth_headers(demo_user))
    assert r.status_code == 404


def test_create_transaction_scores_and_persists(client, demo_user):
    headers = auth_headers(demo_user)
    account_id = demo_user["account_id"]
    r = client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={"amount": 1500, "merchant": "Imtiaz", "category": "groceries", "city": "Karachi"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["amount"] == 1500
    assert "risk_score" in body
    assert isinstance(body["reasons"], list)


def test_impossible_travel_creates_alert(client, demo_user):
    """Karachi then Lahore within an hour must flag and raise an alert."""
    headers = auth_headers(demo_user)
    account_id = demo_user["account_id"]
    now = datetime.now(UTC)

    client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={
            "amount": 2000,
            "merchant": "Karachi Shop",
            "city": "Karachi",
            "country": "Pakistan",
            "occurred_at": (now - timedelta(minutes=30)).isoformat(),
        },
    )
    r = client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={
            "amount": 2000,
            "merchant": "Lahore Shop",
            "city": "Lahore",
            "country": "Pakistan",
            "occurred_at": now.isoformat(),
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["is_flagged"] is True
    assert body["risk_score"] >= 82
    assert body["alert_id"] is not None


def _fresh_account(client, user) -> int:
    """A brand-new account per test, so no earlier test's city leaks in."""
    r = client.post(
        "/api/accounts",
        headers=auth_headers(user),
        json={"name": "Test Account", "home_city": "Karachi", "home_country": "Pakistan"},
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_alert_lifecycle_acknowledge_then_resolve(client, demo_user):
    headers = auth_headers(demo_user)
    account_id = _fresh_account(client, demo_user)
    now = datetime.now(UTC)
    client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={
            "amount": 1000,
            "merchant": "A",
            "city": "Karachi",
            "occurred_at": (now - timedelta(minutes=20)).isoformat(),
        },
    )
    r = client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={"amount": 1000, "merchant": "B", "city": "Lahore", "occurred_at": now.isoformat()},
    )
    alert_id = r.json()["alert_id"]
    assert alert_id

    ack = client.post(
        f"/api/alerts/{alert_id}/action", headers=headers, json={"action": "acknowledge"}
    )
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    res = client.post(
        f"/api/alerts/{alert_id}/action",
        headers=headers,
        json={"action": "resolve", "outcome": "confirmed_fraud"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"
    assert res.json()["outcome"] == "confirmed_fraud"


def test_resolve_without_outcome_is_400(client, demo_user):
    headers = auth_headers(demo_user)
    account_id = _fresh_account(client, demo_user)
    now = datetime.now(UTC)
    client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={
            "amount": 1000,
            "merchant": "A",
            "city": "Karachi",
            "occurred_at": (now - timedelta(minutes=10)).isoformat(),
        },
    )
    r = client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={"amount": 1000, "merchant": "B", "city": "Lahore", "occurred_at": now.isoformat()},
    )
    alert_id = r.json()["alert_id"]
    bad = client.post(f"/api/alerts/{alert_id}/action", headers=headers, json={"action": "resolve"})
    assert bad.status_code == 400


def test_foreign_alert_returns_404(client, demo_user, other_user):
    headers = auth_headers(demo_user)
    account_id = _fresh_account(client, demo_user)
    now = datetime.now(UTC)
    client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={
            "amount": 1000,
            "merchant": "A",
            "city": "Karachi",
            "occurred_at": (now - timedelta(minutes=5)).isoformat(),
        },
    )
    r = client.post(
        f"/api/accounts/{account_id}/transactions",
        headers=headers,
        json={"amount": 1000, "merchant": "B", "city": "Lahore", "occurred_at": now.isoformat()},
    )
    alert_id = r.json()["alert_id"]
    # other user tries to act on it
    r2 = client.post(
        f"/api/alerts/{alert_id}/action",
        headers=auth_headers(other_user),
        json={"action": "acknowledge"},
    )
    assert r2.status_code == 404


def test_negative_amount_rejected(client, demo_user):
    headers = auth_headers(demo_user)
    r = client.post(
        f"/api/accounts/{demo_user['account_id']}/transactions",
        headers=headers,
        json={"amount": -50, "merchant": "Bad"},
    )
    assert r.status_code == 422


def test_insights_returns_shape(client, demo_user):
    r = client.get("/api/insights", headers=auth_headers(demo_user))
    assert r.status_code == 200
    body = r.json()
    for key in ("total_spent", "change_pct", "by_category", "recurring_merchants", "flag_rate"):
        assert key in body


def test_alert_stats_shape(client, demo_user):
    r = client.get("/api/alerts/stats", headers=auth_headers(demo_user))
    assert r.status_code == 200
    body = r.json()
    for key in ("open", "acknowledged", "resolved", "confirmed_fraud", "at_risk_amount"):
        assert key in body


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in r.headers


def test_docs_disabled_in_production_mode(client):
    assert client.get("/docs").status_code == 404
