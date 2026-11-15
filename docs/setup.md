# Setup

## Requirements

- Python 3.11+
- (Optional) Docker + Docker Compose for the PostgreSQL path

## Local, SQLite (fastest)

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-23-hifazat.git
cd day-23-hifazat
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))" >> .env
python -m app.seed
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 and sign in with `demo@hifazat.pk` / `demo12345`.

`app.seed` creates the demo user, one account, 45 days of routine history
replayed through the engine (so the profile is genuinely learned), and a
six-transaction fraud story ending in an impossible-travel incident.

## Docker, PostgreSQL 16

```bash
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
docker compose up --build
```

App on http://localhost:8000, PostgreSQL on :5432. The app container waits for
the database healthcheck before starting.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./hifazat.db` | Use `postgresql+psycopg://…` for Postgres |
| `JWT_SECRET` | — | **Required in production.** Boot fails on the placeholder value |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRE_MINUTES` | `1440` | 24 h |
| `FRONTEND_ORIGIN` | `http://127.0.0.1:8000` | Comma-separated CORS allow-list |
| `RATE_LIMIT_PER_MINUTE` | `120` | |
| `RISK_THRESHOLD` | `40` | Score at/above which an alert is raised |
| `DEBUG` | `false` | `false` disables `/docs` and enforces the secret check |

## Deploying

The repo ships a `Dockerfile`, `docker-compose.yml`, and a Vercel serverless
entry (`api/index.py` + `vercel.json`).

**Vercel / serverless caveat.** Hifazat needs a persistent filesystem for
uploads and a real database. Vercel's filesystem is read-only apart from
`/tmp`, and `/tmp` does not survive between invocations, so SQLite data would
be lost. If you deploy there, set `DATABASE_URL` to a hosted PostgreSQL
(Neon, Supabase, RDS) and a strong `JWT_SECRET` in the project's environment
variables. For a self-contained deployment, Docker Compose is the intended
path.

```bash
# Vercel, with a hosted database
vercel --prod --yes --token "$VERCEL_TOKEN"
```

## Tests and lint

```bash
pytest -q                 # 51 tests, no network required
ruff check .              # lint
ruff format --check .     # formatting
```

## Troubleshooting

- **`RuntimeError: JWT_SECRET is not set to a real value`** — you are running
  with `DEBUG=false` and the placeholder secret. Generate one and put it in
  `.env`.
- **`/docs` returns 404** — expected. Interactive docs are disabled outside
  debug mode.
- **Demo data missing** — `app.seed` skips if the demo user already exists.
  Delete `hifazat.db` and re-run.
