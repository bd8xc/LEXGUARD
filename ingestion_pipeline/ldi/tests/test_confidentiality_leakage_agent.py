from __future__ import annotations

from agents.cl.confidentiality_leakage.agent import ConfidentialityLeakageAgent
from agents.cl.confidentiality_leakage.classifier import (
    CONTEXT_TYPES,
    CRITICAL_TYPES,
    HIGH_TYPES,
    LOW_TYPES,
    MEDIUM_TYPES,
    classify_findings,
    sensitivity_for_detection,
)
from agents.cl.confidentiality_leakage.detectors.confidential_business_detector import detect_confidential_content
from agents.cl.confidentiality_leakage.detectors.ner_detector import detect_ner_sensitive_info
from agents.cl.confidentiality_leakage.detectors.pii_detector import PIIDetector
from agents.cl.confidentiality_leakage.detectors.processing_activity_detector import ProcessingActivityDetector
from agents.cl.confidentiality_leakage.detectors.regex_detector import detect_regex_sensitive_info
from agents.cl.confidentiality_leakage.detectors.sensitive_personal_detector import SensitivePersonalDetector
from agents.cl.confidentiality_leakage.scorer import score_confidentiality


def test_email_detection():
    detections = detect_regex_sensitive_info("Contact john.doe@example.com for details.")
    assert any(item["type"] == "EMAIL" for item in detections)


def test_email_is_not_misclassified_as_upi_id():
    detections = detect_regex_sensitive_info("Contact john.doe@example.com for details.")
    assert not any(item["type"] == "UPI_ID" for item in detections)


def test_labelled_upi_id_is_detected():
    detections = detect_regex_sensitive_info("UPI ID: dhruv@okaxis")
    assert any(item["type"] == "UPI_ID" for item in detections)


def test_phone_detection():
    detections = detect_regex_sensitive_info("Call +91 98765 43210 today.")
    assert any(item["type"] == "PHONE_NUMBER" for item in detections)


def test_pan_detection():
    detections = detect_regex_sensitive_info("PAN is ABCDE1234F.")
    assert any(item["type"] == "PAN_NUMBER" for item in detections)


def test_aadhaar_detection():
    detections = detect_regex_sensitive_info("Aadhaar: 1234 5678 9012")
    assert any(item["type"] == "AADHAAR_NUMBER" for item in detections)


def test_postal_code_detection():
    detections = detect_regex_sensitive_info("Office location pin is 400013.")
    assert any(item["type"] == "POSTAL_CODE" for item in detections)


def test_address_detection():
    text = "Registered office at 95 Ganpatrao Kadam Marg, Lower Parel, Mumbai 400013"
    detections = PIIDetector().detect(text)
    assert any(item["type"] == "ADDRESS" for item in detections)


def test_swift_ignores_uppercase_contract_words():
    detections = detect_regex_sensitive_info("OBLIGATIONS DELIVERY CONFORMANCE TERMINATION")
    assert not any(item["type"] == "SWIFT" for item in detections)


def test_swift_keeps_labelled_bic():
    detections = detect_regex_sensitive_info("SWIFT: DEUTDEFF500")
    assert any(item["type"] == "SWIFT" and "DEUTDEFF500" in item["value"] for item in detections)


def test_address_does_not_capture_legal_introduction_without_address():
    detections = PIIDetector().detect("This agreement is between Vendor and XYZ Private Limited, whose registered office is in India.")
    assert not any(item["type"] == "ADDRESS" for item in detections)


def test_address_keeps_numeric_street_address():
    detections = PIIDetector().detect("Registered office at 95 Ganpatrao Kadam Marg, Lower Parel, Mumbai 400013")
    assert any(item["type"] == "ADDRESS" for item in detections)


def test_valid_credit_card_detection_using_luhn():
    detections = detect_regex_sensitive_info("Card 4111 1111 1111 1111 is listed.")
    assert any(item["type"] == "CREDIT_CARD" for item in detections)


