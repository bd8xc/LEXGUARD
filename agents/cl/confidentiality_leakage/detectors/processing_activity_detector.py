"""Detector for personal-data processing operations."""

from __future__ import annotations

import re
from typing import Any

from .dictionaries import PROCESSING_ACTIVITIES, PROCESSING_DATA_TERMS


class ProcessingActivityDetector:
    """Return each processing verb or transfer concept with clause context."""

    def detect(self, text: str, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        text = text or ""
        expression = r"\b(?:" + "|".join(re.escape(term) for term in PROCESSING_ACTIVITIES) + r")\b"
        matches = list(re.finditer(expression, text, re.IGNORECASE))
        data_context = re.compile(r"\b(?:" + "|".join(re.escape(term) for term in PROCESSING_DATA_TERMS) + r")\b", re.IGNORECASE)
        findings = [
            {
                "type": "PROCESSING_ACTIVITY",
                "value": match.group(0),
                "activity": match.group(0).lower(),
                "start": match.start(),
                "end": match.end(),
                "source": "processing",
                "category": "processing_activity",
            }
            for match in matches
            if data_context.search(text[max(0, match.start() - 80):match.end() + 80])
        ]
        if findings:
            for match in re.finditer(r"\bthird\s+party\b", text, re.IGNORECASE):
                if not any(abs(match.start() - finding["start"]) <= 120 for finding in findings):
                    continue
                findings.append({"type": "PROCESSING_ACTIVITY", "value": match.group(0), "activity": match.group(0).lower(), "start": match.start(), "end": match.end(), "source": "processing", "category": "processing_activity"})
        return findings
