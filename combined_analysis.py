"""Backward-compatible launcher for the LEXGUARD terminal app."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
AGENTS_ROOT = PROJECT_ROOT / "agents"
CRA_ROOT = AGENTS_ROOT / "cra"
for import_root in (AGENTS_ROOT, CRA_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app.cli import main


def _ingest_contract(file_path: str) -> None:
    from ingestion_pipeline.contract_ingestion import ingest_contract_file

    document = ingest_contract_file(file_path)
    metadata = document["metadata"]
    print(f"Ingested: {document['filename']} ({document['file_type'].upper()})")
    print(f"Contract ID: {document['contract_id']}")
    print(
        f"Text: {metadata['word_count']} words, {metadata['characters']} characters; "
        f"{metadata['clause_count']} units, including {metadata['table_count']} tables."
    )
    graph_update = metadata["graph_update"]
    print(f"KG: {graph_update['entities']} named entities, "
          f"{graph_update['relationships']} stated relationships; "
          f"{graph_update['clauses']} source clauses updated.")
    print("\nSegmented units:")
    for clause in document["clauses"]:
        text = clause.get("text", "")
        print(
            f"- {clause.get('clause_id', '?')} | {clause.get('section', 'Document')} | "
            f"{clause.get('level', 'clause')} | {len(text.split())} words"
        )


def _read_litigation_json(plaintext: str):
    from litigation_agent.intake import parse_litigation_payload

    print("\nPaste LE values as a JSON object. Enter END on its own line when finished.")
    print("COI conflict_flag is populated from the graph scan; any JSON value for it is ignored.")
    print("Use numeric values: deal_size USD 50,000-5,000,000; binary fields 0/1; "
          "jurisdiction_risk 1-10; governing_law_clarity 1-5; "
          "clause_deviation_score 0-1.")
    print('Include "parties" with client/counterparty names and optional additional names for COI.')
    print('See sample_json/example_contract_intake.json for the complete format.')
    lines = []
    while True:
        try:
            line = input()
        except EOFError as exc:
            raise ValueError("JSON input ended before the END marker.") from exc
        if line.strip().casefold() == "end":
            break
        lines.append(line)
    if not "\n".join(lines).strip():
        raise ValueError("No LE JSON was entered.")
    try:
        payload = json.loads("\n".join(lines))
        state = parse_litigation_payload(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid LE JSON: {exc.msg} (line {exc.lineno}, column {exc.colno}).") from exc
    state.contract_text = plaintext
    return state, _parse_coi_parties(payload)


def _parse_coi_parties(payload: dict) -> dict | None:
    parties = payload.get("parties")
    if parties is None:
        return None
    if not isinstance(parties, dict):
        raise ValueError("'parties' must be a JSON object.")
    client = parties.get("client")
    counterparty = parties.get("counterparty")
    if client is not None and (not isinstance(client, str) or not client.strip()):
        raise ValueError("'parties.client' must be a nonempty name.")
    if counterparty is not None and (not isinstance(counterparty, str) or not counterparty.strip()):
        raise ValueError("'parties.counterparty' must be a nonempty name.")
    if bool(client) != bool(counterparty):
        raise ValueError("Provide both 'parties.client' and 'parties.counterparty'.")
    additional = parties.get("additional", [])
    if not isinstance(additional, list) or any(not isinstance(name, str) or not name.strip() for name in additional):
        raise ValueError("'parties.additional' must be a list of nonempty names.")
    if not client and not additional:
        raise ValueError("'parties' must include client/counterparty or additional names.")
    return {
        "client": client.strip() if isinstance(client, str) else client,
        "counterparty": counterparty.strip() if isinstance(counterparty, str) else counterparty,
        "additional": [name.strip() for name in additional],
    }


def _analyze_contract(
    file_path: str,
    *,
    with_le: bool = False,
    le_json_path: str | None = None,
) -> None:
    from ingestion_pipeline.contract_ingestion import ingest_contract_file
    from agents.cra.orchestration.contract_pipeline import ContractAnalysisPipeline

    document = ingest_contract_file(file_path)
    print(
        f"Ingested {document['filename']}: "
        f"{document['metadata']['clause_count']} clauses/table units."
    )
    coi_parties = None
    if with_le:
        litigation_state, coi_parties = _read_litigation_json(document["plaintext"])
    elif le_json_path:
        payload = json.loads(Path(le_json_path).read_text(encoding="utf-8"))
        from litigation_agent.intake import parse_litigation_payload
        litigation_state = parse_litigation_payload(payload)
        coi_parties = _parse_coi_parties(payload)
        litigation_state.contract_text = document["plaintext"]
    else:
        litigation_state = None
    report = ContractAnalysisPipeline().analyze(
        document, litigation_state=litigation_state, coi_parties=coi_parties
    )
    ContractAnalysisPipeline.print_summary(report)


def _scan_coi_parties(client: str, counterparty: str) -> None:
    """Run a graph-only COI scan from two manually supplied party names."""
    from agents.coi.conflict_agent import ConflictOfInterestAgent

    report = ConflictOfInterestAgent().run(
        client_entity=client,
        counterparty_entity=counterparty,
        doc_id="manual-party-scan",
    ).to_dict()
    print("\nLEXGUARD COI PARTY SCAN")
    print(f"Client: {client}")
    print(f"Counterparty: {counterparty}")
    print(f"Status: {report['status']} / {report['severity']}")
    print(f"Conflict detected: {report['conflict_detected']}")
    print(f"Conflict flag: {report['conflict_flag']}")
    if report.get("skipped_reason"):
        print(f"Note: {report['skipped_reason']}")
    if report.get("unresolved_entities"):
        print("Unresolved parties: " + ", ".join(report["unresolved_entities"]))
    if report.get("conflict_path"):
        print("Evidence path: " + " -> ".join(report["conflict_path"]))
    for finding in report.get("findings", []):
        print(f"- {finding['severity']} conflict; verified={finding['verified']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LEXGUARD contract analysis and ingestion")
    contract_commands = parser.add_mutually_exclusive_group()
    contract_commands.add_argument(
        "--ingest-contract",
        metavar="PATH",
        help="extract and segment a TXT, PDF, or DOCX contract without running analysis",
    )
    contract_commands.add_argument(
        "--analyze-contract",
        metavar="PATH",
        help="run clause-level CRA and document-level CL/COI analysis on a contract",
    )
    contract_commands.add_argument(
        "--coi-parties",
        nargs=2,
        metavar=("CLIENT", "COUNTERPARTY"),
        help="prompt before a basic COI graph scan using only the two party names",
    )
    le_input = parser.add_mutually_exclusive_group()
    le_input.add_argument(
        "--with-le",
        action="store_true",
        help="prompt for manual Litigation Exposure inputs as raw JSON",
    )
    le_input.add_argument(
        "--le-json",
        metavar="PATH",
        help="load manual Litigation Exposure inputs from a JSON file",
    )
    args = parser.parse_args()
    if (args.with_le or args.le_json) and not args.analyze_contract:
        parser.error("--with-le and --le-json can only be used with --analyze-contract")
    if args.coi_parties:
        answer = input(
            f"Run a COI scan for client '{args.coi_parties[0]}' and "
            f"counterparty '{args.coi_parties[1]}'? [yes/no]: "
        ).strip().casefold()
        if answer in {"y", "yes"}:
            try:
                _scan_coi_parties(*args.coi_parties)
            except Exception as exc:
                parser.error(str(exc))
        elif answer in {"n", "no", ""}:
            print("COI scan cancelled; Neo4j was not queried.")
        else:
            parser.error("Please answer yes or no.")
    elif args.ingest_contract or args.analyze_contract:
        try:
            if args.analyze_contract:
                _analyze_contract(
                    args.analyze_contract,
                    with_le=args.with_le,
                    le_json_path=args.le_json,
                )
            else:
                _ingest_contract(args.ingest_contract)
        except Exception as exc:
            parser.error(str(exc))
    else:
        main()
