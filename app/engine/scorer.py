"""Composite risk scoring: weighted sum of named rule severities.

Deterministic and decomposable — an alert carries the exact reasons that made
up its score, in weight order.
"""

from __future__ import annotations

from dataclasses import dataclass

from .profiles import Profile
from .rules import (
    RuleResult,
    rule_amount_spike,
    rule_geo_travel,
    rule_high_frequency,
    rule_new_payee,
    rule_off_hours,
    rule_rapid_geo,
    rule_velocity,
)

# (key, weight) — weight is the share of the composite score each rule can
# contribute. Rapid geo gets an additional hard floor applied in scoring.
RULE_WEIGHTS: dict[str, float] = {
    "amount_spike": 0.35,
    "rapid_geo": 0.25,
    "geo_travel": 0.20,
    "velocity": 0.15,
    "high_frequency": 0.10,
    "new_payee": 0.10,
    "off_hours": 0.05,
}

# Impossible travel is never "probably fine", even if other rules stay quiet.
RAPID_GEO_FLOOR = 82.0


@dataclass
class ScoreResult:
    """Final verdict on one transaction."""

    score: float  # 0..100
    flagged: bool
    reasons: list[dict]  # serialisable: {key, label, severity, detail, weight}
    at_risk_amount: float  # flagged amount, else 0


def severity_label(severity: float) -> str:
    if severity >= 0.90:
        return "critical"
    if severity >= 0.75:
        return "high"
    if severity >= 0.60:
        return "medium"
    return "low"


def score_transaction(
    tx: dict,
    profile: Profile,
    *,
    threshold: float,
    recent_24h: float | None = None,
    account=None,
) -> ScoreResult:
    """Evaluate a transaction against every rule and merge the results.

    Rules are called with exactly the arguments they declare — geo travel
    needs the account for the home city, velocity needs the rolling 24h sum.
    """
    results: list[RuleResult] = []

    result = rule_amount_spike(tx, profile)
    if result is not None:
        results.append(result)

    result = rule_rapid_geo(tx, profile)
    if result is not None:
        results.append(result)

    result = rule_geo_travel(tx, profile, account=account)
    if result is not None:
        results.append(result)

    result = rule_velocity(tx, profile, recent_24h=recent_24h)
    if result is not None:
        results.append(result)

    result = rule_high_frequency(tx, profile)
    if result is not None:
        results.append(result)

    result = rule_new_payee(tx, profile)
    if result is not None:
        results.append(result)

    result = rule_off_hours(tx, profile)
    if result is not None:
        results.append(result)

    total = 0.0
    reason_dicts: list[dict] = []
    for result in results:
        weight = RULE_WEIGHTS.get(result.key, 0.0)
        total += weight * result.severity
        reason_dicts.append(
            {
                "key": result.key,
                "label": result.label,
                "severity": round(result.severity, 3),
                "detail": result.detail,
                "weight": weight,
            }
        )

    score = total * 100.0
    has_rapid_geo = any(r.key == "rapid_geo" for r in results)
    if has_rapid_geo:
        score = max(score, RAPID_GEO_FLOOR)

    score = round(min(score, 100.0), 1)
    flagged = score >= threshold

    return ScoreResult(
        score=score,
        flagged=flagged,
        reasons=reason_dicts,
        at_risk_amount=tx["amount"] if flagged else 0.0,
    )
