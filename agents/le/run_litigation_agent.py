"""Run a local Litigation Exposure Agent prediction from JSON input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import LexState, LitigationExposureAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Litigation Exposure Agent")
    parser.add_argument("--input", type=Path, help="JSON file with LexState fields; defaults to stdin")
    args = parser.parse_args()
    raw = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    if not raw.strip():
        raise SystemExit("Provide JSON through --input or stdin.")
    payload = json.loads(raw)
    allowed = {"contract_text", "entities", "graph_results", "clause_deviation_score", "final_risk_score"}
    state = LexState(**{key: value for key, value in payload.items() if key in allowed})
    print(json.dumps(LitigationExposureAgent().predict_with_explanation(state), indent=2))


if __name__ == "__main__":
    main()
