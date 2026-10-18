# Contract ingestion

## HTTP API and Swagger

Install the API packages if they are not already in the virtual environment,
then start the development server from the project root:

```powershell
.venv\Scripts\python.exe -m pip install "fastapi>=0.115,<1" "uvicorn[standard]>=0.34,<1"
.venv\Scripts\python.exe -m uvicorn api:app --reload
```

Open `http://127.0.0.1:8000/docs`, expand `POST /analyze-contract`, and choose
**Try it out**. Its JSON body accepts `contract_text` and optional `parties`
(`client`, `counterparty`, `additional`). The COI scan combines those party
names with contract NER entities. Set `include_litigation_exposure` to `true`
to also score LE with the supplied manual `entities` and
`clause_deviation_score`. `GET /health` checks that the API is running.

The browser UI is available at `http://127.0.0.1:8000`. It initializes CRA, CL,
COI, and LE in the background when the page opens and shows per-agent readiness
at the top. `POST /initialize` starts the same process-level warm-up, and
`GET /initialization-status` reports progress. The page also runs asynchronous
health checkpoints every 30 seconds through `POST /agent-health-check` and
`GET /agent-health`; the COI checkpoint verifies Neo4j connectivity. Contract
submissions go to `POST /analyze-contract`. Keep one Uvicorn server process
running; restarting it or using multiple workers creates a separate model
instance per process.

The LE form uses **`POST /build-le-intake`** to validate the button and number
inputs and construct the intake JSON sent with **`POST /analyze-contract`**.
The form leaves unknown facts blank, and COI remains responsible for
`conflict_flag`.

The browser dashboard displays the CL agent's `risk_score` and `risk_level`
directly. Its combined dashboard score is a separate equal-weight mean across
available agents: CRA contributes its highest ML risk band normalized to
0/25/50/75/100, CL contributes its reported 0–100 `risk_score`, COI contributes
severity mapped to None/Low/Medium/High = 0/35/65/100, and LE contributes
litigation probability × 100. Each agent contributes once; unavailable agents
are omitted. The UI deduplicates exact finding occurrences for its counts and
table. Processing activities remain separate context and are not added again
to the combined score.

This package adapts the supplied ingestion pipeline's in-memory TXT/PDF/DOCX
extractor and legal clause splitter. `ingest_contract_bytes` is suitable for
an upload handler; `ingest_contract_file` is for local files. Both return the
extracted plaintext, segmented clause/table units, a content-derived contract
ID, and document counts. They do not write to Neo4j or run analysis agents.

From the project root, inspect ingestion of a local document with:

```powershell
.venv\Scripts\python.exe combined_analysis.py --ingest-contract path\to\contract.pdf
```

Run contract-level CRA, CL, and COI analysis with:

```powershell
.venv\Scripts\python.exe combined_analysis.py --analyze-contract path\to\contract.pdf
```

For a basic COI graph lookup without a contract or NER, enter the client and
counterparty directly. The CLI asks for yes/no confirmation before querying:

```powershell
.venv\Scripts\python.exe combined_analysis.py --coi-parties "Client Company Ltd" "Supplier Company Ltd"
```

Both names must resolve to entities already present in the Neo4j graph. This
checks graph relationships between the two parties and reports evidence/status.

To include Litigation Exposure, either add `--with-le` to paste JSON into the
terminal (finish with `END`) or pass `--le-json PATH` to load an intake file.
`sample_json/example_contract_intake.json` is a starting template;
replace its illustrative values with supported contract facts. Manual contract
features go in `entities` and `clause_deviation_score` at the top level. COI
supplies `graph_results.conflict_flag`; a manual JSON value for that field is
ignored. If COI produces no conflict result, the pipeline defaults the flag to
`0` and labels that fallback in the report. LE is skipped only when another
required input is missing or invalid.

The same JSON can include `parties.client`, `parties.counterparty`, and an
optional `parties.additional` array. COI searches these names alongside
entities detected by NER. The primary party names should match entities in
Neo4j. If `parties` is omitted, COI uses roles detected from the contract.

CRA analyzes each segmented unit with at least five words. CL scans the complete
set of units once, and COI scans the complete extracted text once. Litigation
Exposure is optional via `--with-le`. The contract-level command prints a
summary and clause-level CRA signals; it does not persist the report or write
new facts to Neo4j.

Supported inputs are UTF-8 TXT, text-based PDF, and DOCX, up to 5 MB, 100 PDF
pages, and 120,000 extracted characters. Scanned PDFs need OCR before use.
Clause segmentation, table extraction, grammar cleanup, and semantic repair
are taken from the supplied LDI chunker. The LDI source is kept intact; the
LEXGUARD-specific code coordinates extraction, analysis, and CLI behavior.
