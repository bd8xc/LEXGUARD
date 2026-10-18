# Litigation Exposure (LE)

LE is an optional contract-level model that predicts litigation exposure from
manually supplied deal and contract facts. It runs alongside CRA, CL, and COI
in the root contract analysis API. The LE model artifact
`litigation_model.joblib` and feature metadata are included in this agent
folder.

## Browser and API use

Start the FastAPI app from the repository root as described in the main
[README](../../README.md). In the browser, expand **Litigation exposure (LE)**,
enable the prediction, and enter available boolean/numeric facts using the
buttons and number fields. Unknown facts should remain blank. The UI builds the
JSON input through `POST /build-le-intake` and sends the result to
`POST /analyze-contract`.

For Swagger, `POST /analyze-contract` accepts `include_litigation_exposure`,
`entities`, and `clause_deviation_score`. The conflict flag is controlled by
COI; callers should not provide a manual conflict flag. The response places
LE output under `litigation_exposure`, including status, risk band,
`litigation_probability`, feature contributions, and the COI conflict flag
source.

The expected manual fields are:

- `deal_size`: USD amount from 50,000 through 5,000,000.
- `liability_cap`: boolean.
- `auto_renewal`: boolean.
- `jurisdiction_risk`: integer from 1 through 10.
- `indemnification_clause`: boolean.
- `dispute_history`: boolean.
- `governing_law_clarity`: integer from 1 through 5.
- `clause_deviation_score`: number from 0 through 1, based on an approved-playbook comparison.

Use [`example_contract_intake.json`](../../sample_json/example_contract_intake.json)
as a shape example and replace its illustrative values with supported facts.

## COI conflict flag

The contract pipeline uses the COI graph result for `conflict_flag`. When COI
does not provide a conflict value, the current pipeline supplies `0` and
records a fallback source. This means no positive COI result was available; it
does not mean a graph-verified absence of conflict. Review the COI status and
graph evidence alongside LE.

## Limitations

The classifier was trained on synthetic contract records. Its output is a
model estimate, not a validated real-world litigation probability, legal
advice, or a causal finding. SHAP values describe model contributions, not
legal reasons. The jurisdiction-risk field has no built-in rubric; use a
consistent project rubric. Deal size is denominated in USD.

For programmatic use, the intake helpers `load_litigation_state()` and
`parse_litigation_payload()` remain available in `intake.py`.