def test_invalid_credit_card_like_number_rejection():
    detections = detect_regex_sensitive_info("Card 4111 1111 1111 1112 is listed.")
    assert all(item["type"] != "CREDIT_CARD" for item in detections)


def test_ambiguous_identifiers_require_contextual_labels():
    detections = detect_regex_sensitive_info("Reference 123456789012 and code A1234567 in clause 4.")
    assert not {item["type"] for item in detections}.intersection({"AADHAAR_NUMBER", "PASSPORT_NUMBER"})


def test_network_identifier_keeps_labelled_ip_address():
    detections = detect_regex_sensitive_info("Application server IP address: 192.168.1.10")
    assert any(item["type"] == "IP_ADDRESS" for item in detections)


def test_ner_rejects_street_names_and_contract_deadlines():
    detections = detect_ner_sensitive_info("95 Ganpatrao Kadam Marg is available within thirty days.")
    assert not any(item["type"] == "PERSON" and "Kadam Marg" in item["value"] for item in detections)
    assert not any(item["type"] == "DATE" and "thirty days" in item["value"].lower() for item in detections)


def test_person_ner_detection():
    detections = detect_ner_sensitive_info("John Doe signed the agreement.")
    assert any(item["type"] == "PERSON" for item in detections)


def test_org_context_dependent_detection():
    detections = detect_ner_sensitive_info("Acme Corporation approved the change.")
    assert any(item["type"] == "ORG" for item in detections)


def test_ner_filters_legal_boilerplate_terms():
    detections = detect_ner_sensitive_info("Confidential Information may be shared only for the Purpose by the Party.")
    values = {item["value"].lower() for item in detections}
    assert "confidential information" not in values
    assert "purpose" not in values
    assert "party" not in values


def test_ner_filters_generic_roles_and_placeholders():
    detections = detect_ner_sensitive_info("Vendor XYZ Private Limited Force Majeure Neither Party")
    values = {item["value"].lower() for item in detections}
    assert not values.intersection({"vendor", "xyz", "private limited", "force majeure", "neither party"})


def test_ner_keeps_genuine_person_and_company_entities():
    detections = detect_ner_sensitive_info("John Doe signed for TATA DIGITAL PRIVATE LIMITED.")
    values = {item["value"] for item in detections}
    assert "John Doe" in values or any("John Doe" in value for value in values)
    assert any("TATA DIGITAL PRIVATE LIMITED" in value for value in values)


def test_ner_filters_address_phrase_from_person():
    detections = detect_ner_sensitive_info("95 Ganpatrao Kadam Marg, Lower Parel, Mumbai")
    assert not any(item["type"] == "PERSON" and "Kadam Marg" in item["value"] for item in detections)


def test_ner_keeps_real_company_names():
    detections = detect_ner_sensitive_info("TATA DIGITAL PRIVATE LIMITED and STAR INDIA PRIVATE LIMITED signed.")
    org_values = [item["value"] for item in detections if item["type"] == "ORG"]
    assert any("TATA DIGITAL PRIVATE LIMITED" in value for value in org_values)


def test_regex_legal_entity_detection_for_company_names():
    detections = detect_regex_sensitive_info("Agreement between STAR INDIA PRIVATE LIMITED and TATA DIGITAL PRIVATE LIMITED")
    org_values = [item["value"] for item in detections if item["type"] == "ORG"]
    assert any("STAR INDIA PRIVATE LIMITED" in value for value in org_values)


def test_confidential_content_detection():
    detections = detect_confidential_content("This includes business plans, trade secret material, and customer lists.")
    types = {item["type"] for item in detections}
    assert "CONFIDENTIAL_STRATEGY" in types
    assert "CONFIDENTIAL_TRADE_SECRET" in types
    assert "CONFIDENTIAL_CUSTOMER" in types


def test_sensitive_personal_detector_distinguishes_medical_context():
    detector = SensitivePersonalDetector()
    assert detector.detect("The parties discussed treatment of a contractual dispute.") == []
    findings = detector.detect("The employee's medical treatment records and diagnosis are restricted.")
    assert {finding["type"] for finding in findings} >= {"PRESCRIPTION", "DIAGNOSIS"}


