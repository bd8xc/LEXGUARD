# Contract agent runner

The integrated entry point extracts a TXT, PDF, or DOCX contract once with Ingestion Pipeline 2 and splits it once. For each clause, CR runs LegalBERT, retrieves candidate Indian Contract Act provisions, and sends only that clause's text, CR signal, and retrieved provisions to the grounded LLM. CL, COI, and LE outputs are not sent to the LLM; they remain separate sections in the final JSON. Groq is disconnected. COI searches the existing Neo4j graph using the client and counterparty entered in the form or CLI; it does not ingest relationships from the current contract. LE runs only with a complete COI result and all required feature values. There is no contract-wide final synthesis call.

## Setup

From the repository root, create a virtual environment and install the combined runtime dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-agents.txt
Copy-Item .env.example .env
```

Set a unique `NEO4J_PASSWORD` in `.env` before starting Neo4j. The same `.env` configures the container and the Python client. Do not commit or share it. Start the local graph with:

```powershell
docker compose --env-file .env -f agents/coi/compose.yaml up -d
```

Neo4j Browser is at `http://127.0.0.1:7474`; Bolt is bound to `127.0.0.1:7687`. The database is initially empty. COI returns an unresolved result until its graph has relationship data for the named parties. Contract submissions do not populate it.

Set `LEXGUARD_LLM_API_STYLE`, `LEXGUARD_LLM_BASE_URL`, and `LEXGUARD_LLM_MODEL` to configure CR's clause-level LLM. Defaults use local Ollama (`ollama`, `http://localhost:11434`, `qwen2.5:1.5b`). An OpenAI-compatible server can be used by setting `LEXGUARD_LLM_API_STYLE=openai_compatible` and its base URL ending in `/v1`; set `LEXGUARD_LLM_API_KEY` only if that server requires it. Keep contract-serving endpoints on a private network.

CR loads its model from `checkpoints\best_model.pt` or `agents\cr\checkpoints\best_model.pt`. If neither file exists, CR reports `unavailable` while the other agents continue where possible. If LegalBERT is loaded but the configured LLM server is unavailable, `/api/status` reports CR as `degraded`; classification and legal retrieval still run, while grounded explanations remain incomplete.

## Run

### Browser app

Install dependencies into the existing environment if needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements-agents.txt
```

Start the local web backend from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

On each server start, the backend tries to load the CR checkpoint, LegalBERT, the India-law embeddings, and the LLM client. This warm-up is printed in the server terminal. If the CR checkpoint is absent, CR reports unavailable while other available checks continue. Each document is still extracted and split on its own. Open `http://127.0.0.1:8000` in your browser. The multipage interface has an overview, guided review, live results, four specialist workspaces, and a developer console. The guided review accepts a PDF, DOCX, or TXT file (up to 5 MiB), or pasted text. Its upload preview lets you check extracted text; edits to that preview are submitted as text. Client, counterparty, and additional entities are optional for a full review; COI needs both parties to run. LE runs only when all seven features plus clause deviation are supplied and COI returns a known conflict flag. Analysis runs one job at a time. The results page reconnects to live job progress and offers JSON/PDF downloads. The last completed report is retained in that browser tab until the tab closes. Uploads are saved under `contracts\uploads\` and reports under `agents\cr\outputs\`.

The specialist pages call `/api/tools/conflicts`, `/api/tools/clauses`, `/api/tools/confidentiality`, and `/api/tools/litigation`. They use the same coordinator agent functions as the combined workflow. The conflict pages search the configured Neo4j graph and never ingest the submitted contract into it. `/api/extract` previews uploaded text without starting analysis. `/api/status` reports local model and service availability. The developer console exercises the specialist JSON routes; run a complete document review through `/review`.

### CLI

```powershell
.\.venv\Scripts\python.exe -m agents.cr.analyze_contract
```

The CLI remains available and prints the same progress events. It asks for a contract path plus client and counterparty names for the Neo4j graph lookup. For the synthetic demo PDF and seeded graph, enter `Alpha Org` and `Alpha Labs`. It then prompts for LE's seven contract features and clause-deviation score. Enter all eight to run LE; leave any blank to skip it. The COI conflict flag is supplied directly by Neo4j and is not an operator input.

## Optional synthetic COI fixture

`agents/coi/synthetic_graph.py` can seed a small, explicitly synthetic test fixture into the configured graph. It is not run automatically and its unverified relationships are not real evidence. Use approved relationship data for a real review.

```powershell
.\.venv\Scripts\python.exe -m agents.coi.synthetic_graph
```

Reports are written to `agents\cr\outputs\` as separate JSON and PDF files. CL-detected sensitive values are masked in exported evidence. The `review_required` field remains true; agent scores are not combined. LE's model was trained using synthetic labels, so its score is not a calibrated real-world litigation probability.

## Runtime behavior

- If text extraction or clause splitting fails, downstream agents are not called.
- COI graph lookup needs Neo4j and matching entities in the graph. It does not call Groq or write contract relationships.
- LE is skipped if COI is incomplete or if any required LE feature is missing. Its model was trained on synthetic labels and its score is not a calibrated real-world probability.
- Only CR clause data and its retrieved Indian Contract Act passages are submitted to the per-clause LLM; CL, COI, and LE outputs remain outside its prompts.
- LegalBERT's raw model scores are not calibrated probabilities. Each clause remains marked for human review.
