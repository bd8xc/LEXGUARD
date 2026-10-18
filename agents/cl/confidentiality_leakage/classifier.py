"""Sensitivity classification and deduplication logic."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

CRITICAL_TYPES = {
    "API_KEY", "PRIVATE_KEY", "JWT_TOKEN", "ACCESS_TOKEN", "OAUTH_TOKEN", "SECRET_KEY",
    "DATABASE_PASSWORD", "CONNECTION_STRING", "AWS_ACCESS_KEY", "AZURE_KEY", "GOOGLE_API_KEY",
    "BANK_ACCOUNT", "CREDIT_CARD", "MEDICAL_HISTORY", "DIAGNOSIS", "PRESCRIPTION", "BIOMETRIC_DATA",
    "GENETIC_INFORMATION", "CONFIDENTIAL_TRADE_SECRET", "CONFIDENTIAL_FINANCIAL", "CONFIDENTIAL_CREDENTIAL",
}
HIGH_TYPES = {
    "AADHAAR_NUMBER",
    "PAN_NUMBER",
    "IBAN",
    "PASSPORT", "PASSPORT_NUMBER", "DRIVING_LICENSE", "DRIVING_LICENSE_NUMBER", "GST", "TAX_ID", "SALARY",
    "HEALTH_INSURANCE", "BLOOD_GROUP", "DISABILITY", "RELIGION", "POLITICAL_AFFILIATION", "SEXUAL_ORIENTATION",
    "CONFIDENTIAL_CUSTOMER", "CONFIDENTIAL_RESEARCH",
}
MEDIUM_TYPES = {
    "EMAIL",
    "PHONE_NUMBER",
    "IP_ADDRESS",
    "ADDRESS",
    "POSTAL_CODE",
    "DOB", "AGE", "GENDER", "NATIONALITY", "EMERGENCY_CONTACT", "MARITAL_STATUS",
    "DEPENDENT_INFORMATION", "EMPLOYEE_NUMBER", "PAYROLL_ID", "UPI_ID", "IFSC", "SWIFT", "MAC_ADDRESS",
    "EMPLOYEE_ID", "VENDOR_ID", "INVOICE_ID",
    "CONFIDENTIAL_STRATEGY",
    "CONFIDENTIAL_PERSONNEL",
}
CONTEXT_TYPES = {"ORG", "GPE", "LOC", "MONEY", "DATE", "PERSON"}
LOW_TYPES = {"CONFIDENTIAL_CONTRACT", "PROCESSING_ACTIVITY"}
UNKNOWN_SENSITIVITY = "LOW"

KNOWN_TYPES = CRITICAL_TYPES | HIGH_TYPES | MEDIUM_TYPES | CONTEXT_TYPES | LOW_TYPES

if len(KNOWN_TYPES) != sum(len(group) for group in (CRITICAL_TYPES, HIGH_TYPES, MEDIUM_TYPES, CONTEXT_TYPES, LOW_TYPES)):
    raise RuntimeError("Sensitivity policy contains duplicate detection types")


def sensitivity_for_detection(detection_type: str) -> str:
    """Return the explicit policy class for a detector type.

    Unknown types are retained as LOW until their detector contract is reviewed;
    this prevents an unrecognized finding from inflating risk or context counts.
    """
    if detection_type in CRITICAL_TYPES:
        return "CRITICAL"
    if detection_type in HIGH_TYPES:
        return "HIGH"
    if detection_type in MEDIUM_TYPES:
        return "MEDIUM"
    if detection_type in CONTEXT_TYPES:
        return "CONTEXT_DEPENDENT"
    return UNKNOWN_SENSITIVITY


def _priority(finding: Dict[str, Any]) -> Tuple[int, int]:
    source_rank = 0 if finding.get("source") != "ner" else 1
    sensitivity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "CONTEXT_DEPENDENT": 4}.get(
        finding.get("sensitivity", "CONTEXT_DEPENDENT"),
        5,
    )
    return source_rank, sensitivity_rank


def _overlaps(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return not (left["end"] <= right["start"] or right["end"] <= left["start"])


def classify_findings(findings: Iterable[Dict[str, Any]], clause_id: str = "", section: str = "") -> List[Dict[str, Any]]:
    """Attach sensitivity and remove duplicates / overlapping weaker findings."""

    classified: List[Dict[str, Any]] = []
    for finding in findings:
        item = dict(finding)
        item["sensitivity"] = sensitivity_for_detection(str(item.get("type", "")))
        item["clause_id"] = clause_id
        item["section"] = section
        classified.append(item)

    classified.sort(key=lambda item: (item["start"], item["end"], _priority(item)))
    deduped: List[Dict[str, Any]] = []

    for item in classified:
        replaced = False
        for index, kept in enumerate(list(deduped)):
            exact_duplicate = (
                item["type"] == kept["type"]
                and item["value"] == kept["value"]
                and item["start"] == kept["start"]
                and item["end"] == kept["end"]
            )
            ner_structured_conflict = (
                _overlaps(item, kept)
                and ((item.get("source") == "ner") != (kept.get("source") == "ner"))
            )
            if exact_duplicate or ner_structured_conflict:
                if ner_structured_conflict and _priority(item) < _priority(kept):
                    deduped[index] = item
                replaced = True
                break
        if not replaced:
            deduped.append(item)

    deduped.sort(key=lambda item: (item["start"], item["end"], item["type"], item["value"]))
    return deduped
