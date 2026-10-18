"""Bounded, evidence-preserving COI analysis; three hops by default."""
from __future__ import annotations

from collections import deque
from contextlib import nullcontext
from datetime import date
from itertools import combinations
from time import monotonic
from typing import Any

from neo4j.exceptions import Neo4jError, DriverError
from .domain import ConflictReport, TRIGGERS, entity_key, entity_match_key
from .graph_manager import GraphQueryError, SearchLimitError, get_graph

MAX_HOPS = 3
CONFLICT_TRIGGER_RELATIONSHIPS = set(TRIGGERS)
COIAgentError = GraphQueryError
RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


class ConflictOfInterestAgent:
    def __init__(self, *, graph=None, max_hops=3, max_entities=15,
                 max_expansions=10000, max_findings=500, max_neighbors=200, timeout=15):
        if not 1 <= max_hops <= 3:
            raise ValueError("max_hops must be between 1 and 3")
        if min(max_entities, max_expansions, max_findings, max_neighbors, timeout) <= 0:
            raise ValueError("Search limits must be positive")
        self.graph = graph
        self.max_hops = max_hops
        self.max_entities = max_entities
        self.max_expansions = max_expansions
        self.max_findings = max_findings
        self.max_neighbors = max_neighbors
        self.timeout = timeout

    def run(self, *, client_entity, counterparty_entity, doc_id,
            contract_entities=None, additional_entities=None, as_of=None):
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise ValueError("doc_id is required")
        names = [client_entity, counterparty_entity, *(contract_entities or []), *(additional_entities or [])]
        keys = sorted({entity_key(n) for n in names})
        requested_party_keys = {entity_key(client_entity), entity_key(counterparty_entity)}
        if len(requested_party_keys) != 2:
            raise ValueError("Client and counterparty must be different entities")
        day = date.fromisoformat(as_of) if as_of else date.today()
        start = monotonic()
        report = ConflictReport(run_metadata={"doc_id": doc_id, "as_of": day.isoformat(),
                                "max_hops": self.max_hops, "pairs_checked": 0, "expansions": 0,
                                "scope": "shared institutional graph"})
        findings = []
        try:
            if len(keys) > self.max_entities:
                raise SearchLimitError("entity_limit")
            graph = self.graph or get_graph()
            context = graph.read_view() if hasattr(graph, "read_view") else nullcontext(graph)
            with context as view:
                resolved = view.resolve_entities(names)
                resolved_by_match = {entity_match_key(name): key for key, name in resolved.items()}
                report.unresolved_entities = [n for n in names if entity_match_key(n) not in resolved_by_match]
                party_keys = {
                    resolved_by_match.get(entity_match_key(client_entity), entity_key(client_entity)),
                    resolved_by_match.get(entity_match_key(counterparty_entity), entity_key(counterparty_entity)),
                }
                if party_keys - resolved.keys():
                    report.status = "unknown"
                    report.skipped_reason = "entity_resolution_failed"
                else:
                    if report.unresolved_entities:
                        report.status = "incomplete"
                        report.skipped_reason = "some_contract_entities_unresolved"
                    cache = {}
                    for left, right in combinations(sorted(resolved), 2):
                        if not {left, right} & party_keys:
                            continue
                        queue = deque([([left], [])])
                        while queue:
                            nodes, edges = queue.popleft()
                            if monotonic() - start > self.timeout:
                                raise SearchLimitError("time_limit")
                            current = nodes[-1]
                            if current not in cache:
                                cache[current] = sorted(view.get_neighbors(current, as_of=day.isoformat(), limit=self.max_neighbors),
                                    key=lambda e: (e.source, e.target, e.type, e.doc_id, e.clause_id))
                            for edge in cache[current]:
                                report.run_metadata["expansions"] += 1
                                if report.run_metadata["expansions"] > self.max_expansions:
                                    raise SearchLimitError("expansion_limit")
                                neighbor = edge.target if edge.source == current else edge.source
                                if neighbor in nodes:
                                    continue
                                next_nodes, next_edges = nodes + [neighbor], edges + [edge]
                                if neighbor == right:
                                    triggers = [TRIGGERS[e.type] for e in next_edges if e.type in TRIGGERS]
                                    if triggers:
                                        if len(findings) >= self.max_findings:
                                            raise SearchLimitError("finding_limit")
                                        path = [next_nodes[0]]
                                        for e, node in zip(next_edges, next_nodes[1:]):
                                            path.extend([e.type, node])
                                        findings.append({"path": path, "severity": max(triggers, key=RANK.get),
                                            "verified": all(e.verified for e in next_edges),
                                            "evidence": [e.model_dump() for e in next_edges]})
                                elif len(next_edges) < self.max_hops:
                                    # Path-local cycle checks retain alternate evidence and visited-node histories.
                                    queue.append((next_nodes, next_edges))
                        report.run_metadata["pairs_checked"] += 1
        except SearchLimitError as exc:
            report.status, report.skipped_reason = "incomplete", str(exc)
        except (GraphQueryError, Neo4jError, DriverError, OSError):
            report.status, report.skipped_reason = "unavailable", "graph_unavailable"
        findings.sort(key=lambda f: (not f["verified"], -RANK[f["severity"]], len(f["path"]), str(f)))
        report.findings = findings
        if findings:
            report.conflict_detected = True
            report.conflict_path = findings[0]["path"]
            report.severity = findings[0]["severity"]
            if not any(f["verified"] for f in findings) and report.status == "complete":
                report.status = "unknown"
                report.skipped_reason = "unverified_conflict_evidence"
        elif report.status == "complete":
            report.severity = "NONE"
        report.review_required = report.status != "complete" or report.conflict_detected
        report.run_metadata.update(duration_ms=round((monotonic() - start) * 1000, 2), findings=len(findings))
        return report


def conflict_agent_node(state: dict[str, Any], agent=None):
    entities = state.get("entities") or {}
    report = (agent or ConflictOfInterestAgent()).run(
        client_entity=entities.get("client_entity") or entities.get("client") or entities.get("party_a") or "",
        counterparty_entity=entities.get("counterparty_entity") or entities.get("counterparty") or entities.get("party_b") or "",
        contract_entities=entities.get("contract_entities") or entities.get("all_entities") or [],
        doc_id=state.get("doc_id", ""), as_of=state.get("as_of"))
    return report.to_lex_state_update()
