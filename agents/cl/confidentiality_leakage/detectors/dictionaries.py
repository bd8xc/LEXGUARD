"""Controlled vocabularies used by semantic, category detectors."""

SENSITIVE_PERSONAL = {
    "MEDICAL_HISTORY": ("medical history", "medical record", "medical records", "health history"),
    "DIAGNOSIS": ("diagnosis", "diagnosed", "clinical condition"),
    "PRESCRIPTION": ("prescription", "medication", "treatment"),
    "HEALTH_INSURANCE": ("health insurance", "medical insurance"),
    "BLOOD_GROUP": ("blood group", "blood type"),
    "BIOMETRIC_DATA": ("biometric", "fingerprint", "retina", "iris scan", "face id", "facial recognition"),
    "GENETIC_INFORMATION": ("genetic information", "genetic data", "dna"),
    "DISABILITY": ("disability", "disabled status"),
    "RELIGION": ("religion", "religious affiliation"),
    "POLITICAL_AFFILIATION": ("political affiliation", "political party membership"),
    "SEXUAL_ORIENTATION": ("sexual orientation",),
}

BUSINESS_CONFIDENTIAL = {
    "CONFIDENTIAL_TRADE_SECRET": ("trade secret", "proprietary information", "source code", "algorithm"),
    "CONFIDENTIAL_FINANCIAL": ("financial statement", "financial forecast", "revenue", "profit margin", "pricing", "budget"),
    "CONFIDENTIAL_CUSTOMER": ("customer list", "customer lists", "client list", "client lists", "supplier list", "supplier lists", "vendor list", "vendor lists"),
    "CONFIDENTIAL_STRATEGY": ("business plan", "business plans", "internal strategy", "product roadmap", "acquisition plan"),
    "CONFIDENTIAL_RESEARCH": ("research and development", "research data", "patent information"),
    "CONFIDENTIAL_CONTRACT": ("confidential contract", "contract terms", "non-public agreement"),
    "CONFIDENTIAL_CREDENTIAL": ("encryption key", "api secret", "password", "credential"),
}

PROCESSING_ACTIVITIES = (
    "collect", "collects", "collected", "collecting",
    "store", "stores", "stored", "storing",
    "retain", "retains", "retained", "retaining",
    "delete", "deletes", "deleted", "deleting",
    "erase", "erases", "erased", "erasing",
    "share", "shares", "shared", "sharing",
    "transfer", "transfers", "transferred", "transferring",
    "transmit", "transmits", "transmitted", "transmitting",
    "process", "processes", "processed", "processing",
)

LEGAL_BOILERPLATE = {
    "company", "employee", "vendor", "supplier", "customer", "client", "recipient", "purpose",
    "applicable law", "cause", "agreement", "schedule", "section", "party", "third party",
    "receiving party", "disclosing party", "neither party", "either party", "force majeure",
    "confidential information", "affiliate", "affiliates", "private limited", "pvt ltd", "limited",
}

ENTITY_PLACEHOLDERS = {"xyz", "abc", "tbd", "n/a", "na"}

ENTITY_ROLE_TERMS = {
    "vendor", "supplier", "customer", "client", "company", "employee", "recipient", "party",
    "purpose", "force majeure", "neither party", "either party", "receiving party", "disclosing party",
}

ENTITY_NON_PERSON_TERMS = {
    "street", "road", "rd", "avenue", "ave", "lane", "ln", "marg", "boulevard", "blvd",
    "highway", "hwy", "drive", "dr", "place", "pl", "floor", "building", "office",
}

MEDICAL_CONTEXT_TERMS = (
    "medical", "health", "clinical", "patient", "doctor", "hospital", "diagnosis", "diagnosed",
    "prescription", "medication", "drug", "illness", "disease", "treatment plan",
)

CONFIDENTIALITY_CONTEXT_TERMS = (
    "confidential", "proprietary", "non-public", "nonpublic", "internal", "restricted", "secret",
    "sensitive", "protected", "commercially sensitive",
)

PROCESSING_DATA_TERMS = (
    "personal data", "personal information", "sensitive data", "employee data", "customer data",
    "user data", "data", "information", "records", "details", "identifiers", "account", "bank",
)


LABELS = {
    "DOB": r"\b(?:date of birth|dob|birth date)\s*[:=-]?\s*[^,;.\n]+",
    "AGE": r"\b(?:age)\s*[:=-]?\s*\d{1,3}\b",
    "GENDER": r"\b(?:gender|sex)\s*[:=-]?\s*(?:male|female|non-binary|other)\b",
    "NATIONALITY": r"\b(?:nationality|citizenship)\s*[:=-]?\s*[A-Za-z -]+",
    "ADDRESS": r"\b(?:residential|home|registered|mailing) address\s*[:=-]?\s*(?=[^;.\n]{0,160}\d)\d{1,6}\s+[^;.\n]{1,160}|\bregistered office\s+(?:at|located at)\s+(?=\d)\d{1,6}\s+[^;.\n]{1,160}",
    "SALARY": r"\b(?:salary|compensation|remuneration|pay)\s*[:=-]?\s*(?:[$€£₹]\s*)?[\d,]+(?:\.\d+)?",
    "EMERGENCY_CONTACT": r"\b(?:emergency contact|next of kin)\s*[:=-]?\s*[^;\n]+",
    "MARITAL_STATUS": r"\bmarital status\s*[:=-]?\s*[A-Za-z-]+",
    "DEPENDENT_INFORMATION": r"\bdependents?\s*[:=-]?\s*[^;\n]+",
    "EMPLOYEE_NUMBER": r"\b(?:employee|emp)\s*(?:number|no|id)\s*[:#=-]?\s*[A-Z0-9/-]+",
    "PAYROLL_ID": r"\bpayroll\s*(?:id|number|no)\s*[:#=-]?\s*[A-Z0-9/-]+",
}

