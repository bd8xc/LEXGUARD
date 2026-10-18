"""Turn extracted contract text into clause-scoped, unverified COI graph facts."""
from __future__ import annotations

import re
from typing import Any

from agents.cl.confidentiality_leakage.detectors.ner_detector import NERDetector
from agents.coi.domain import entity_key


_LABELS = {"ORG": "Company", "PERSON": "Person", "GPE": "Location", "LOC": "Location"}
_NON_NAME_WORDS = {"agreement", "contract", "schedule", "section", "article", "clause", "terms"}
# The spaCy model is optional and can omit legal names. Match common legal
# suffixes explicitly so ingestion still finds companies in minimal installs.
_LEGAL_NAME = re.compile(
    r"\b(?:[A-Z][\w&'-]*\s+){1,7}"
    r"(?:Pvt\.?\s+Ltd\.?|Private\s+Limited|Ltd\.?|Limited|Inc\.?|"
    r"Corp\.?|Corporation|LLP|LLC)\b\.?")
_SENTENCE_BREAK = re.compile(r"(?<=[!?;])\s+|\n+")
_NEGATION = re.compile(r"\b(?:not|never|neither|no\s+longer)\b", re.I)

# A relationship is created only when the text between two named entities
# actually states one. The direction is relative to their order in the text.
_RELATIONS = (
    (re.compile(r"\b(?:is|was|are|were)\s+(?:an?\s+|the\s+)?subsidiary\s+of\b", re.I), "SUBSIDIARY_OF", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+(?:the\s+)?parent\s+(?:company\s+)?of\b", re.I), "PARENT_OF", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+(?:an?\s+)?affiliate\s+of\b", re.I), "AFFILIATED_WITH", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+(?:an?\s+)?(?:director|board\s+member)\s+of\b", re.I), "BOARD_MEMBER_OF", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+(?:the\s+)?(?:chief\s+executive\s+officer|CEO)\s+of\b", re.I), "CEO_OF", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+(?:an?\s+|the\s+)?founder\s+of\b", re.I), "FOUNDER_OF", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+(?:an?\s+|the\s+)?(?:manager|managing\s+director)\s+of\b", re.I), "MANAGER_OF", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+owned\s+by\b", re.I), "OWNS", -1),
    (re.compile(r"\b(?:owns|owned|holds?\s+(?:shares?|equity)\s+in)\b", re.I), "OWNS", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+represented\s+by\b", re.I), "REPRESENTS", -1),
    (re.compile(r"\b(?:represents?|represented)\b", re.I), "REPRESENTS", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+employed\s+by\b", re.I), "EMPLOYS", -1),
    (re.compile(r"\b(?:employs?|employed)\b", re.I), "EMPLOYS", 1),
    (re.compile(r"\b(?:suppl(?:y|ies|ied)(?:\s+(?:goods|services))?(?:\s+to)?|provides?\s+(?:goods|services)\s+to)\b", re.I), "SUPPLIES_TO", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+(?:a\s+)?supplier\s+to\b", re.I), "SUPPLIES_TO", 1),
    (re.compile(r"\b(?:licenses?|licensed)\s+(?:\w+\s+){0,3}to\b", re.I), "LICENSES_TO", 1),
    (re.compile(r"\b(?:is|was|are|were)\s+litigating\s+against\b", re.I), "LITIGATING_AGAINST", 1),
    (re.compile(r"\b(?:competes?|competed)\s+with\b", re.I), "COMPETES_WITH", 1),
    (re.compile(r"\b(?:has|have|had)\s+(?:a\s+)?dispute\s+with\b", re.I), "DISPUTE_WITH", 1),
    (re.compile(r"\b(?:partners?\s+with|partnered\s+with)\b", re.I), "PARTNER_OF", 1),
    (re.compile(r"\b(?:contracts?\s+with|contracted\s+with|entered\s+into\s+an?\s+agreement\s+with)\b", re.I), "CONTRACT_WITH", 1),
)


def _mentions(text: str) -> list[dict[str, Any]]:
    found = []
    for item in NERDetector().detect(text):
        if item.get("type") in _LABELS:
            words = {word.casefold() for word in re.findall(r"[A-Za-z]+", item["value"])}
            if item["type"] == "PERSON" and (words & _NON_NAME_WORDS or words & {"this", "that", "these", "those"}):
                continue
            found.append({"name": item["value"].strip(), "label": _LABELS[item["type"]],
                          "start": item["start"], "end": item["end"]})
    for match in _LEGAL_NAME.finditer(text):
        found = [item for item in found if item["end"] <= match.start() or item["start"] >= match.end()]
        found.append({"name": match.group().strip(), "label": "Company",
                      "start": match.start(), "end": match.end()})
    return sorted(found, key=lambda item: (item["start"], -item["end"]))


def clauses_to_graph_facts(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract named nodes and explicitly stated, clause-local relationships."""
    graph_clauses = []
    for clause in clauses:
        text = str(clause.get("text") or "")
        mentions = _mentions(text)
        entities = {entity_key(item["name"]): {"name": item["name"], "label": item["label"]}
                    for item in mentions}
        relationships = []
        seen = set()
        boundaries = [0, *[match.end() for match in _SENTENCE_BREAK.finditer(text)], len(text)]
        for left_bound, right_bound in zip(boundaries, boundaries[1:]):
            local = [item for item in mentions if left_bound <= item["start"] and item["end"] <= right_bound]
            for left, right in zip(local, local[1:]):
                if entity_key(left["name"]) == entity_key(right["name"]):
                    continue
                between = text[left["end"]:right["start"]]
                if len(between) > 120 or _NEGATION.search(between) or re.search(r"[;!?]|\.(?:\s|$)", between):
                    continue
                for pattern, kind, direction in _RELATIONS:
                    if pattern.search(between):
                        source, target = (left, right) if direction == 1 else (right, left)
                        identity = (entity_key(source["name"]), entity_key(target["name"]), kind)
                        if identity not in seen:
                            seen.add(identity)
                            relationships.append({
                                "from": source["name"], "to": target["name"],
                                "type": kind, "verified": False,
                                "evidence": text[left["start"]:right["end"]].strip(),
                            })
                        break
                else:
                    # Explicitly named parties to an agreement form a contract
                    # connection, without treating arbitrary co-mentions as edges.
                    prefix = text[max(left_bound, left["start"] - 32):left["start"]]
                    if re.fullmatch(r"\s+and\s+", between, re.I) and re.search(r"\bbetween\s*$", prefix, re.I):
                        identity = (entity_key(left["name"]), entity_key(right["name"]), "CONTRACT_WITH")
                        if identity not in seen:
                            seen.add(identity)
                            relationships.append({
                                "from": left["name"], "to": right["name"],
                                "type": "CONTRACT_WITH", "verified": False,
                                "evidence": text[max(left_bound, left["start"] - 32):right["end"]].strip(),
                            })
        graph_clauses.append({"clause_id": str(clause["clause_id"]), "text": text,
                              "entities": list(entities.values()), "relationships": relationships})
    return graph_clauses
