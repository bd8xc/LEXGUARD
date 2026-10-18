"""Extract clause entities and produce a clause-level COI scan."""
from __future__ import annotations

import re
from typing import Any

from agents.cl.confidentiality_leakage.detectors.ner_detector import NERDetector


# Legal suffix plus a following defined role keeps ordinary prose from being
# swallowed into the party name (for example, "shall provide ... Client").
_DEFINED_PARTY = re.compile(
    r"(?P<name>(?:[A-Z][A-Za-z0-9&.'-]*\s+){1,7}"
    r"(?i:Pvt\.?\s+Ltd\.?|Private\s+Limited|Limited|Ltd\.?|Inc\.?|"
    r"Corporation|Corp\.?|LLP|LLC))\s*[\(\[][^\)\]]{0,16}"
    r"(?i:\b(?P<role>supplier|vendor|provider|client|customer|buyer|purchaser)\b)"
    r"[^\)\]]{0,16}[\)\]]"
)
_SHARED_DIRECTOR = re.compile(
    r"(?:the\s+)?(?P<role>supplier|vendor|provider|client|customer|buyer|purchaser)"
    r"(?:.{0,6}?s)?\s+director\s*,?\s*"
    r"(?P<person>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"
    r"\s*,?\s*(?:is|serves as)\s+(?:also\s+)?(?:a\s+)?director\s+of\s+"
    r"(?:the\s+)?(?P<other>[A-Z][A-Za-z0-9&.,'()\- ]{2,100}?)(?=[,.;]|\s+and\b|$)",
    re.IGNORECASE,
)


def scan_clause_for_coi(
    clause: str, *, doc_id: str = "interactive-clause", agent=None,
    parties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run NER over a clause, then use extracted entities in COI graph search.

    Clause text can independently provide a potential shared-director finding;
    it is labeled as clause evidence and is never treated as a verified graph edge.
    """
    entities = NERDetector().detect(clause)
    seen: set[tuple[str, str]] = set()
    extracted = []
    for entity in entities:
        identity = (entity["type"], entity["value"].casefold())
        if identity not in seen:
            seen.add(identity)
            extracted.append({"type": entity["type"], "name": entity["value"]})

    roles: dict[str, str] = {}
    for match in _DEFINED_PARTY.finditer(clause):
        role = match.group("role").casefold()
        party_type = "client" if role in {"client", "customer", "buyer", "purchaser"} else "counterparty"
        roles.setdefault(party_type, match.group("name").strip(" ,.;"))

    clause_findings = []
    entity_names = {item["name"].casefold(): item["name"] for item in extracted}
    for match in _SHARED_DIRECTOR.finditer(clause):
        person = match.group("person")
        if person.casefold() not in entity_names:
            continue
        other_name = re.sub(r"\s+", " ", match.group("other")).strip(" ,.;")
        client_name = roles.get("client", "")
        if (
            match.group("role").casefold() in {"supplier", "vendor", "provider"}
            and client_name
            and client_name.casefold() in other_name.casefold()
        ):
            clause_findings.append({
                "type": "POTENTIAL_SHARED_DIRECTOR",
                "severity": "LOW",
                "verified": False,
                "source": "clause_text",
                "person": entity_names[person.casefold()],
                "relationship": match.group(0),
                "evidence": match.group(0),
            })

    supplied_parties = parties or {}
    client_name = str(supplied_parties.get("client") or roles.get("client") or "").strip()
    counterparty_name = str(
        supplied_parties.get("counterparty") or roles.get("counterparty") or ""
    ).strip()
    extra_names = supplied_parties.get("additional", [])
    # Party names are user-supplied lookup hints; keep NER results in the search too.
    graph_entities = list(dict.fromkeys(
        [item["name"] for item in extracted] + extra_names
    ))

    graph_report = None
    graph_error = None
    if client_name and counterparty_name:
        try:
            graph_report = (agent or _default_agent()).run(
                client_entity=client_name,
                counterparty_entity=counterparty_name,
                contract_entities=graph_entities,
                doc_id=doc_id,
            ).to_dict()
        except Exception as exc:
            graph_error = type(exc).__name__

    return {
        "status": "complete" if clause_findings else (graph_report or {}).get("status", "unknown"),
        "entities": extracted,
        "party_roles": {
            **roles,
            **({"client": client_name} if client_name else {}),
            **({"counterparty": counterparty_name} if counterparty_name else {}),
            "additional": extra_names,
        },
        "clause_findings": clause_findings,
        "graph_result": graph_report,
        "graph_error": graph_error,
    }


def _default_agent():
    from .conflict_agent import ConflictOfInterestAgent

    return ConflictOfInterestAgent()
