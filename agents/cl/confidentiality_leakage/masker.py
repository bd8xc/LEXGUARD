"""Value masking helpers for confidentiality API responses."""

from __future__ import annotations

import re


def _mask_word(word: str) -> str:
    if len(word) <= 1:
        return "*"
    if len(word) == 2:
        return f"{word[0]}*"
    return f"{word[0]}{'*' * (len(word) - 2)}{word[-1]}"


def mask_value(value_type: str, value: str) -> str:
    """Mask sensitive value according to detection type for safe API output."""

    text = (value or "").strip()
    if not text:
        return ""

    if value_type in {"EMAIL"}:
        parts = text.split("@", 1)
        if len(parts) == 2:
            local = parts[0]
            domain = parts[1]
            local_masked = (local[:1] + "***") if local else "***"
            return f"{local_masked}@{domain}"

    if value_type in {"PHONE_NUMBER", "AADHAAR_NUMBER", "PAN_NUMBER", "BANK_ACCOUNT", "IBAN", "CREDIT_CARD", "POSTAL_CODE"}:
        digits = re.sub(r"\D", "", text)
        if len(digits) <= 4:
            return "*" * len(digits)
        return f"{'*' * (len(digits) - 4)}{digits[-4:]}"

    if value_type in {"IP_ADDRESS"}:
        octets = text.split(".")
        if len(octets) == 4:
            return f"***.***.***.{octets[-1]}"

    if value_type in {"PERSON", "ORG", "GPE", "LOC", "ADDRESS"}:
        words = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9\s]+", text)
        masked = []
        for token in words:
            if token.isalnum():
                masked.append(_mask_word(token))
            else:
                masked.append(token)
        return "".join(masked)

    if value_type.startswith("CONFIDENTIAL_"):
        return f"[{value_type}]"

    return "***"
