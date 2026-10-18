"""Structured identifier and credential detector."""

from __future__ import annotations

import re
from typing import Any

from .patterns import PATTERNS


_LABEL_CONTEXT = {
    "PAN": ("pan", "permanent account number"),
    "AADHAAR": ("aadhaar", "aadhar", "uid"),
    "PASSPORT": ("passport",),
    "GST": ("gst", "gstin", "tax registration"),
    "IFSC": ("ifsc", "bank code", "bank"),
    "IBAN": ("iban", "bank account"),
}
_PHONE_CONTEXT = ("call", "phone", "mobile", "telephone", "contact", "tel", "fax")
_NETWORK_CONTEXT = ("ip", "ip address", "server", "host", "network", "address")
_UPI_CONTEXT = ("upi", "vpa", "unified payments interface", "virtual payment address")


def _nearby(text: str, start: int, end: int, terms: tuple[str, ...], radius: int = 60) -> bool:
    context = text[max(0, start - radius):min(len(text), end + radius)].lower()
    return any(term in context for term in terms)


def _valid_luhn(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = sum((digit * 2 - 9 if digit * 2 > 9 else digit * 2) if index % 2 == len(digits) % 2 else digit for index, digit in enumerate(digits))
    return checksum % 10 == 0


class RegexDetector:
    """Detect formatted identifiers and secrets without classifying prose."""

    def detect(self, text: str, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        text = text or ""
        type_names = {"PAN": "PAN_NUMBER", "AADHAAR": "AADHAAR_NUMBER", "PASSPORT": "PASSPORT_NUMBER", "DRIVING_LICENSE": "DRIVING_LICENSE_NUMBER"}
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                if name == "PHONE" and re.fullmatch(r"\d{4}[ -]?\d{4}[ -]?\d{4}", match.group(0)):
                    continue
                if name == "CREDIT_CARD" and not _valid_luhn(match.group(0)):
                    continue
                if name == "PHONE" and len(re.sub(r"\D", "", match.group(0))) < 10:
                    continue
                if name in _LABEL_CONTEXT and not _nearby(text, match.start(), match.end(), _LABEL_CONTEXT[name]):
                    continue
                if name == "PHONE" and not (match.group(0).startswith("+") or _nearby(text, match.start(), match.end(), _PHONE_CONTEXT, radius=35)):
                    continue
                if name == "IP_ADDRESS" and not _nearby(text, match.start(), match.end(), _NETWORK_CONTEXT, radius=35):
                    continue
                if name == "POSTAL_CODE" and not _nearby(text, match.start(), match.end(), ("pin", "postal", "zip", "address", "office"), radius=40):
                    continue
                if name == "UPI_ID" and not _nearby(text, match.start(), match.end(), _UPI_CONTEXT):
                    continue
                value = match.group(0)
                if name == "ORG" and value.split()[0].lower() in {"xyz", "abc", "tbd", "n/a", "na"}:
                    continue
                findings.append({
                    "type": type_names.get(name, "PHONE_NUMBER" if name == "PHONE" else name),
                    "value": value,
                    "start": match.start(),
                    "end": match.end(),
                    "source": "regex",
                    "category": "context" if name == "ORG" else "personal_data",
                })
        return findings


def detect_regex_sensitive_info(text: str) -> list[dict[str, Any]]:
    """Compatibility function for the original public detector API."""
    return RegexDetector().detect(text)
