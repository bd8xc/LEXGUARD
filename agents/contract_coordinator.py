"""Run CR, CL, COI, and LE over one shared Ingestion Pipeline 2 split."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from ingestion_pipeline.document_input import extract_text
from ingestion_pipeline.ldi.chunking.clause_splitter import split_clauses

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = AGENT_ROOT / "cr" / "outputs"

LE_FEATURES = {
    "deal_size": ("Deal size in USD", 50_000, 5_000_000),
    "liability_cap": ("Liability cap / deal size", 0, 1),
    "auto_renewal": ("Auto renewal (0=no, 1=yes)", 0, 1),
    "jurisdiction_risk": ("Jurisdiction risk", 1, 10),
    "indemnification_clause": ("Indemnification present (0=no, 1=yes)", 0, 1),
    "dispute_history": ("Prior dispute history (0=no, 1=yes)", 0, 1),
    "governing_law_clarity": ("Governing law clarity (1=unclear, 5=clear)", 1, 5),
}


def _clause_id(clause: dict[str, Any], index: int) -> str:
    return str(clause.get("clause_id") or f"clause-{index:04d}")


def _emit_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    *,
    stage: str,
    message: str,
    percent: int,
    clause_index: int | None = None,
    clause_total: int | None = None,
    clause_id: str | None = None,
) -> None:
    """Print a progress update and optionally forward the same safe event."""
    event = {
        "stage": stage,
        "message": message,
        "percent": max(0, min(100, int(percent))),
    }
    if clause_index is not None:
        event["clause_index"] = clause_index
    if clause_total is not None:
        event["clause_total"] = clause_total
    if clause_id is not None:
        event["clause_id"] = clause_id

    print(message, flush=True)
    if progress_callback is not None:
        try:
            progress_callback(event)
        except Exception as exc:
            print(f"[progress publisher] Could not forward an update ({type(exc).__name__}).", flush=True)


def _mask_tree(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        for secret, masked in replacements.items():
            if secret:
                value = value.replace(secret, masked)
        return value
    if isinstance(value, list):
        return [_mask_tree(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _mask_tree(item, replacements) for key, item in value.items()}
    return value


@dataclass
class ContractAnalysisRuntime:
    """Heavy CR and India-law models held for the lifetime of the web process."""

    predictor: Any = None
    rag: Any = None
    llm_client: Any = None
    cr_error: str | None = None
    rag_error: str | None = None
    llm_error: str | None = None


def load_contract_runtime(
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ContractAnalysisRuntime:
    """Load CR and RAG once so the web backend can reuse them across uploads."""
    load_dotenv(ROOT / ".env")
    runtime = ContractAnalysisRuntime()
    checkpoint_candidates = (
        ROOT / "checkpoints" / "best_model.pt",
        AGENT_ROOT / "cr" / "checkpoints" / "best_model.pt",
    )
    checkpoint = next((candidate for candidate in checkpoint_candidates if candidate.is_file()), None)
    if checkpoint is None:
        expected = " or ".join(str(path) for path in checkpoint_candidates)
        runtime.cr_error = f"CR checkpoint not found; expected {expected}"
        _emit_progress(progress_callback, stage="cr_init", message="[Startup] CR checkpoint is unavailable.", percent=5)
        return runtime

    try:
        from agents.cr.models.inference import ContractRiskPredictor
        from agents.cr.rag.legal_rag import IndianLegalRAG
        from llm.local_llm import LocalLegalLLM
    except Exception as exc:
        runtime.cr_error = f"CR components could not import ({type(exc).__name__})."
        _emit_progress(progress_callback, stage="cr_init", message=f"[Startup] CR components unavailable ({type(exc).__name__}).", percent=90)
        return runtime

    try:
        _emit_progress(progress_callback, stage="cr_init", message="[Startup] Loading LegalBERT model...", percent=3)
        runtime.predictor = ContractRiskPredictor(checkpoint_path=str(checkpoint))
        _emit_progress(progress_callback, stage="cr_init", message="[Startup] LegalBERT model ready.", percent=25)
    except Exception as exc:
        runtime.cr_error = f"CR could not initialize ({type(exc).__name__})."
        _emit_progress(progress_callback, stage="cr_init", message=f"[Startup] CR unavailable ({type(exc).__name__}).", percent=90)
        return runtime

    try:
        _emit_progress(progress_callback, stage="rag_init", message="[Startup] Loading Indian Contract Act RAG and embeddings...", percent=30)
        runtime.rag = IndianLegalRAG(
            source_path=str(AGENT_ROOT / "cr" / "knowledge_base" / "processed" / "indian_contract_act_sections.json")
        )
        _emit_progress(progress_callback, stage="rag_init", message="[Startup] Indian Contract Act RAG is resident.", percent=85)
    except Exception as exc:
        runtime.rag_error = f"Indian Contract Act RAG unavailable ({type(exc).__name__})."
        _emit_progress(progress_callback, stage="rag_init", message=f"[Startup] RAG unavailable ({type(exc).__name__}).", percent=85)

    try:
        runtime.llm_client = LocalLegalLLM()
        _emit_progress(progress_callback, stage="llm_init", message=f"[Startup] LLM client ready for {runtime.llm_client.model_name}.", percent=90)
    except Exception as exc:
        runtime.llm_error = f"LLM client could not initialize ({type(exc).__name__})."
        _emit_progress(progress_callback, stage="llm_init", message=f"[Startup] LLM client unavailable ({type(exc).__name__}).", percent=90)
    _emit_progress(progress_callback, stage="ready", message="[Startup] Backend model warm-up complete.", percent=100)
    return runtime


def _run_cr(
    clauses: list[dict[str, Any]],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    runtime: ContractAnalysisRuntime | None = None,
) -> dict[str, Any]:
    try:
        runtime = runtime or load_contract_runtime(progress_callback)
        if runtime.predictor is None:
            return {"status": "unavailable", "reason": runtime.cr_error or "CR model is unavailable.", "clauses": []}
        predictor = runtime.predictor
        rag = runtime.rag
        rag_error = runtime.rag_error
        llm = runtime.llm_client
        llm_error = runtime.llm_error
        if llm is not None:
            _emit_progress(progress_callback, stage="llm_init", message="[LLM] Checking configured model connection...", percent=21)
            if not llm.check_connection():
                llm_error = "Configured LLM server is unavailable."
                llm = None
            else:
                _emit_progress(progress_callback, stage="llm_init", message=f"[LLM] Connected to {llm.model_name}.", percent=22)
        elif llm_error:
            _emit_progress(progress_callback, stage="llm_init", message=f"[LLM] {llm_error}", percent=22)

        rows = []
        clauses_to_analyze = [
            (index, clause)
            for index, clause in enumerate(clauses, start=1)
            if str(clause.get("text", "")).strip()
        ]
        total_clauses = len(clauses_to_analyze)
        for progress_index, (index, clause) in enumerate(clauses_to_analyze, start=1):
            text = str(clause.get("text", "")).strip()
            clause_id = _clause_id(clause, index)
            clause_percent = 22 + int(50 * (progress_index - 1) / max(total_clauses, 1))
            row: dict[str, Any] = {
                "clause_id": clause_id,
                "section": clause.get("section"),
                "clause": text,
            }
            _emit_progress(
                progress_callback,
                stage="cr",
                message=f"[CR] Clause {progress_index}/{total_clauses} ({clause_id}): running LegalBERT...",
                percent=clause_percent,
                clause_index=progress_index,
                clause_total=total_clauses,
                clause_id=clause_id,
            )
            try:
                hybrid_result = predictor.predict_hybrid(text)
                class_scores = hybrid_result.get("class_scores", {})
                model_result = {
                    "prediction": hybrid_result.get("model_display", hybrid_result.get("model_prediction", "Unknown")),
                    "raw_prediction": hybrid_result.get("model_prediction", "Unknown"),
                    "model_score": hybrid_result.get("model_score", 0.0),
                    "class_scores": {
                        ("Baseline" if str(label).lower() == "seed" else label): score
                        for label, score in class_scores.items()
                    },
                    "raw_class_scores": class_scores,
                    "num_windows": hybrid_result.get("num_windows"),
                }
                row["model"] = model_result
                row["hybrid"] = hybrid_result
                _emit_progress(
                    progress_callback,
                    stage="cr",
                    message=f"[CR] Clause {progress_index}/{total_clauses}: LegalBERT complete ({model_result['prediction']}).",
                    percent=clause_percent,
                    clause_index=progress_index,
                    clause_total=total_clauses,
                    clause_id=clause_id,
                )
            except Exception as exc:
                _emit_progress(
                    progress_callback,
                    stage="cr",
                    message=f"[CR] Clause {progress_index}/{total_clauses}: failed ({type(exc).__name__}).",
                    percent=clause_percent,
                    clause_index=progress_index,
                    clause_total=total_clauses,
                    clause_id=clause_id,
                )
                row.update({
                    "status": "unavailable",
                    "reason": f"CR could not analyze this clause ({type(exc).__name__}).",
                    "llm_status": "not_run",
                })
                rows.append(row)
                continue

            retrieved_law: list[dict[str, Any]] = []
            if rag is not None:
                try:
                    _emit_progress(
                        progress_callback,
                        stage="rag",
                        message=f"[RAG] Clause {progress_index}/{total_clauses}: retrieving Indian Contract Act context...",
                        percent=clause_percent,
                        clause_index=progress_index,
                        clause_total=total_clauses,
                        clause_id=clause_id,
                    )
                    retrieved_law = rag.retrieve(query=text, top_k=5)
                    row["rag_status"] = "complete"
                    _emit_progress(
                        progress_callback,
                        stage="rag",
                        message=f"[RAG] Clause {progress_index}/{total_clauses}: retrieved {len(retrieved_law)} provisions.",
                        percent=clause_percent,
                        clause_index=progress_index,
                        clause_total=total_clauses,
                        clause_id=clause_id,
                    )
                except Exception as exc:
                    row["rag_status"] = "unavailable"
                    row["rag_error"] = f"RAG retrieval failed ({type(exc).__name__})."
            else:
                row["rag_status"] = "unavailable"
                row["rag_error"] = rag_error
            row["retrieved_law"] = retrieved_law

            if llm is None:
                row["llm_status"] = "unavailable"
                row["llm_error"] = llm_error or "Configured LLM is unavailable."
                _emit_progress(
                    progress_callback,
                    stage="llm",
                    message=f"[LLM] Clause {progress_index}/{total_clauses}: skipped ({row['llm_error']}).",
                    percent=clause_percent,
                    clause_index=progress_index,
                    clause_total=total_clauses,
                    clause_id=clause_id,
                )
                row["analysis"] = {
                    "assessed_risk": "Unknown",
                    "agreement_with_model": False,
                    "summary": "Grounded LLM analysis could not be generated.",
                    "risk_reasoning": row["llm_error"],
                    "relevant_sections": [],
                    "irrelevant_or_weak_sections": [],
                    "contractual_concern": "Manual review required.",
                    "suggested_mitigation": "Review this clause manually.",
                    "human_review_required": True,
                    "evidence_sufficient": False,
                }
            else:
                try:
                    _emit_progress(
                        progress_callback,
                        stage="llm",
                        message=f"[LLM] Sending clause {progress_index}/{total_clauses} to {llm.model_name}...",
                        percent=clause_percent,
                        clause_index=progress_index,
                        clause_total=total_clauses,
                        clause_id=clause_id,
                    )
                    analysis = llm.analyze(
                        clause=text,
                        model_result=model_result,
                        retrieved_law=retrieved_law,
                    )
                    response_valid = analysis.pop("response_valid", True)
                    model_risk = str(model_result.get("prediction", "")).strip().lower()
                    llm_risk = str(analysis.get("assessed_risk", "")).strip().lower()
                    if model_risk in {"seed", "baseline"}:
                        model_risk = "low"
                    analysis["agreement_with_model"] = bool(model_risk and llm_risk == model_risk)
                    analysis["human_review_required"] = True
                    if not retrieved_law:
                        analysis["relevant_sections"] = []
                        analysis["evidence_sufficient"] = False
                    row["analysis"] = analysis
                    row["llm_status"] = "complete" if response_valid else "incomplete"
                    if not response_valid:
                        row["llm_error"] = "LLM response was malformed or incomplete; fallback values were used."
                    _emit_progress(
                        progress_callback,
                        stage="llm",
                        message=f"[LLM] Received analysis for clause {progress_index}/{total_clauses}.",
                        percent=22 + int(50 * progress_index / max(total_clauses, 1)),
                        clause_index=progress_index,
                        clause_total=total_clauses,
                        clause_id=clause_id,
                    )
                except Exception as exc:
                    row["llm_status"] = "unavailable"
                    row["llm_error"] = f"LLM analysis failed ({type(exc).__name__})."
                    _emit_progress(
                        progress_callback,
                        stage="llm",
                        message=f"[LLM] Clause {progress_index}/{total_clauses}: failed ({type(exc).__name__}).",
                        percent=clause_percent,
                        clause_index=progress_index,
                        clause_total=total_clauses,
                        clause_id=clause_id,
                    )
                    row["analysis"] = {
                        "assessed_risk": "Unknown",
                        "agreement_with_model": False,
                        "summary": "Grounded LLM analysis could not be generated.",
                        "risk_reasoning": row["llm_error"],
                        "relevant_sections": [],
                        "irrelevant_or_weak_sections": [],
                        "contractual_concern": "Manual review required.",
                        "suggested_mitigation": "Review this clause manually.",
                        "human_review_required": True,
                        "evidence_sufficient": False,
                    }
            row["status"] = (
                "complete"
                if row.get("rag_status") == "complete" and row.get("llm_status") == "complete"
                else "incomplete"
            )
            row["interpretation_note"] = (
                "LegalBERT is a learned risk signal, not a calibrated probability. "
                "Retrieved provisions are candidate legal context and do not by themselves establish a violation."
            )
            rows.append(row)

        llm_statuses = {row.get("llm_status") for row in rows if row.get("llm_status")}
        rag_complete = all(row.get("rag_status") == "complete" for row in rows)
        result_status = "complete" if llm_statuses == {"complete"} and rag_complete else "incomplete"
        result = {"status": result_status, "clauses": rows}
        if result_status != "complete":
            result["reason"] = "One or more clauses lack complete CR, RAG, or LLM analysis."
        if rag_error:
            result["rag_reason"] = rag_error
        return result
    except Exception as exc:
        return {"status": "unavailable", "reason": f"CR could not initialize or analyze clauses ({type(exc).__name__}).", "clauses": []}


def _run_cl(doc_id: str, clauses: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        from agents.cl.confidentiality_leakage.agent import ConfidentialityLeakageAgent
        from agents.cl.confidentiality_leakage.masker import mask_value

        report = ConfidentialityLeakageAgent().analyze(doc_id, clauses=clauses).model_dump()
        replacements: dict[str, str] = {}
        for finding in report.get("findings", []):
            value = str(finding.get("value", ""))
            if value:
                replacements[value] = mask_value(str(finding.get("type", "")), value)
        return {"status": "complete", "report": report}, replacements
    except Exception as exc:
        return {"status": "unavailable", "reason": f"CL could not analyze clauses ({type(exc).__name__})."}, {}


def _run_coi(doc_id: str, operator_input: dict[str, Any]) -> dict[str, Any]:
    """Search the existing Neo4j graph without extracting contract relationships."""
    client = str(operator_input.get("client_entity") or "").strip()
    counterparty = str(operator_input.get("counterparty_entity") or "").strip()
    if not client or not counterparty:
        return {"status": "skipped", "reason": "COI graph search requires client and counterparty names."}
    graph = None
    try:
        from agents.coi.conflict_agent import ConflictOfInterestAgent
        from agents.coi.graph_manager import close_graph, get_graph

        graph = get_graph()
        report = ConflictOfInterestAgent(graph=graph).run(
            client_entity=client,
            counterparty_entity=counterparty,
            doc_id=doc_id,
            additional_entities=operator_input.get("additional_entities") or [],
        ).to_dict()
        return {
            "status": report.get("status", "unknown"),
            "report": report,
            "method": "Neo4j graph search only; the submitted contract was not ingested into the graph.",
        }
    except Exception as exc:
        detail = str(exc) if type(exc).__name__ == "GraphQueryError" else type(exc).__name__
        return {"status": "unavailable", "reason": f"COI Neo4j graph search failed ({detail})."}
    finally:
        if graph is not None:
            try:
                close_graph()
            except Exception:
                pass


def _run_le(operator_input: dict[str, Any], coi: dict[str, Any]) -> dict[str, Any]:
    report = coi.get("report") or {}
    conflict_flag = report.get("conflict_flag")
    if coi.get("status") != "complete" or conflict_flag not in (0, 1):
        return {"status": "skipped", "reason": "LE requires a complete COI analysis with a known conflict flag."}
    features = operator_input.get("le_features") or {}
    missing = [name for name in LE_FEATURES if features.get(name) is None]
    deviation = operator_input.get("clause_deviation_score")
    if missing or deviation is None:
        fields = ", ".join(missing + (["clause_deviation_score"] if deviation is None else []))
        return {"status": "skipped", "reason": f"Missing LE inputs: {fields}."}
    try:
        from agents.le.agent.litigation_agent import LexState, LitigationExposureAgent

        state = LexState(entities=features, graph_results={"conflict_flag": conflict_flag}, clause_deviation_score=deviation)
        result = LitigationExposureAgent().predict_with_explanation(state)
        return {"status": "complete", "result": result,
                "interpretation": "Score from a model trained on synthetic labels; not a calibrated real-world litigation probability."}
    except Exception as exc:
        if isinstance(exc, ModuleNotFoundError):
            reason = f"LE dependency '{exc.name}' is missing; install requirements-agents.txt."
        elif isinstance(exc, ValueError):
            reason = f"LE input validation failed: {exc}"
        else:
            reason = f"LE could not produce a result ({type(exc).__name__})."
        return {"status": "unavailable", "reason": reason}


def _prompt_le_number(label: str, minimum: float, maximum: float) -> float | None:
    while True:
        raw = input(f"{label} [{minimum:g}-{maximum:g}] (Enter to skip): ").strip()
        if not raw:
            return None
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            print("Enter a number in the shown range, or press Enter to skip.")
            continue
        if not minimum <= value <= maximum:
            print("That value is outside the shown range; try again or press Enter to skip.")
            continue
        return value


def analyze_contract(
    file_path: str | Path,
    operator_input: dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    runtime: ContractAnalysisRuntime | None = None,
) -> dict[str, Any]:
    """Extract once, then call the clause agents with the identical split."""
    operator_input = operator_input or {}
    load_dotenv(ROOT / ".env")
    _emit_progress(progress_callback, stage="extract", message="[Pipeline] Reading contract document...", percent=1)
    source = Path(file_path).expanduser().resolve()
    raw = source.read_bytes()
    text = extract_text(source.name, raw)
    _emit_progress(progress_callback, stage="extract", message="[Pipeline] Document text extracted.", percent=5)
    _emit_progress(progress_callback, stage="segment", message="[Pipeline] Splitting document into clauses...", percent=6)
    clauses = split_clauses(text)
    if not clauses:
        raise ValueError("The ingestion pipeline did not identify any clauses.")
    _emit_progress(
        progress_callback,
        stage="segment",
        message=f"[Pipeline] Found {len(clauses)} clauses.",
        percent=9,
    )

    content_id = hashlib.sha256(raw).hexdigest()[:16]
    doc_id = f"{re.sub(r'[^A-Za-z0-9_.-]+', '_', source.stem)[:60] or 'contract'}-{content_id}"
    _emit_progress(progress_callback, stage="cr", message="[CR] Starting clause risk analysis...", percent=10)
    cr = _run_cr(clauses, progress_callback=progress_callback, runtime=runtime)
    _emit_progress(progress_callback, stage="cr", message=f"[CR] Analysis {cr.get('status', 'unknown')}.", percent=74)
    _emit_progress(progress_callback, stage="cl", message="[CL] Checking confidentiality and leakage...", percent=76)
    cl, replacements = _run_cl(doc_id, clauses)
    _emit_progress(progress_callback, stage="cl", message=f"[CL] Analysis {cl.get('status', 'unknown')}.", percent=81)
    _emit_progress(progress_callback, stage="coi", message="[COI] Checking the configured conflict graph...", percent=83)
    coi = _run_coi(doc_id, operator_input)
    _emit_progress(progress_callback, stage="coi", message=f"[COI] Analysis {coi.get('status', 'unknown')}.", percent=87)
    _emit_progress(progress_callback, stage="le", message="[LE] Evaluating litigation exposure when inputs are available...", percent=89)
    le = _run_le(operator_input, coi)
    _emit_progress(progress_callback, stage="le", message=f"[LE] Analysis {le.get('status', 'unknown')}.", percent=92)

    # Keep shared text out of the saved JSON. CR's optional evidence snippets
    # and every agent's evidence strings are masked before export.
    cr_export = _mask_tree({**cr, "clauses": [{k: v for k, v in row.items() if k not in {"text", "excerpt"}}
                                                  for row in cr.get("clauses", [])]}, replacements)
    cl = _mask_tree(cl, replacements)
    coi = _mask_tree(coi, replacements)
    le = _mask_tree(le, replacements)
    statuses = {"CR": cr.get("status"), "CL": cl.get("status"), "COI": coi.get("status"), "LE": le.get("status")}
    warnings = [f"{agent} status: {status}." for agent, status in statuses.items() if status != "complete"]
    if coi.get("status") == "complete":
        warnings.append("COI searched existing Neo4j relationships only; it did not extract relationships from this contract.")
    if le.get("status") == "complete":
        warnings.append(le["interpretation"])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.stem)[:60] or "contract"
    output_json = OUTPUT_DIR / f"{safe_stem}_{timestamp}.json"
    output_pdf = OUTPUT_DIR / f"{safe_stem}_{timestamp}.pdf"
    document = {"file_name": source.name, "file_type": source.suffix.lstrip("."),
                "word_count": len(text.split()), "clause_count": len(clauses)}
    result = {"document": document, "cr": cr_export, "cl": cl, "coi": coi, "le": le,
              "agent_statuses": statuses,
              "warnings": warnings, "review_required": True,
              "outputs": {"json": str(output_json), "pdf": str(output_pdf)}}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    _emit_progress(progress_callback, stage="report", message="[Report] JSON report saved; generating PDF...", percent=94)

    cr_rows = []
    for row in cr.get("clauses", []):
        cr_rows.append(_mask_tree({
            **row,
            **row.get("model", {}),
            "excerpt": str(next((c.get("text", "") for i, c in enumerate(clauses, 1)
                                 if _clause_id(c, i) == row["clause_id"]), ""))[:1600],
        }, replacements))
    counts = Counter((row.get("hybrid") or {}).get("display_risk", "Unknown") for row in cr.get("clauses", []))
    pdf_summary = {"prediction_counts": dict(counts)}
    try:
        from agents.cr.reporting.document_report import generate_pdf_report
        generate_pdf_report(document, pdf_summary, cr_rows,
                            agent_results={"cr": cr_export, "cl": cl, "coi": coi, "le": le, "warnings": warnings},
                            output_path=output_pdf)
    except Exception as exc:
        result["warnings"].append(f"PDF report could not be generated ({type(exc).__name__}).")
        result["outputs"]["pdf"] = None
        output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        _emit_progress(progress_callback, stage="report", message=f"[Report] PDF unavailable ({type(exc).__name__}); JSON report is saved.", percent=98)
    else:
        _emit_progress(progress_callback, stage="report", message="[Report] PDF report saved.", percent=98)
    _emit_progress(progress_callback, stage="complete", message="[Pipeline] Contract analysis complete.", percent=100)
    return result


def run_cli() -> None:
    print("Contract analysis (per-clause CR, Indian Contract Act RAG, and grounded LLM)")
    file_path = input("Contract file path (TXT/PDF/DOCX): ").strip().strip("\"'")
    if not file_path:
        print("A contract file path is required.")
        return
    print("COI checks the existing Neo4j graph only; it does not ingest this contract or call Groq.")
    operator: dict[str, Any] = {
        "client_entity": input("Client entity (example: Alpha Org): ").strip(),
        "counterparty_entity": input("Counterparty entity (example: Alpha Labs): ").strip(),
    }
    if operator["client_entity"] and operator["counterparty_entity"]:
        print("LE values are optional. Provide all seven features and clause deviation to run LE; leave any blank to skip.")
        features: dict[str, float] = {}
        for key, (label, minimum, maximum) in LE_FEATURES.items():
            value = _prompt_le_number(label, minimum, maximum)
            if value is not None:
                features[key] = value
        operator["le_features"] = features
        operator["clause_deviation_score"] = _prompt_le_number(
            "Clause deviation (0=standard, 1=highly customized)", 0, 1
        )
    try:
        result = analyze_contract(file_path, operator)
    except Exception as exc:
        print(f"Analysis could not start: {type(exc).__name__}: {exc}")
        return
    print("\nAgent statuses:")
    for name in ("cr", "cl", "coi", "le"):
        print(f"  {name.upper()}: {result[name]['status']}")
    print(f"JSON: {result['outputs']['json']}")
    print(f"PDF:  {result['outputs']['pdf'] or 'not generated'}")