def test_business_detector_requires_context_for_ambiguous_financial_terms():
    assert detect_confidential_content("The pricing was discussed during negotiations.") == []
    findings = detect_confidential_content("The confidential pricing model and revenue forecast are restricted.")
    assert {finding["type"] for finding in findings} >= {"CONFIDENTIAL_FINANCIAL"}


def test_processing_detector_ignores_non_data_contract_actions():
    assert ProcessingActivityDetector().detect("The Supplier shall transfer title and deliver goods.") == []


def test_processing_detector_ignores_vendor_without_data_handling():
    detections = ProcessingActivityDetector().detect("The Vendor shall deliver products within 30 days")
    assert detections == []


def test_processing_detector_finds_transfer_and_third_party():
    detections = ProcessingActivityDetector().detect(
        "The Vendor shall transfer employee bank details to a third party"
    )
    values = {item["activity"] for item in detections}
    assert values == {"transfer", "third party"}


def test_processing_detector_finds_inflected_data_handling_verb():
    detections = ProcessingActivityDetector().detect("Personal data must be stored securely")
    assert [item["activity"] for item in detections] == ["stored"]


def test_multiple_findings_in_one_clause():
    agent = ConfidentialityLeakageAgent()
    report = agent.analyze(
        "contract_001",
        [{"clause_id": "4.2", "section": "Employee Information", "text": "John Doe can be reached at john.doe@example.com."}],
    )
    assert report.total_findings >= 2


def test_response_values_follow_current_raw_value_contract():
    agent = ConfidentialityLeakageAgent()
    report = agent.analyze(
        "contract_003",
        [{"clause_id": "3.1", "section": "Contacts", "text": "Contact John Doe at john.doe@example.com or +91 98765 43210."}],
    )
    assert report.total_findings >= 2
    assert all(finding.value for finding in report.findings)


def test_duplicate_overlapping_finding_removal():
    findings = [
        {"type": "PERSON", "value": "John Doe", "source": "ner", "start": 0, "end": 8},
        {"type": "PERSON", "value": "John Doe", "source": "ner", "start": 0, "end": 8},
    ]
    classified = classify_findings(findings, clause_id="1", section="S")
    assert len(classified) == 1


def test_every_classifier_policy_type_has_one_explicit_sensitivity():
    groups = {
        "CRITICAL": CRITICAL_TYPES,
        "HIGH": HIGH_TYPES,
        "MEDIUM": MEDIUM_TYPES,
        "CONTEXT_DEPENDENT": CONTEXT_TYPES,
        "LOW": LOW_TYPES,
    }
    all_types = [detection_type for types in groups.values() for detection_type in types]
    assert len(all_types) == len(set(all_types))
    for sensitivity, types in groups.items():
        assert all(sensitivity_for_detection(detection_type) == sensitivity for detection_type in types)


def test_unknown_detection_type_is_retained_as_explicit_low_sensitivity():
    assert sensitivity_for_detection("UNSUPPORTED_DETECTOR_TYPE") == "LOW"
    finding = classify_findings(
        [{"type": "UNSUPPORTED_DETECTOR_TYPE", "value": "x", "source": "future", "start": 0, "end": 1}]
    )[0]
    assert finding["sensitivity"] == "LOW"


def test_context_entities_are_zero_risk_but_remain_findings():
    findings = classify_findings(
        [
            {"type": "DATE", "value": "30 days", "source": "ner", "start": 0, "end": 7},
            {"type": "ORG", "value": "Acme", "source": "ner", "start": 8, "end": 12},
            {"type": "LOC", "value": "Mumbai", "source": "ner", "start": 13, "end": 19},
        ]
    )
    assert len(findings) == 3
    assert all(item["sensitivity"] == "CONTEXT_DEPENDENT" for item in findings)
    assert score_confidentiality(findings)["risk_score"] == 0


