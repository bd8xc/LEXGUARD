"""Pydantic schemas for confidentiality leakage detection."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class ClauseInput(BaseModel):
    """Incoming clause payload consumed by the agent."""

    model_config = ConfigDict(extra="ignore")

    doc_id: Optional[str] = None
    clause_id: Optional[str] = None
    level: Optional[str] = None
    text: str = ""
    section: Optional[str] = None


class ConfidentialityAnalyzeRequest(BaseModel):
    """Request body for the confidentiality analysis endpoint."""

    doc_id: str = Field(..., description="Source filename or document identifier from the embedded LDI index.")


class SensitiveFinding(BaseModel):
    """Normalized sensitive finding traceable to a clause."""

    model_config = ConfigDict(extra="ignore")

    type: str
    value: str
    source: str
    sensitivity: str
    category: str = "personal_data"
    clause_id: str = ""
    section: str = ""
    start: int
    end: int


class ConfidentialityReport(BaseModel):
    """Document-level confidentiality risk report."""

    doc_id: str
    sensitive_data_detected: bool
    risk_score: int = Field(ge=0, le=100)
    risk_level: str
    total_findings: int
    high_sensitivity_count: int
    medium_sensitivity_count: int
    context_dependent_count: int
    findings: List[SensitiveFinding]
    summary: dict[str, int] = Field(default_factory=lambda: {
        "personal_data": 0,
        "sensitive_personal_data": 0,
        "business_confidential": 0,
        "processing_activities": 0,
    })
    processing_activity: List[dict[str, Any]] = Field(default_factory=list)


class ClauseFinding(BaseModel):
    """Internal finding representation before traceability enrichment."""

    model_config = ConfigDict(extra="ignore")

    type: str
    value: str
    start: int
    end: int
    source: str


class DocumentIndexItem(BaseModel):
    """Embedded document identifier surfaced for user discovery."""

    doc_id: str
    document_hash: str = ""
