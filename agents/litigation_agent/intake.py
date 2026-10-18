"""Read explicit, contract-level inputs for Litigation Exposure inference."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .agent import LexState


FEATURE_ORDER = [
    "deal_size",
    "liability_cap",
    "auto_renewal",
    "jurisdiction_risk",
    "conflict_flag",
    "clause_deviation_score",
    "indemnification_clause",
    "dispute_history",
    "governing_law_clarity",
]


def load_litigation_state(path: str | Path) -> LexState:
    """Load model inputs from the documented JSON intake format."""
    intake_path = Path(path)
    with intake_path.open("r", encoding="utf-8") as stream:
        payload: Any = json.load(stream)

    return parse_litigation_payload(payload)


def parse_litigation_payload(payload: Any) -> LexState:
    """Validate a parsed JSON intake object for CLI or programmatic use."""

    if not isinstance(payload, dict):
        raise ValueError("Litigation intake JSON must contain an object.")

    entities = payload.get("entities", {})
    graph_results = payload.get("graph_results", {})
    if not isinstance(entities, dict):
        raise ValueError("'entities' must be a JSON object.")
    if not isinstance(graph_results, dict):
        raise ValueError("'graph_results' must be a JSON object.")

    return LexState(
        contract_text=str(payload.get("contract_text", "")),
        entities=entities,
        graph_results=graph_results,
        clause_deviation_score=payload.get("clause_deviation_score"),
    )


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.;!?])\s+|\n+", text) if part.strip()]


def _detect_clause_flag(clause: str, feature: str) -> tuple[float | None, str | None]:
    """Detect only explicit wording; absence in one clause is not proof of absence in a contract."""
    sentences = _sentences(clause)
    for sentence in sentences:
        lower = sentence.lower()
        if feature == "liability_cap":
            if re.search(r"\b(?:no|without)\s+(?:overall\s+|aggregate\s+)?liability\s+cap\b", lower):
                return 0.0, sentence
            if re.search(
                r"\b(?:total|aggregate|maximum|overall)\s+liability\b.{0,180}"
                r"\b(?:not\s+exceed|limited\s+to|capped\s+at|cap\s+of)\b",
                lower,
            ) or re.search(r"\bliability\s+cap\b", lower):
                return 1.0, sentence

        if feature == "auto_renewal":
            if re.search(
                r"\b(?:does\s+not|shall\s+not|will\s+not|may\s+not)\s+"
                r"(?:automatically\s+renew|renew\s+automatically)\b|"
                r"\bno\s+automatic\s+renewal\b",
                lower,
            ):
                return 0.0, sentence
            if re.search(r"\b(?:automatically\s+renew|automatic\s+renewal)\b", lower):
                return 1.0, sentence

    return None, None


def _ask_binary(
    feature: str,
    question: str,
    inferred: float | None = None,
    evidence: str | None = None,
) -> tuple[float | None, str]:
    if inferred is not None:
        print(f"Detected {feature}: {'yes' if inferred else 'no'}")
        print(f"Clause evidence: {evidence}")
        prompt = "Confirm? [Enter=yes, n=no, u=unknown]: "
    else:
        print(question)
        prompt = "Answer yes / no / unknown: "

    while True:
        answer = input(prompt).strip().lower()
        if answer == "" and inferred is not None:
            return inferred, f"clause text: {evidence}"
        if answer in {"y", "yes"}:
            return 1.0, "user confirmed"
        if answer in {"n", "no"}:
            return 0.0, "user provided"
        if answer in {"u", "unknown", "unsure"}:
            return None, "not provided"
        print("Enter yes, no, or unknown.")


def _ask_number(
    feature: str,
    question: str,
    minimum: float,
    maximum: float,
    integer: bool = False,
) -> tuple[float | None, str]:
    print(question)
    while True:
        answer = input(f"{feature} [{minimum:g}–{maximum:g}, or unknown]: ").strip().lower()
        if answer in {"u", "unknown", "unsure"}:
            return None, "not provided"
        try:
            value = float(answer.replace(",", ""))
        except ValueError:
            print("Enter a number or unknown.")
            continue
        if not math.isfinite(value) or not minimum <= value <= maximum:
            print(f"Value must be between {minimum:g} and {maximum:g}.")
            continue
        if integer and not value.is_integer():
            print("Enter a whole number.")
            continue
        return value, "user provided"


def _run_coi() -> tuple[float | None, str]:
    """Obtain conflict_flag only from a complete COI graph analysis."""
    doc_id = input("COI graph document ID: ").strip()
    client = input("Client entity name: ").strip()
    counterparty = input("Counterparty entity name: ").strip()
    if not (doc_id and client and counterparty):
        print("COI requires a document ID, client, and counterparty; conflict remains unknown.")
        return None, "COI inputs missing"

    try:
        from agents.coi import ConflictOfInterestAgent

        report = ConflictOfInterestAgent().run(
            doc_id=doc_id,
            client_entity=client,
            counterparty_entity=counterparty,
        )
    except Exception as exc:
        print(f"COI unavailable ({type(exc).__name__}); conflict remains unknown.")
        return None, "COI unavailable"

    if report.status != "complete" or report.conflict_flag is None:
        print(f"COI result is {report.status}; conflict remains unknown ({report.skipped_reason or 'incomplete evidence'}).")
        return None, f"COI {report.status}"

    print(f"COI completed: conflict {'detected' if report.conflict_flag else 'not detected'}.")
    return float(report.conflict_flag), "COI graph result"


def collect_litigation_state(clause: str) -> tuple[LexState, dict[str, str], list[str]]:
    """Collect validated LE features through simple prompts, not user-edited JSON."""
    print("\nLITIGATION EXPOSURE INTAKE")
    print("Answer from known deal facts. Type 'unknown' when you cannot support an answer.")
    print("Unknown required features will skip LE scoring; they will not be guessed.\n")

    values: dict[str, float | None] = {}
    sources: dict[str, str] = {}

    inferred, evidence = _detect_clause_flag(clause, "liability_cap")
    values["liability_cap"], sources["liability_cap"] = _ask_binary(
        "liability_cap",
        "Does the agreement contain a liability cap? Consider the full agreement if this clause is silent.",
        inferred,
        evidence,
    )

    inferred, evidence = _detect_clause_flag(clause, "auto_renewal")
    values["auto_renewal"], sources["auto_renewal"] = _ask_binary(
        "auto_renewal",
        "Does the agreement automatically renew? Consider the full agreement.",
        inferred,
        evidence,
    )

    values["deal_size"], sources["deal_size"] = _ask_number(
        "deal_size",
        "Enter the deal size in USD, as expected by the model.",
        50_000,
        5_000_000,
    )

    values["jurisdiction_risk"], sources["jurisdiction_risk"] = _ask_number(
        "jurisdiction_risk",
        "Enter the project-defined jurisdiction risk score. The ZIP has no scoring rubric; use unknown if you do not have one.",
        1,
        10,
        integer=True,
    )

    values["conflict_flag"], sources["conflict_flag"] = _run_coi()

    values["clause_deviation_score"], sources["clause_deviation_score"] = _ask_number(
        "clause_deviation_score",
        "Enter a measured score from an approved-playbook comparison, or unknown if unavailable.",
        0,
        1,
    )

    values["indemnification_clause"], sources["indemnification_clause"] = _ask_binary(
        "indemnification_clause",
        "Does the agreement provide a strong, clearly scoped indemnity?",
    )

    values["dispute_history"], sources["dispute_history"] = _ask_binary(
        "dispute_history",
        "Has this counterparty had prior disputes with you?",
    )

    values["governing_law_clarity"], sources["governing_law_clarity"] = _ask_number(
        "governing_law_clarity",
        "Rate governing-law clarity: 1=vague or contested; 5=clear and predictable.",
        1,
        5,
        integer=True,
    )

    print("\nFEATURE REVIEW")
    for feature in FEATURE_ORDER:
        value = values[feature]
        display = "UNKNOWN" if value is None else f"{value:g}"
        print(f"- {feature}: {display} (source: {sources[feature]})")

    missing = [feature for feature in FEATURE_ORDER if values[feature] is None]
    if missing:
        return _build_state(values), sources, missing

    while True:
        confirmation = input("Use these values for LE scoring? [Y/n]: ").strip().lower()
        if confirmation in {"", "y", "yes"}:
            return _build_state(values), sources, []
        if confirmation in {"n", "no"}:
            print("Re-enter the intake values.\n")
            return collect_litigation_state(clause)
        print("Enter yes or no.")


def _build_state(values: dict[str, float | None]) -> LexState:
    return LexState(
        entities={
            key: values[key]
            for key in (
                "deal_size",
                "liability_cap",
                "auto_renewal",
                "jurisdiction_risk",
                "indemnification_clause",
                "dispute_history",
                "governing_law_clarity",
            )
        },
        graph_results={"conflict_flag": values["conflict_flag"]},
        clause_deviation_score=values["clause_deviation_score"],
    )
