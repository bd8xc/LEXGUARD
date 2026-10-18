"""Detector for regulated or highly sensitive personal data."""

from __future__ import annotations

import re
from typing import Any

from .dictionaries import MEDICAL_CONTEXT_TERMS, SENSITIVE_PERSONAL


class SensitivePersonalDetector:
    """Find explicit sensitive-personal-data vocabulary in clause text."""

    def detect(self, text: str, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        findings = []
        for detection_type, terms in SENSITIVE_PERSONAL.items():
            expression = r"\b(?:" + "|".join(re.escape(term) for term in terms) + r")\b"
            for match in re.finditer(expression, text or "", re.IGNORECASE):
                if detection_type == "PRESCRIPTION" and match.group(0).lower() in {"treatment", "medication"}:
                    context = (text or "")[max(0, match.start() - 50):match.end() + 50].lower()
                    if not any(term in context for term in MEDICAL_CONTEXT_TERMS):
                        continue
                findings.append({"type": detection_type, "value": match.group(0), "start": match.start(), "end": match.end(), "source": "sensitive_personal", "category": "sensitive_personal_data"})
        return findings
