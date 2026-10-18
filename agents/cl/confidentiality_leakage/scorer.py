"""Deterministic document-level risk scoring."""

from __future__ import annotations

from collections import Counter
from math import exp
from typing import Dict, Iterable, Tuple

TYPE_WEIGHTS: Dict[str, int] = {
    "CRITICAL": 30, "HIGH": 16, "MEDIUM": 7, "LOW": 2, "CONTEXT_DEPENDENT": 0,
}

RISK_LEVELS: Tuple[Tuple[int, int, str], ...] = (
    (0, 19, "LOW"),
    (20, 49, "MEDIUM"),
    (50, 74, "HIGH"),
    (75, 100, "CRITICAL"),
)


def _risk_level(score: int) -> str:
    for low, high, label in RISK_LEVELS:
        if low <= score <= high:
            return label
    return "CRITICAL"


def score_confidentiality(
    findings: Iterable[Dict[str, object]],
    processing_activity_count: int = 0,
) -> Dict[str, object]:
    """Return a capped 0-100 risk score and discrete risk level."""

    counts = Counter(str(finding.get("sensitivity", "CONTEXT_DEPENDENT")) for finding in findings)
    critical = counts.get("CRITICAL", 0)
    high = counts.get("HIGH", 0)
    medium = counts.get("MEDIUM", 0)
    low = counts.get("LOW", 0)
    context = counts.get("CONTEXT_DEPENDENT", 0)

    if (critical + high + medium + low + context + processing_activity_count) <= 0:
        return {"risk_score": 0, "risk_level": "LOW"}

    # Saturating components keep the score bounded and prevent context-only
    # entities from dominating large legal documents.
    critical_component = 55.0 * (1.0 - exp(-critical / 1.5))
    high_component = 30.0 * (1.0 - exp(-high / 2.0))
    medium_component = 15.0 * (1.0 - exp(-medium / 4.0))
    processing_component = 12.0 * (1.0 - exp(-processing_activity_count / 8.0))
    low_component = min(5.0, low * 0.5)

    score = int(round(min(100.0, critical_component + high_component + medium_component + processing_component + low_component)))
    return {"risk_score": score, "risk_level": _risk_level(score)}
