"""Detector for labelled personal information."""

from __future__ import annotations

import re
from typing import Any
from .dictionaries import LABELS


class PIIDetector:
    """Detect personal attributes only when a clear label provides context."""

    def detect(self, text: str, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        findings = []
        for detection_type, expression in LABELS.items():
            for match in re.finditer(expression, text or "", re.IGNORECASE):
                findings.append({"type": detection_type, "value": match.group(0), "start": match.start(), "end": match.end(), "source": "pii", "category": "personal_data"})
        return findings
