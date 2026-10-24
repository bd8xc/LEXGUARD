# Contract agent runner

The integrated entry point extracts a TXT, PDF, or DOCX contract once with Ingestion Pipeline 2 and splits it once. For each clause, CR runs LegalBERT, retrieves candidate Indian Contract Act provisions, and sends only that clause's text, CR signal, and retrieved provisions to the grounded LLM. CL, COI, and LE outputs are not sent to the LLM; they remain separate sections in the final JSON. Groq is disconnected. COI searches the existing Neo4j graph using the client and counterparty entered in the form or CLI; it does not ingest relationships from the current contract. LE runs only with a complete COI result and all required feature values. There is no contract-wide final synthesis call.

## Setup

From the repository root, create a virtual environment and install the combined runtime dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-agents.txt
Copy-Item .env.example .env
```

Set the Neo4j connection values in `.env` to enable COI graph search. Do not commit or share `.env`.

Set `LEXGUARD_LLM_API_STYLE`, `LEXGUARD_LLM_BASE_URL`, and `LEXGUARD_LLM_MODEL` to configure CR's clause-level LLM. Defaults use local Ollama (`ollama`, `http://localhost:11434`, `qwen2.5:1.5b`). An OpenAI-compatible server can be used by setting `LEXGUARD_LLM_API_STYLE=openai_compatible` and its base URL ending in `/v1`; set `LEXGUARD_LLM_API_KEY` only if that server requires it. Keep contract-serving endpoints on a private network.

CR loads its model from `checkpoints\best_model.pt` or `agents\cr\checkpoints\best_model.pt`. If neither file exists, CR reports `unavailable` while the other agents continue where possible.

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

On each server start, the backend loads LegalBERT, the India-law embedding model and corpus vectors, and the LLM client once before it accepts uploads. This initial warm-up is printed in the server terminal. Later contracts reuse those loaded objects; restarting the backend loads them again. Each document is still extracted and split on its own. Open `http://127.0.0.1:8000` in your browser. Upload a PDF, DOCX, or TXT file, enter COI parties, and optionally fill all seven LE features plus clause deviation. Analysis runs one job at a time. Clause-level progress appears in the browser and in the server terminal; the terminal output remains available while the browser shows the progress bar and event log. Results include separate CR, CL, COI, and LE findings plus JSON/PDF download links. Uploads are saved under `contracts\uploads\` and reports under `agents\cr\outputs\`.

### CLI

```powershell
.\.venv\Scripts\python.exe -m agents.cr.analyze_contract
```

The CLI remains available and prints the same progress events. It asks for a contract path plus client and counterparty names for the Neo4j graph lookup. For the synthetic demo PDF and seeded graph, enter `Alpha Org` and `Alpha Labs`. It then prompts for LE's seven contract features and clause-deviation score. Enter all eight to run LE; leave any blank to skip it. The COI conflict flag is supplied directly by Neo4j and is not an operator input.

## Synthetic COI demo

The separate demo command seeds the configured Neo4j database with 100 fictional companies, 50 fictional people, 123 relationships, and LOW/MEDIUM/HIGH trigger edges. Company names are like `Alpha Org`; person names are like `Anurag Demo`. It then runs one COI example at each severity. Every row is labeled `SYNTHETIC DEMO ONLY`; rerunning replaces the fixture and removes orphaned nodes from the earlier generic fixture.

```powershell
.\.venv\Scripts\python.exe -m agents.coi.demo
```

The integrated contract runner can search these demo relationships when the entered parties match the seeded companies. `Alpha Org` and `Alpha Labs` share a synthetic director and demonstrate a LOW conflict. Its COI result comes from the existing graph; no relationships are extracted from the submitted contract.

Reports are written to `agents\cr\outputs\` as separate JSON and PDF files. CL-detected sensitive values are masked in exported evidence. The `review_required` field remains true; agent scores are not combined. LE's model was trained using synthetic labels, so its score is not a calibrated real-world litigation probability.

## Runtime behavior

- If text extraction or clause splitting fails, downstream agents are not called.
- COI graph lookup needs Neo4j and matching entities in the graph. It does not call Groq or write contract relationships.
- LE is skipped if COI is incomplete or if any required LE feature is missing. Its model was trained on synthetic labels and its score is not a calibrated real-world probability.
- Only CR clause data and its retrieved Indian Contract Act passages are submitted to the per-clause LLM; CL, COI, and LE outputs remain outside its prompts.
- LegalBERT's raw model scores are not calibrated probabilities. Each clause remains marked for human review.
