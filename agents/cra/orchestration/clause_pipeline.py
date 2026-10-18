"""Coordinate clause-level analysis without changing agent implementations."""

from __future__ import annotations

import os
from typing import Any
from pathlib import Path

from dotenv import load_dotenv

from analyze_clause import ContractRiskAnalysisSystem
from agents.cl.confidentiality_leakage import ConfidentialityLeakageAgent
from agents.cl.confidentiality_leakage.masker import mask_value
from agents.coi.clause_scan import scan_clause_for_coi


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


class ClauseAnalysisPipeline:
    """Run intake, available agents, retrieval, and grounded synthesis."""

    def __init__(self) -> None:
        self.contract_risk = ContractRiskAnalysisSystem()
        self.confidentiality = ConfidentialityLeakageAgent()
        self.enable_litigation = os.getenv("LEXGUARD_ENABLE_LE", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }

    def analyze(self, clause: str) -> dict[str, Any]:
        """Pre-scan confidentiality, then run clause and optional LE analysis."""
        confidentiality_report = self.confidentiality.analyze(
            doc_id="interactive-clause",
            clauses=[{"clause_id": "clause-1", "text": clause}],
        )
        coi_report = scan_clause_for_coi(clause)
        if confidentiality_report.sensitive_data_detected:
            print(
                "\nCONFIDENTIALITY PREFLIGHT: detected "
                f"{confidentiality_report.total_findings} finding(s) "
                f"({confidentiality_report.risk_level}, "
                f"score {confidentiality_report.risk_score}/100)."
            )
            print(
                "Values will be masked in the findings display. The original "
                "clause will still be analyzed by the configured local models."
            )

        litigation_result = None
        if not self.enable_litigation:
            print("\nLitigation Exposure is disabled in the trial pipeline.")
        else:
            from litigation_agent.intake import collect_litigation_state

            litigation_state, input_sources, missing = collect_litigation_state(clause)
            if missing:
                print(
                    "\nSkipping Litigation Exposure because these required "
                    "features are unknown: "
                    + ", ".join(missing)
                )
                print("The clause analysis will continue with LegalBERT and retrieved law.")
            else:
                print("\nRunning Litigation Exposure...")
                litigation_result = self.contract_risk.predict_litigation(litigation_state)
                litigation_result["input_provenance"] = input_sources

        result = self.contract_risk.analyze(
            clause,
            litigation_result=litigation_result,
        )
        result["confidentiality"] = confidentiality_report.model_dump()
        result["coi"] = coi_report
        return result

    def print_result(self, result: dict[str, Any]) -> None:
        self.contract_risk.print_result(result)
        report = result.get("confidentiality")
        if not report:
            return

        print("\n" + "=" * 70)
        print("5. CONFIDENTIALITY & PRIVACY SCAN")
        print("=" * 70)
        print(f"Risk level    : {report['risk_level']}")
        print(f"Risk score    : {report['risk_score']}/100")
        print(f"Total findings: {report['total_findings']}")
        print(f"Summary       : {report['summary']}")
        if not report["findings"]:
            print("No sensitive or confidential content was detected.")
        else:
            print("Findings (values masked):")
            for finding in report["findings"]:
                masked = mask_value(finding["type"], finding["value"])
                print(
                    f"- {finding['sensitivity']} {finding['type']}: {masked} "
                    f"(clause {finding['clause_id'] or 'unknown'}, "
                    f"characters {finding['start']}-{finding['end']})"
                )

        coi = result.get("coi")
        if coi:
            print("\n" + "=" * 70)
            print("6. CONFLICT OF INTEREST SCAN")
            print("=" * 70)
            print(f"NER entities: {', '.join(item['name'] for item in coi['entities']) or 'none detected'}")
            if coi["party_roles"]:
                print("Party roles: " + ", ".join(f"{role}={name}" for role, name in coi["party_roles"].items()))
            if coi["clause_findings"]:
                for finding in coi["clause_findings"]:
                    print(f"Potential conflict: shared director {finding['person']} (LOW; based on clause text, not graph-verified).")
                    print(f"Evidence: {finding['evidence']}")
            if coi["graph_result"]:
                graph = coi["graph_result"]
                print(f"Graph result: {graph['status']} / {graph['severity']}; conflict detected={graph['conflict_detected']}")
                if graph.get("skipped_reason"):
                    print(f"Graph note: {graph['skipped_reason']}")
            elif not coi["clause_findings"]:
                print("No clause-level conflict pattern detected; graph scan unavailable because party roles were not resolved from the clause.")
