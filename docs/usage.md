# Usage

## Signing in

The demo account is `demo@hifazat.pk` / `demo12345`. It arrives with a warm
profile and two real alerts, so the dashboard is not empty on first load.

Registering a fresh account starts with a **cold profile**. The engine needs
about five transactions before amount-based rules mean anything, and it stays
silent until then rather than guessing. That is deliberate: a brand-new account
has no "normal" to compare against.

## The four screens

**Home** — balance, open alerts, at-risk amount, flag rate, recent activity and
the latest alerts.

**Activity** — every transaction, newest first, with a `flagged` marker on the
ones the engine scored above the threshold.

**Alerts** — the full list with lifecycle controls. Each row shows severity,
score, and the summary. Press **Why** to see the exact reasons behind the
score, with each rule's weight and severity.

**Insights** — this week's spend, week-over-week change, average transaction,
top category, a category breakdown, and recurring merchants.

## Adding a transaction

Press **+ Transaction**, fill in the amount and (optionally) merchant, city and
country, and submit. The engine scores it immediately:

- Below the threshold → a toast says "no flags".
- At or above → a toast reports the score and the alert appears in the Alerts
  tab, pushed live over the WebSocket if the dashboard is open.

Try the demo: add a small purchase in Karachi, then a large one in Lahore a
minute later. The second one flags as **impossible travel** with a score of at
least 82.

## Alert lifecycle

```
open ──acknowledge──▶ acknowledged ──resolve──▶ resolved
  │                                                │
  └──────────────── resolve ───────────────────────┘
                     (outcome required)
```

- **Ack** — you have seen it and are looking into it.
- **Fraud** — resolve as `confirmed_fraud`.
- **OK** — resolve as `false_positive`.

Resolving requires an outcome; the API returns 400 without one. Acknowledging
an already-acknowledged alert is a no-op, not an error.

## Reading a score

The composite score is a weighted sum of the rules that fired:

| Rule | Weight | What it means |
|---|---|---|
| Unusual amount | 0.35 | Amount far above your robust spending scale |
| Impossible travel | 0.25 | Two far-apart cities within hours (hard floor: 82) |
| Unexpected travel | 0.20 | First-ever transaction in a far-from-home city |
| Spending burst | 0.15 | 24 h spend well above your expected daily volume |
| Unusual frequency | 0.10 | Transactions much faster than your cadence |
| New payee, large amount | 0.10 | First-ever merchant with a big payment |
| Late-night spend | 0.05 | 00:00–05:00 above your usual mean |

Score bands: 40–59 low · 60–74 medium · 75–89 high · 90+ critical.

## What the engine will not do

- It will not flag a transaction it cannot reason about. If a city is not in
  its coordinate table, the geo rules stay silent rather than guess.
- It will not accuse on a cold profile.
- It has no trained model. It finds the *shape* of unusual activity, not
  known fraud patterns. A clean-looking synthetic transaction passes.
