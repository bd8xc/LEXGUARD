"""FastAPI router for confidentiality leakage analysis."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .agent import ConfidentialityLeakageAgent
from .schemas import ConfidentialityAnalyzeRequest, ConfidentialityReport, DocumentIndexItem

router = APIRouter(prefix="/confidentiality", tags=["confidentiality"])
_agent = ConfidentialityLeakageAgent()


@router.post(
    "/analyze",
    response_model=ConfidentialityReport,
    responses={404: {"description": "Document not indexed or no clauses found for supplied doc_id."}},
)
def analyze_confidentiality(request: ConfidentialityAnalyzeRequest) -> ConfidentialityReport:
    """Analyze clause output produced by the existing LDI pipeline."""

    try:
        return _agent.analyze(request.doc_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents", response_model=list[DocumentIndexItem])
def list_embedded_documents() -> list[DocumentIndexItem]:
    """List embedded documents so users can choose a filename for analysis."""

    return _agent.list_documents()
