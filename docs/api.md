# API Reference

Base URL: `http://127.0.0.1:8000`. All request and response bodies are JSON.
Authenticated routes expect `Authorization: Bearer <token>`.

Errors use FastAPI's shape: `{"detail": "..."}` for handled errors, and
`{"detail": [ ... ]}` for validation failures (HTTP 422).

---

## Health

### `GET /api/health`
No auth. Returns `{"status": "ok", "name": "Hifazat", "version": "1.0.0"}`.

---

## Auth

### `POST /api/auth/register`
Creates a user and returns a token immediately.

```json
{ "email": "you@example.com", "name": "Your Name", "password": "at-least-8-chars" }
```

- `201` → `{ "access_token": "...", "token_type": "bearer", "user": {...} }`
- `409` → email already registered
- `422` → validation failure (name < 2 chars, password < 8 chars, bad email)

### `POST /api/auth/login`
Rate limited to 10 requests/minute per client.

```json
{ "email": "you@example.com", "password": "..." }
```

- `200` → `{ "token": { "access_token": "...", "user": {...} } }`
- `401` → invalid email or password (same message for both — no user enumeration)

### `GET /api/auth/me`
Auth required. Returns the current user.

---

## Accounts

### `GET /api/accounts`
Auth required. Returns the caller's accounts.

### `POST /api/accounts`
Auth required. Maximum 6 accounts per user.

```json
{ "name": "HBL Current", "account_type": "checking", "bank": "HBL",
  "currency": "PKR", "home_city": "Karachi", "home_country": "Pakistan",
  "balance": 100000 }
```

- `201` → the created account
- `400` → account limit reached

### `GET /api/accounts/{account_id}`
Auth required. **`404` if the account belongs to another user** — foreign
resources are indistinguishable from missing ones.

---

## Transactions

### `POST /api/accounts/{account_id}/transactions`
Auth required. Scores the transaction against the account's online profile,
updates the profile, and raises an alert if the score meets the threshold.

```json
{ "amount": 1500, "merchant": "Imtiaz Super Store", "category": "groceries",
  "city": "Karachi", "country": "Pakistan", "channel": "card",
  "occurred_at": "2026-11-15T14:00:00Z" }
```

`occurred_at` is optional and defaults to now. `amount` must be > 0.

- `201` → the transaction, including `risk_score`, `is_flagged`, `reasons[]`
  and `alert_id` (null when not flagged)
- `404` → account not found or not yours
- `422` → validation failure (e.g. negative amount)

`reasons[]` entries look like:

```json
{ "key": "rapid_geo", "label": "Impossible travel", "severity": 0.95,
  "detail": "Transaction in Lahore only 1.0h after a transaction in Karachi",
  "weight": 0.25 }
```

### `GET /api/accounts/{account_id}/transactions?limit=50&offset=0`
Auth required. Newest first. `limit` 1–200.

### `GET /api/transactions?limit=50&offset=0`
Auth required. Across all of the caller's accounts.

---

## Alerts

### `GET /api/alerts?status=open&limit=50&offset=0`
Auth required. `status` is optional and one of `open`, `acknowledged`,
`resolved`.

### `GET /api/alerts/stats`
Auth required.

```json
{ "open": 2, "acknowledged": 0, "resolved": 0, "confirmed_fraud": 0,
  "false_positive": 0, "at_risk_amount": 280000.0 }
```

`at_risk_amount` sums the flagged transaction amounts on alerts that are still
open or acknowledged.

### `POST /api/alerts/{alert_id}/action`
Auth required. **`404` for another user's alert.**

```json
{ "action": "acknowledge" }
{ "action": "resolve", "outcome": "confirmed_fraud" }
{ "action": "resolve", "outcome": "false_positive" }
```

- `200` → the updated alert
- `400` → `resolve` without an `outcome`
- `404` → alert not found or not yours
- `422` → unknown action or outcome

---

## Insights

### `GET /api/insights`
Auth required.

```json
{
  "total_spent": 252628.0,
  "total_spent_prev": 54500.0,
  "change_pct": 363.9,
  "avg_tx": 7418.0,
  "top_category": "other",
  "expense_ratio": 0.51,
  "by_category": [ { "category": "other", "total": 280000.0, "count": 2, "share": 0.91 } ],
  "recurring_merchants": [ { "merchant": "Imtiaz Super Store", "count": 7,
                             "avg_amount": 2343.0, "last": "2026-11-15T14:17:00Z" } ],
  "at_risk_amount": 0.0,
  "flag_rate": 0.04
}
```

---

## WebSocket

### `WS /ws/alerts?token=<jwt>`
Browsers cannot set headers on a WebSocket handshake, so the JWT goes in the
query string. An invalid or missing token closes the socket with code `4401`.

On a flagged transaction the server pushes:

```json
{ "type": "new_alert",
  "alert": { "id": 1, "account_id": 1, "severity": "high", "score": 82.0,
             "summary": "Impossible travel — ...", "reasons": [ ... ],
             "status": "open", "created_at": "2026-11-15T19:17:00Z" } }
```

---

## Status codes at a glance

| Code | Meaning here |
|---|---|
| 200 | OK |
| 201 | Created (register, account, transaction) |
| 400 | Bad request (account limit, resolve without outcome) |
| 401 | Missing/invalid token, or bad credentials |
| 404 | Not found **or not yours** (accounts, alerts) |
| 409 | Email already registered |
| 422 | Validation failure |
| 429 | Rate limit exceeded |
