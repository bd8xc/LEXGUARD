"""Conservative spaCy context detector; NER never drives risk severity."""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from .dictionaries import ENTITY_NON_PERSON_TERMS, ENTITY_PLACEHOLDERS, ENTITY_ROLE_TERMS, LEGAL_BOILERPLATE
from .patterns import PATTERNS

_ALLOWED = {"PERSON", "ORG", "GPE", "LOC", "MONEY", "DATE"}
_PLACEHOLDER = re.compile(r"^[A-Z]{2,5}$")
_CORPORATE_SUFFIXES = re.compile(r"\b(?:private limited|pvt\.? ltd\.?|limited|corporation|corp\.?)\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def _load_nlp():
    try:
        import spacy
    except ImportError:  # NER is optional; deterministic detectors remain usable.
        return None
    try:
        return spacy.load("en_core_web_sm")
    except OSError:  # The deterministic detectors and narrow regex NER remain usable.
        return None


def _valid(label: str, value: str, context: str = "") -> bool:
    normalized = re.sub(r"\s+", " ", value.strip(" \"'`.,;:()[]{}"))
    lowered = normalized.lower()
    words = lowered.split()
    first_word = words[0] if words else ""
    if (
        not normalized
        or lowered in LEGAL_BOILERPLATE
        or lowered in ENTITY_ROLE_TERMS
        or lowered in ENTITY_PLACEHOLDERS
        or any(lowered.startswith(term + " ") for term in LEGAL_BOILERPLATE)
        or first_word in ENTITY_PLACEHOLDERS
        or all(word in {"the", "a", "an", "private", "pvt", "limited", "ltd", "corporation", "corp"} for word in words)
    ):
        return False
    if label == "PERSON":
        return (
            len(re.findall(r"[A-Za-z]+", normalized)) >= 2
            and not re.search(r"\b(?:company|employee|party|section|schedule)\b", lowered)
            and not _CORPORATE_SUFFIXES.search(normalized)
            and not any(term in words for term in ENTITY_NON_PERSON_TERMS)
            and not (re.search(r"\d", context) and any(term in context.lower().split() for term in ENTITY_NON_PERSON_TERMS))
        )
    if label == "MONEY":
        return bool(re.search(r"\d|[$€£₹]", normalized))
    if label in {"GPE", "LOC"}:
        return len(normalized) >= 3 and not any(term in words for term in ENTITY_ROLE_TERMS)
    if label == "ORG":
        return len(normalized) >= 4 and not lowered.startswith(("the ", "a ")) and not _PLACEHOLDER.fullmatch(normalized) and not (first_word in ENTITY_PLACEHOLDERS and _CORPORATE_SUFFIXES.search(normalized))
    if label == "DATE":
        return not re.search(r"\b(?:within|after|before|for)\s+(?:\w+\s+)?days?\b", context.lower())
    return True


class NERDetector:
    """Supplement deterministic detectors with validated named-entity context."""

    def detect(self, text: str, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        findings = []
        nlp = _load_nlp()
        if nlp is None:
            # Keep the engine usable in minimal deployments; this narrow fallback
            # only recognizes explicit person names and corporate suffixes.
            for match in re.finditer(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", text or ""):
                context = (text or "")[max(0, match.start() - 60):match.end() + 60]
                if _valid("PERSON", match.group(0), context):
                    findings.append({"type": "PERSON", "value": match.group(0), "start": match.start(), "end": match.end(), "source": "ner", "category": "context"})
            for match in PATTERNS["ORG"].finditer(text or ""):
                value = match.group(0).strip()
                context = (text or "")[max(0, match.start() - 60):match.end() + 60]
                if _valid("ORG", value, context):
                    findings.append({"type": "ORG", "value": value, "start": match.start(), "end": match.end(), "source": "ner", "category": "context"})
            return findings
        for entity in nlp(text or "").ents:
            context = (text or "")[max(0, entity.start_char - 60):entity.end_char + 60]
            if entity.label_ not in _ALLOWED or not _valid(entity.label_, entity.text, context):
                continue
            findings.append({"type": entity.label_, "value": entity.text.strip(), "start": entity.start_char, "end": entity.end_char, "source": "ner", "category": "context"})
        # spaCy can return only the suffix portion of an all-caps company name.
        # Prefer the full deterministic legal-name span when both overlap.
        for match in PATTERNS["ORG"].finditer(text or ""):
            value = match.group(0).strip()
            context = (text or "")[max(0, match.start() - 60):match.end() + 60]
            if not _valid("ORG", value, context):
                continue
            findings = [
                item for item in findings
                if item.get("type") != "ORG"
                or item["end"] <= match.start()
                or item["start"] >= match.end()
            ]
            findings.append({"type": "ORG", "value": value, "start": match.start(), "end": match.end(), "source": "ner", "category": "context"})
        return findings


def detect_ner_sensitive_info(text: str) -> list[dict[str, Any]]:
    """Compatibility function for the original public detector API."""
    return NERDetector().detect(text)
