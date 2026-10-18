"""Coordinate CRA, CL, and COI over one ingested contract."""
from __future__ import annotations

from collections import Counter
from typing import Any

from analyze_clause import ContractRiskAnalysisSystem
from agents.cl.confidentiality_leakage import ConfidentialityLeakageAgent
from agents.cl.confidentiality_leakage.masker import mask_value
from agents.coi.clause_scan import scan_clause_for_coi


RISK_ORDER = {"baseline": 0, "seed": 0, "low": 1, "medium": 2, "high": 3}


class ContractAnalysisPipeline:
    """Run clause risk analysis plus contract-wide privacy and COI scans."""

    def __init__(self) -> None:
        self.contract_risk = ContractRiskAnalysisSystem()
        self.confidentiality = ConfidentialityLeakageAgent()

    def analyze(
        self, document: dict[str, Any], litigation_state=None,
        coi_parties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plaintext = str(document.get("plaintext") or "")
        clauses = document.get("clauses") or []
        if not plaintext.strip() or not clauses:
            raise ValueError("Ingest a nonempty contract before running contract analysis.")

        contract_id = str(document.get("contract_id") or "contract")
        clauses_for_cl = [
            {
                "clause_id": str(clause.get("clause_id") or f"P{index}"),
                "section": str(clause.get("section") or ""),
                "text": str(clause.get("text") or ""),
            }
            for index, clause in enumerate(clauses, start=1)
            if str(clause.get("text") or "").strip()
        ]

        # CL and COI are document-level scans. CRA is evaluated clause by clause.
        confidentiality = self.confidentiality.analyze(
            doc_id=contract_id,
            clauses=clauses_for_cl,
        ).model_dump()
        coi = scan_clause_for_coi(
            plaintext, doc_id=contract_id, parties=coi_parties,
            agent=getattr(self, "coi_agent", None),
        )

        litigation_result = None
        litigation_report: dict[str, Any] = {"status": "not_requested"}
        if litigation_state is not None:
            litigation_state.contract_text = plaintext
            litigation_state.graph_results = dict(litigation_state.graph_results or {})
            graph = coi.get("graph_result")
            if graph and graph.get("conflict_flag") is not None:
                graph_conflict = int(bool(graph["conflict_flag"]))
                conflict_flag_source = "COI graph result"
            elif graph and graph.get("conflict_detected"):
                graph_conflict = 1
                conflict_flag_source = "COI detected a conflict; graph result incomplete"
            else:
                graph_conflict = 0
                conflict_flag_source = "COI produced no conflict result; defaulted to 0"
            # COI alone owns conflict_flag; ignore any manual JSON value.
            litigation_state.graph_results["conflict_flag"] = graph_conflict
            try:
                litigation_result = self.contract_risk.predict_litigation(litigation_state)
                litigation_report = {
                    "status": "complete",
                    **litigation_result,
                    "conflict_flag": graph_conflict,
                    "conflict_flag_source": conflict_flag_source,
                }
            except ValueError as exc:
                litigation_report = {
                    "status": "skipped", "reason": str(exc),
                    "conflict_flag": graph_conflict,
                    "conflict_flag_source": conflict_flag_source,
                }
            except Exception as exc:
                litigation_report = {
                    "status": "unavailable",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "conflict_flag": graph_conflict,
                    "conflict_flag_source": conflict_flag_source,
                }

        analyzed: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        eligible = [
            (index, clause)
            for index, clause in enumerate(clauses, start=1)
            if len(str(clause.get("text") or "").split()) >= 5
        ]

        # Context-dependent NER alone is not a confidentiality flag. Only
        # substantive CL findings with a clause location request LLM review.
        cl_flagged_clause_ids = {
            str(finding.get("clause_id"))
            for finding in confidentiality.get("findings", [])
            if finding.get("clause_id")
            and str(finding.get("sensitivity", "")).upper() != "CONTEXT_DEPENDENT"
        }

        for position, (index, clause) in enumerate(eligible, start=1):
            clause_id = str(clause.get("clause_id") or f"P{index}")
            text = str(clause.get("text") or "").strip()
            print(f"Analyzing clause {position}/{len(eligible)}: {clause_id}")
            try:
                model_result = self.contract_risk.predict_model(text)
                prediction = str(model_result.get("prediction", "")).strip().casefold()
                cra_flagged = prediction not in {"", "baseline", "seed", "unknown"}
                cl_flagged = clause_id in cl_flagged_clause_ids
                llm_included = cra_flagged or cl_flagged
                if llm_included:
                    risk = self.contract_risk.analyze(
                        text,
                        litigation_result=litigation_result,
                        model_result=model_result,
                    )
                else:
                    risk = {
                        "clause": text,
                        "model": model_result,
                        "retrieved_law": [],
                        "analysis": {},
                        "litigation": litigation_result,
                        "llm_analysis_skipped": True,
                    }
                analyzed.append({
                    "clause_id": clause_id,
                    "section": clause.get("section"),
                    "level": clause.get("level"),
                    "text": text,
                    "cra": risk,
                    "llm_analysis_included": llm_included,
                    "llm_trigger": [
                        trigger for trigger, matched in (("CRA above baseline", cra_flagged), ("CL finding", cl_flagged))
                        if matched
                    ],
                })
            except Exception as exc:
                analyzed.append({
                    "clause_id": clause_id,
                    "section": clause.get("section"),
                    "level": clause.get("level"),
                    "text": text,
                    "cra_error": f"{type(exc).__name__}: {exc}",
                })

        for index, clause in enumerate(clauses, start=1):
            text = str(clause.get("text") or "").strip()
            if not text or len(text.split()) >= 5:
                continue
            skipped.append({
                "clause_id": str(clause.get("clause_id") or f"P{index}"),
                "reason": "fewer than five words",
            })

        cra_model_counts: Counter[str] = Counter()
        llm_counts: Counter[str] = Counter()
        review_clause_ids = []
        for item in analyzed:
            risk = item.get("cra")
            if not risk:
                continue
            model_label = str(risk.get("model", {}).get("prediction", "unknown"))
            cra_model_counts[_display_risk(model_label)] += 1
            llm_label = risk.get("analysis", {}).get("assessed_risk")
            if llm_label:
                llm_counts[_display_risk(str(llm_label))] += 1
                if risk.get("analysis", {}).get("human_review_required"):
                    review_clause_ids.append(item["clause_id"])

        coi_graph = coi.get("graph_result")
        coi_needs_review = bool(
            coi.get("clause_findings")
            or not coi_graph
            or (coi_graph and (
                coi_graph.get("conflict_detected")
                or coi_graph.get("status") != "complete"
            ))
        )
        human_review = bool(
            review_clause_ids
            or coi_needs_review
            or confidentiality.get("risk_level", "").upper() == "HIGH"
            or (litigation_state is not None and litigation_report.get("status") != "complete")
            or litigation_report.get("risk_level", "").upper() == "HIGH"
        )

        cra_summary_input = []
        for item in analyzed:
            risk = item.get("cra") or {}
            model = risk.get("model") or {}
            llm_analysis = risk.get("analysis") or {}
            cra_summary_input.append({
                "clause_id": item["clause_id"],
                "ml_prediction": model.get("prediction"),
                "ml_score": model.get("model_score"),
                "above_baseline": bool(item.get("llm_trigger") and "CRA above baseline" in item["llm_trigger"]),
                "llm_output": {
                    "assessed_risk": llm_analysis.get("assessed_risk"),
                    "agreement_with_model": llm_analysis.get("agreement_with_model"),
                    "summary": llm_analysis.get("summary"),
                    "risk_reasoning": llm_analysis.get("risk_reasoning"),
                },
            })
        overall_summary_inputs = {
            "cra_clause_results": cra_summary_input,
            "skipped_clauses": skipped,
            # Send the complete CL report (including traceable findings) to the
            # local LLM and expose this exact object in the summary dialog.
            "confidentiality": confidentiality,
        }
        try:
            overall_summary = {
                "status": "complete",
                **self.contract_risk.llm.summarize_contract(
                    cra_summary_input,
                    confidentiality,
                    skipped_clauses=skipped,
                ),
            }
        except Exception as exc:
            overall_summary = {
                "status": "unavailable",
                "message": f"Overall CRA/CL summary unavailable ({type(exc).__name__}).",
            }
        overall_summary["source_inputs"] = overall_summary_inputs

        return {
            "contract_id": contract_id,
            "filename": document.get("filename"),
            "metadata": document.get("metadata", {}),
            "summary": {
                "clauses_analyzed": sum(bool(item.get("cra")) for item in analyzed),
                "clauses_failed": sum("cra_error" in item for item in analyzed),
                "clauses_skipped": len(skipped),
                "cra_model_risk_counts": dict(cra_model_counts),
                "llm_assessed_risk_counts": dict(llm_counts),
                "highest_legalbert_risk": _highest_risk(cra_model_counts),
                "highest_llm_assessed_risk": _highest_risk(llm_counts),
                "human_review_required": human_review,
                "human_review_clause_ids": review_clause_ids,
                "llm_analysis_clause_ids": [
                    item["clause_id"] for item in analyzed if item.get("llm_analysis_included")
                ],
            },
            "clauses": analyzed,
            "skipped_clauses": skipped,
            "confidentiality": confidentiality,
            "coi": coi,
            "litigation_exposure": litigation_report,
            "overall_summary": overall_summary,
        }

    @staticmethod
    def print_summary(report: dict[str, Any]) -> None:
        summary = report["summary"]
        metadata = report.get("metadata") or {}
        print("\n" + "=" * 70)
        print("LEXGUARD CONTRACT-LEVEL ANALYSIS")
        print("=" * 70)
        print(f"Contract: {report.get('filename') or report['contract_id']}")
        print(f"Analyzed: {summary['clauses_analyzed']} clauses; "
              f"{summary['clauses_failed']} failed; {summary['clauses_skipped']} skipped")
        print(f"Highest LegalBERT signal: {summary['highest_legalbert_risk']}")
        print(f"Highest LLM assessment: {summary['highest_llm_assessed_risk']}")
        if metadata:
            print(f"Document length: {metadata.get('word_count', 0)} words")
        flagged = [
            item for item in report["clauses"]
            if item.get("cra")
            and str(item["cra"].get("model", {}).get("prediction", "")).casefold()
            not in {"baseline", "seed", "unknown", ""}
        ]
        failed = [item for item in report["clauses"] if "cra_error" in item]
        print("\nClauses flagged above Baseline by LegalBERT:")
        if not flagged:
            print("- None")
        for item in flagged:
            risk = item["cra"]
            model = risk.get("model", {})
            analysis = risk.get("analysis", {})
            model_prediction = model.get("prediction", "Unknown")
            model_score = model.get("model_score")
            score_text = ""
            if model_score is not None:
                try:
                    normalized_score = float(model_score)
                    if normalized_score <= 1:
                        normalized_score *= 100
                    score_text = f" ({normalized_score:.2f}%)"
                except (TypeError, ValueError):
                    pass
            reason = analysis.get("risk_reasoning") or analysis.get("summary") or "No LLM reasoning provided."
            reason = " ".join(str(reason).split())
            if len(reason) > 360:
                reason = reason[:357].rsplit(" ", 1)[0] + "..."
            print(f"- {item['clause_id']}: LegalBERT {model_prediction}{score_text}; "
                  f"LLM {analysis.get('assessed_risk', 'Unknown')}")
            print(f"  Reason: {reason}")
        if failed:
            print(f"\nCRA analysis failed for {len(failed)} clause(s): "
                  + ", ".join(item["clause_id"] for item in failed))

        cl = report["confidentiality"]
        print("\nCL document scan:")
        print(f"- {cl['risk_level']} risk ({cl['risk_score']}/100); "
              f"{cl['total_findings']} finding(s)")
        for finding in cl.get("findings", []):
            print(f"- {finding['sensitivity']} {finding['type']}: "
                  f"{mask_value(finding['type'], finding['value'])} "
                  f"(clause {finding['clause_id'] or 'unknown'})")

        coi = report["coi"]
        print("\nCOI document scan:")
        if coi.get("party_roles"):
            print("- Parties: " + ", ".join(
                f"{role}={name}" for role, name in coi["party_roles"].items()
            ))
        for finding in coi.get("clause_findings", []):
            print(f"- Potential shared-director conflict: {finding['person']} "
                  "(based on clause text; not graph-verified)")
        graph = coi.get("graph_result")
        if graph:
            print(f"- Graph: {graph['status']} / {graph['severity']}; "
                  f"conflict detected={graph['conflict_detected']}")
            if graph.get("skipped_reason"):
                print(f"  Note: {graph['skipped_reason']}")
        elif not coi.get("clause_findings"):
            print("- No clause-level conflict pattern detected; graph scan unavailable.")

        print("\nOverall workflow: "
              f"{'human review required' if summary['human_review_required'] else 'no review trigger from configured checks'}")
        le = report["litigation_exposure"]
        print("\nLitigation Exposure:")
        if "conflict_flag" in le:
            print(f"- COI conflict_flag: {le['conflict_flag']} "
                  f"({le['conflict_flag_source']})")
        if le["status"] == "complete":
            print(f"- {le['risk_level']} ({le['litigation_probability']:.2%})")
            contributions = le.get("shap_explanation") or {}
            top_contributions = sorted(contributions.items(), key=lambda pair: abs(pair[1]), reverse=True)[:3]
            if top_contributions:
                print("- Top model contributions: " + ", ".join(
                    f"{name} {value:+.3f}" for name, value in top_contributions
                ))
        elif le["status"] == "skipped":
            print(f"- Scoring skipped: {le.get('reason', 'required inputs missing')}")
        elif le["status"] == "unavailable":
            print(f"- Unavailable: {le.get('reason', 'model error')}")
        else:
            print("- Not requested")


def _highest_risk(counts: Counter[str]) -> str:
    if not counts:
        return "Unknown"
    return max(counts, key=lambda label: RISK_ORDER.get(label.casefold(), -1))


def _display_risk(label: str) -> str:
    return "Baseline" if label.strip().casefold() in {"baseline", "seed"} else label.title()
