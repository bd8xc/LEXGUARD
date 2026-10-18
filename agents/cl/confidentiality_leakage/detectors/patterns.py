"""Centralized patterns for structured identifiers.

Patterns intentionally require labels or identifier-like formatting where possible;
plain numbers are handled only by the PII detector when a nearby label exists.
"""

import re

PATTERNS = {
    "EMAIL": re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w-])"),
    "PHONE": re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?)?\d{3,5}[\s.-]\d{4,5}(?!\d)"),
    "PAN": re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])"),
    "AADHAAR": re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)"),
    "PASSPORT": re.compile(r"(?i)\b(?:passport(?:\s*(?:no|number))?\s*[:#-]?\s*)?[A-Z][0-9]{7}\b"),
    "DRIVING_LICENSE": re.compile(r"(?i)\b(?:dl|driving\s+licen[cs]e)(?:\s*(?:no|number))?\s*[:#-]?\s*[A-Z0-9/-]{6,20}\b"),
    "GST": re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b"),
    "IFSC": re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
    "BANK_ACCOUNT": re.compile(r"(?i)\b(?:a/?c|account(?:\s+number)?|bank\s+account)\s*[:#-]?\s*\d{9,18}\b"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    # BICs are accepted only with an explicit label or a digit in the location/branch part.
    # This prevents ordinary all-uppercase contract words from being treated as codes.
    "SWIFT": re.compile(r"(?i)(?<![A-Z0-9])(?:swift|bic)(?:\s+code)?\s*[:#=-]?\s*[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?(?![A-Z0-9])|(?<![A-Z0-9])[A-Z]{4}[A-Z]{2}(?=[A-Z0-9]*\d)[A-Z0-9]{2}(?:[A-Z0-9]{3})?(?![A-Z0-9])"),
    "CREDIT_CARD": re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    "UPI_ID": re.compile(r"\b[A-Za-z0-9._-]{2,}@[A-Za-z][A-Za-z0-9.-]{1,}\b"),
    "ORG": re.compile(r"\b(?:[A-Z][A-Za-z&.-]*\s+){1,8}(?:PRIVATE LIMITED|PVT\.?\s+LTD\.?|LIMITED|CORPORATION|CORP\.?)\b"),
    "IP_ADDRESS": re.compile(r"(?<!\d)(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?!\d)"),
    "MAC_ADDRESS": re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b"),
    "POSTAL_CODE": re.compile(r"\b[1-9][0-9]{5}\b"),
    "EMPLOYEE_ID": re.compile(r"(?i)\b(?:employee|emp|staff)\s*(?:id|number|no)\s*[:#-]?\s*[A-Z0-9/-]{2,20}\b"),
    "VENDOR_ID": re.compile(r"(?i)\bvendor\s*(?:id|number|no)\s*[:#-]?\s*[A-Z0-9/-]{2,20}\b"),
    "INVOICE_ID": re.compile(r"(?i)\binvoice\s*(?:id|number|no)\s*[:#-]?\s*[A-Z0-9/-]{3,30}\b"),
    "API_KEY": re.compile(r"(?i)\b(?:api[_ -]?key|x-api-key)\s*[:=]\s*[A-Za-z0-9._~+/=-]{16,}\b"),
    "JWT_TOKEN": re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "ACCESS_TOKEN": re.compile(r"(?i)\b(?:access[_ -]?token|bearer)\s*[:=]\s*[A-Za-z0-9._~+/=-]{16,}\b"),
    "OAUTH_TOKEN": re.compile(r"(?i)\b(?:oauth[_ -]?token|refresh[_ -]?token)\s*[:=]\s*[A-Za-z0-9._~+/=-]{16,}\b"),
    "SECRET_KEY": re.compile(r"(?i)\b(?:secret[_ -]?key|client[_ -]?secret)\s*[:=]\s*[^\s,;]{12,}\b"),
    "DATABASE_PASSWORD": re.compile(r"(?i)\b(?:db|database)[_ -]?pass(?:word)?\s*[:=]\s*[^\s,;]{6,}\b"),
    "CONNECTION_STRING": re.compile(r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|redis)://[^\s\"']+"),
    "AWS_ACCESS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "AZURE_KEY": re.compile(r"(?i)\b(?:azure|storage)[_ -]?(?:account[_ -]?)?key\s*[:=]\s*[A-Za-z0-9+/=]{20,}\b"),
    "GOOGLE_API_KEY": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
}
