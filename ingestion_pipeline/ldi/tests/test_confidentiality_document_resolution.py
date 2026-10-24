from __future__ import annotations

from agents.cl.confidentiality_leakage.agent import ConfidentialityLeakageAgent


def test_analyze_resolves_clauses_from_filename(monkeypatch):
    agent = ConfidentialityLeakageAgent()

    monkeypatch.setattr(
        agent,
        "_load_clauses_for_document",
        lambda file_name: [
            {
                "clause_id": "P1",
                "section": "Document",
                "text": "John Doe can be reached at john.doe@example.com.",
            }
        ],
    )

    report = agent.analyze("NDA T2 (1).docx", None)

    assert report.doc_id == "NDA T2 (1).docx"
    assert report.total_findings >= 1
    assert report.sensitive_data_detected is True


def test_list_documents_returns_filenames(monkeypatch):
    agent = ConfidentialityLeakageAgent()

    monkeypatch.setattr(
        agent._vector_store,
        "list_documents",
        lambda: [
            {
                "doc_id": "NDA T2 (1).docx",
                "document_hash": "abc123",
            }
        ],
    )

    documents = agent.list_documents()

    assert documents[0].doc_id == "NDA T2 (1).docx"
