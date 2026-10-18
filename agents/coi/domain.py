"""Shared COI vocabulary and validated records."""
from __future__ import annotations

from enum import Enum
from typing import Literal
import unicodedata
import re
from pydantic import BaseModel, ConfigDict, Field

TRIGGERS = {"LITIGATING_AGAINST": "HIGH", "DISPUTE_WITH": "MEDIUM",
            "COMPETES_WITH": "MEDIUM", "SHARED_DIRECTOR": "LOW"}
BRIDGES = {"SUBSIDIARY_OF", "PARENT_OF", "AFFILIATED_WITH", "PARTNER_OF",
           "CONTRACT_WITH", "JOINT_VENTURE_WITH", "MERGED_WITH", "ACQUIRES",
           "REPRESENTS", "AGENT_OF", "BOARD_MEMBER_OF", "CEO_OF", "FOUNDER_OF",
           "MANAGER_OF", "MANAGES", "OWNS", "SHAREHOLDER_OF"}
TRAVERSABLE_RELATIONSHIPS = set(TRIGGERS) | BRIDGES
ENTITY_RELATIONSHIPS = TRAVERSABLE_RELATIONSHIPS | {
    "AGREES_WITH", "ASSIGNS_TO", "AUDITS", "BORROWS_FROM", "CLIENT_OF",
    "CONSULTANT_FOR", "DELIVERS_TO", "DEVELOPS_FOR", "DIRECTS", "DISTRIBUTES_FOR",
    "EMPLOYS", "FINANCES", "GUARANTEES", "HEADQUARTERED_IN", "INDEMNIFIES",
    "INFRINGES", "INSURES", "INVESTS_IN", "LEASES_TO", "LENDS_TO", "LICENSES_TO",
    "LOCATED_IN", "MANAGES", "MANUFACTURES_FOR", "OCCUPIES", "OWNS_IP", "PAYS",
    "PROVIDES_SERVICES_TO", "RELATED_TO", "RENEWS_WITH", "RENTS_FROM",
    "SUBCONTRACTS_TO", "SUBLEASES_TO", "SUPPLIES_TO", "TERMINATES", "USES_FOR",
    "VENDORS_TO", "WARRANTS_TO"}


def entity_key(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Entity names must be non-empty strings")
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def entity_match_key(name: str) -> str:
    """Normalize punctuation differences for matching extracted party names."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Entity names must be non-empty strings")
    normalized = unicodedata.normalize("NFKC", name).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str
    target: str
    type: str
    doc_id: str
    clause_id: str
    evidence: str = ""
    verified: bool = False
    valid_from: str | None = None
    valid_until: str | None = None


class ConflictReport(BaseModel):
    conflict_detected: bool = False
    conflict_path: list[str] = Field(default_factory=list)
    severity: str = "UNKNOWN"
    status: Literal["complete", "unknown", "incomplete", "unavailable"] = "complete"
    skipped_reason: str | None = None
    unresolved_entities: list[str] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    review_required: bool = True
    run_metadata: dict = Field(default_factory=dict)

    @property
    def conflict_flag(self) -> int | None:
        return int(self.conflict_detected) if self.status == "complete" else None

    def to_dict(self) -> dict:
        return {**self.model_dump(), "conflict_flag": self.conflict_flag}

    def to_lex_state_update(self) -> dict:
        return {**self.to_dict(), "graph_results": self.to_dict()}
