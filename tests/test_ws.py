"""WebSocket tests: auth rejection and live alert delivery."""

from datetime import UTC, datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.security import create_access_token
from tests.conftest import auth_headers


def test_ws_rejects_missing_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/alerts") as ws:
            ws.receive_text()


def test_ws_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/alerts?token=garbage") as ws:
            ws.receive_text()


def test_ws_delivers_new_alert(client, demo_user):
    """A flagged transaction must arrive on the user's live socket."""
    token = create_access_token(demo_user["user_id"])
    headers = auth_headers(demo_user)
    account_id = demo_user["account_id"]
    now = datetime.now(UTC)

    with client.websocket_connect(f"/ws/alerts?token={token}") as ws:
        # Prime a Karachi transaction, then a Lahore one 10 min later.
        client.post(
            f"/api/accounts/{account_id}/transactions",
            headers=headers,
            json={
                "amount": 1200,
                "merchant": "Karachi A",
                "city": "Karachi",
                "country": "Pakistan",
                "occurred_at": (now - timedelta(minutes=10)).isoformat(),
            },
        )
        client.post(
            f"/api/accounts/{account_id}/transactions",
            headers=headers,
            json={
                "amount": 1200,
                "merchant": "Lahore B",
                "city": "Lahore",
                "country": "Pakistan",
                "occurred_at": now.isoformat(),
            },
        )
        message = ws.receive_json()
        assert message["type"] == "new_alert"
        assert message["alert"]["severity"] in ("high", "critical")
        assert message["alert"]["score"] >= 82
