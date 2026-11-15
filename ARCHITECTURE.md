# Hifazat — Architecture

Hifazat (حفاظت) is a personal finance + fraud detection web app. It watches a
user's transactions through a deterministic anomaly engine — seven explainable
rules operating on an online-learned spending profile per account — and raises
real-time, resovable alerts. No black box: every score is a weighted sum of
named reasons the user gets to see.

## System diagram

```
                    ┌──────────────────────────────────────────────┐
                    │                  Browser (SPA)                │
                    │  login · dashboard · transactions · insights  │
                    └───────────────┬──────────────────┬───────────┘
                                    │ REST (JSON)      │ WebSocket /ws/alerts
                                    ▼                  ▼
                    ┌──────────────────────────────────────────────┐
                    │                    FastAPI                    │
                    │  /api/auth · /api/accounts · /api/transactions│
                    │  /api/alerts · /api/insights · /ws/alerts    │
                    │         security headers · CORS · rate limits │
                    └───────┬──────────────────────────┬───────────┘
                            │                          │
                      anomaly engine             push new alerts
                            │                          │
                    ┌───────▼──────────┐   ┌──────────▼───────────┐
                    │  app/engine/     │   │  alert manager        │
                    │  profiles · rules│   │  (websocket registry) │
                    │  travel · scorer │   └───────────────────────┘
                    └───────┬──────────┘
                            │ SQLAlchemy 2.0 (ORM)
                    ┌───────▼──────────────────────────────┐
                    │  PostgreSQL 16 (prod) / SQLite (dev)│
                    │  users · accounts · transactions ·   │
                    │  alerts                              │
                    └──────────────────────────────────────┘
```

## Anomaly engine — how a transaction is judged

Every account keeps an **online profile** (stored on the account row, updated
with each transaction in the same DB transaction):

- `ema_amount` — exponentially weighted mean of transaction amounts.
- `ema_mad` — exponentially weighted mean absolute deviation (robust scale).
- `ema_gap_h` — EMA of hours between transactions (cadence).
- `seen_cities` / `merchants` — first-time signals.
- `last_tx_at`, `last_city`, `last_amount` — context for sequence rules.

A new transaction is scored against seven rules:

| Rule | Signal | Weight |
|---|---|---|
| `amount_spike` | amount > mean + 8×MAD and ≥ 3× mean | 0.35 |
| `rapid_geo` | two cities ≥ 400 km apart within 24 h | 0.25 (hard floor: score ≥ 82) |
| `geo_travel` | city > 1000 km from home, first time there | 0.20 |
| `velocity` | 24 h spend > 4× expected daily volume | 0.15 |
| `high_frequency` | burst: gap far below cadence + repeats | 0.10 |
| `new_payee` | never-seen merchant, amount > 2× mean | 0.10 |
| `off_hours` | 00–05 h and amount > 1.5× mean | 0.05 |

Composite = Σ(weight × rule severity), capped at 100. Rules that need history
(e.g. mean) skip silently until the profile has enough samples, so early
transactions are not misjudged.

- score ≥ 40 → flagged, alert created (severity by band).
- Severity bands: 40–59 low · 60–74 medium · 75–89 high · 90+ critical.

Alert lifecycle: `open → acknowledged → resolved (false_positive | confirmed_fraud)`.
Resolving an alert is a user decision, and the outcome is stored — false
positives tune nothing automatically because the profile is amount-driven, not
event-driven; a human verdict stays visible in history.

## Data model

- **users** — email, name, password hash (bcrypt, rounds 12), demo flag.
- **accounts** — owner, type, bank, currency, home city/country, balance, profile
  columns (ema_amount, ema_mad, ema_gap_h, tx_count, seen_cities JSON,
  merchants JSON, last_tx_at, last_city, last_country).
- **transactions** — account, amount, category, merchant, city, country, channel,
  occurred_at, risk_score, is_flagged, reasons JSON, alert_id.
- **alerts** — account_id, user_id (denormalised for fast queries), tx_id,
  severity, status, outcome, timestamps.

## Security

- JWT (HS256) access tokens, bcrypt password hashing, per-route ownership checks
  returning **404** for foreign resources (no existence leak).
- SlowAPI rate limiting (auth and transactions; per-process — Redis for
  multi-worker production).
- Security headers middleware (nosniff, X-Frame-Options DENY, referrer-policy,
  permissions-policy, CSP) + CORS allow-list from env.
- Secrets only via environment (`.env`); production boot refuses a weak
  `JWT_SECRET`. No hardcoded keys anywhere.

## Scaling notes

- The engine is pure and stateless per account — the profile lives in the DB,
  so multiple API workers can score concurrently; no shared memory needed.
- Background worker (`celery` + Redis) is the intended upgrade: transactions
  accepted with a `202`, engine scores off-queue, events fan out via Redis
  pub/sub to the WebSocket gateway.
- Read path scales with standard Postgres indexes on `(user_id, created_at)` for
  transactions/alerts; insights queries can move to a materialised summary
  table or a read replica.
- Rate limiting moves from per-process to Redis-backed when scaling beyond one
  process.

## Tech stack

FastAPI · SQLAlchemy 2.0 · Pydantic v2 · JWT + bcrypt · slowapi · vanilla-JS
mobile-first SPA (no build step) · SQLite (dev) / PostgreSQL 16 (Docker prod) ·
WebSockets for realtime alerts · pytest · ruff.
