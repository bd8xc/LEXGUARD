"""Document-level confidentiality and privacy analysis over LDI clauses."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .classifier import classify_findings
from .detectors import ConfidentialBusinessDetector, NERDetector, PIIDetector, ProcessingActivityDetector, RegexDetector, SensitivePersonalDetector
from .schemas import ConfidentialityReport, DocumentIndexItem, SensitiveFinding
from .scorer import score_confidentiality


class _LazyClauseVectorStore:
    """Defer the standalone Chroma dependency until indexed data is requested."""

    def __init__(self) -> None:
        self._store: Any | None = None

    def _get(self) -> Any:
        if self._store is None:
            try:
                from ingestion_pipeline.ldi.embeddings.vector_store import ClauseVectorStore
            except ImportError as exc:
                raise RuntimeError("ChromaDB is required to read indexed LDI documents; pass clauses for direct analysis.") from exc
            self._store = ClauseVectorStore()
        return self._store

    def get_document_clauses(self, file_name: str) -> list[dict[str, Any]]:
        return self._get().get_document_clauses(file_name)

    def list_documents(self) -> list[dict[str, Any]]:
        return self._get().list_documents()


class ConfidentialityLeakageAgent:
    """Aggregate independent DLP detectors over clauses already produced by LDI."""

    def __init__(self, vector_store: Any | None = None) -> None:
        # Direct clause analysis does not need LDI/ChromaDB. Load that optional
        # dependency only when callers ask this agent to read the standalone index.
        self._vector_store = vector_store or _LazyClauseVectorStore()
        self._detectors = (RegexDetector(), PIIDetector(), SensitivePersonalDetector(), ConfidentialBusinessDetector(), NERDetector())
        self._processing_detector = ProcessingActivityDetector()

    def _load_clauses_for_document(self, file_name: str) -> list[dict[str, Any]]:
        clauses = self._vector_store.get_document_clauses(file_name)
        if not clauses:
            raise LookupError(f"No embedded clauses found for '{file_name}'. Index the document first, then retry with the same file name.")
        return clauses

    def list_documents(self) -> list[DocumentIndexItem]:
        return [DocumentIndexItem(**item) for item in self._vector_store.list_documents()]

    def analyze(self, doc_id: str, clauses: list[dict[str, Any]] | None = None) -> ConfidentialityReport:
        all_findings: list[dict[str, Any]] = []
        activities: list[dict[str, Any]] = []
        clause_rows = clauses if clauses is not None else self._load_clauses_for_document(doc_id)
        for clause in clause_rows:
            text = str(clause.get("text", "") or "")
            metadata = {"clause_id": str(clause.get("clause_id") or ""), "section": str(clause.get("section") or "")}
            detected = [finding for detector in self._detectors for finding in detector.detect(text, metadata)]
            all_findings.extend(classify_findings(detected, **metadata))
            activities.extend({**activity, **metadata} for activity in self._processing_detector.detect(text, metadata))

        score = score_confidentiality(all_findings, processing_activity_count=len(activities))
        public_findings = []
        for finding in all_findings:
            public = dict(finding)
            public_findings.append(SensitiveFinding(**public))

        sensitivity_counts = Counter(finding["sensitivity"] for finding in all_findings)
        category_counts = Counter(finding.get("category", "personal_data") for finding in all_findings)
        return ConfidentialityReport(
            doc_id=doc_id,
            sensitive_data_detected=bool(all_findings),
            risk_score=int(score["risk_score"]),
            risk_level=str(score["risk_level"]),
            total_findings=len(public_findings),
            high_sensitivity_count=sensitivity_counts.get("HIGH", 0),
            medium_sensitivity_count=sensitivity_counts.get("MEDIUM", 0),
            context_dependent_count=sensitivity_counts.get("CONTEXT_DEPENDENT", 0),
            findings=public_findings,
            summary={
                "personal_data": category_counts.get("personal_data", 0),
                "sensitive_personal_data": category_counts.get("sensitive_personal_data", 0),
                "business_confidential": category_counts.get("business_confidential", 0),
                "processing_activities": len(activities),
            },
            processing_activity=activities,
        )