def test_overlapping_ner_is_removed_when_structured_finding_exists():
    findings = classify_findings(
        [
            {"type": "ORG", "value": "Acme Corporation", "source": "ner", "start": 0, "end": 16},
            {"type": "CONFIDENTIAL_CUSTOMER", "value": "customer list", "source": "business", "start": 6, "end": 19},
        ]
    )
    assert [item["type"] for item in findings] == ["CONFIDENTIAL_CUSTOMER"]


def test_overlapping_structured_findings_are_both_preserved():
    findings = classify_findings(
        [
            {"type": "ADDRESS", "value": "12 Main Street 400013", "source": "pii", "start": 0, "end": 22},
            {"type": "POSTAL_CODE", "value": "400013", "source": "regex", "start": 16, "end": 22},
        ]
    )
    assert {item["type"] for item in findings} == {"ADDRESS", "POSTAL_CODE"}


def test_distinct_overlapping_structured_findings_are_preserved():
    findings = [
        {"type": "ADDRESS", "value": "12 Main Street, Mumbai 400013", "source": "pii", "start": 0, "end": 29},
        {"type": "POSTAL_CODE", "value": "400013", "source": "regex", "start": 23, "end": 29},
    ]
    classified = classify_findings(findings, clause_id="1", section="Address")
    assert {item["type"] for item in classified} == {"ADDRESS", "POSTAL_CODE"}


def test_empty_clause():
    agent = ConfidentialityLeakageAgent()
    report = agent.analyze("empty_doc", [{"clause_id": "1", "section": "S", "text": ""}])
    assert report.total_findings == 0
    assert report.sensitive_data_detected is False


def test_document_containing_no_sensitive_information():
    agent = ConfidentialityLeakageAgent()
    report = agent.analyze("clean_doc", [{"clause_id": "1", "section": "S", "text": "This agreement is effective upon signature."}])
    assert report.total_findings == 0
    assert report.risk_score == 0


def test_risk_score_calculation():
    score = score_confidentiality(
        [
            {"sensitivity": "HIGH"},
            {"sensitivity": "MEDIUM"},
            {"sensitivity": "CONTEXT_DEPENDENT"},
        ]
    )
    assert 0 <= score["risk_score"] <= 100
    assert score["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_context_heavy_findings_do_not_auto_become_critical():
    score = score_confidentiality([{"sensitivity": "CONTEXT_DEPENDENT"} for _ in range(60)])
    assert score["risk_score"] < 75
    assert score["risk_level"] in {"LOW", "MEDIUM", "HIGH"}


def test_high_sensitivity_findings_drive_higher_risk_than_context_only():
    context_only = score_confidentiality([{"sensitivity": "CONTEXT_DEPENDENT"} for _ in range(20)])
    with_high = score_confidentiality(
        [{"sensitivity": "HIGH"}, {"sensitivity": "HIGH"}] + [{"sensitivity": "CONTEXT_DEPENDENT"} for _ in range(5)]
    )
    assert with_high["risk_score"] > context_only["risk_score"]


def test_critical_findings_raise_risk_and_context_only_does_not():
    context_only = score_confidentiality([{"sensitivity": "CONTEXT_DEPENDENT"}])
    critical = score_confidentiality([{"sensitivity": "CRITICAL"}])
    assert context_only["risk_score"] == 0
    assert critical["risk_score"] > context_only["risk_score"]
    assert critical["risk_level"] != "LOW"


def test_multiple_clauses_preserve_clause_id_and_section():
    agent = ConfidentialityLeakageAgent()
    report = agent.analyze(
        "contract_002",
        [
            {"clause_id": "1", "section": "Alpha", "text": "john.doe@example.com"},
            {"clause_id": "2", "section": "Beta", "text": "Google approved the change."},
        ],
    )
    assert {finding.clause_id for finding in report.findings} == {"1", "2"}
    assert {finding.section for finding in report.findings} == {"Alpha", "Beta"}
