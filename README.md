# LEXGUARD

LEXGUARD is a contract analysis prototype with a browser interface and a FastAPI backend. It runs four independent analysis agents and presents their results together:

- **CRA - Contract Risk Analysis:** clause-level LegalBERT risk predictions, Indian-law retrieval, and local LLM explanations.
- **CL - Confidentiality Leakage:** detects personal data, sensitive personal data, business-confidential terms, and processing activity context.
- **COI - Conflict of Interest:** combines contract NER and supplied party names with a Neo4j relationship graph; clause text may also identify an unverified shared-director pattern.
- **LE - Litigation Exposure:** optional contract-level model prediction using manually supplied contract facts. COI supplies the conflict-of-interest flag.

This is a research and review aid, not legal advice. Model outputs require qualified human review. Do not submit real confidential or personal data to an untrusted deployment.

## Repository layout

```text
api.py                         FastAPI application and browser API
combined_analysis.py           CLI launcher
static/                        Browser frontend
ingestion_pipeline/            TXT, PDF, DOCX ingestion and clause segmentation
agents/cra/                    CRA models, retrieval, LLM, and orchestration
agents/cl/                     Confidentiality Leakage agent
agents/coi/                    Neo4j-backed Conflict of Interest agent
agents/litigation_agent/       Litigation Exposure model and intake
sample_contracts/              Synthetic/demo contract
sample_json/                   Example contract intake
docker-compose.yml             Local Neo4j service
```

See each agent's README for its inputs, outputs, and limitations:
[CRA](agents/cra/README.md) · [CL](agents/cl/README.md) · [COI](agents/coi/README.md) · [LE](agents/litigation_agent/README.md).

## Prerequisites

- Python 3.12 or newer (use a Python version supported by the installed PyTorch release).
- Git and Docker Desktop with Docker Compose for Neo4j-backed COI searches.
- Ollama with the `qwen2.5:1.5b` model for CRA LLM explanations.
- The project CRA fine-tuned checkpoint at `agents/cra/checkpoints/best_model.pt`. This approximately 1.3 GB model file is intentionally excluded from ordinary Git commits. Obtain the approved artifact from the project maintainer or train it using the CRA training workflow before starting the service.

The first CRA initialization also downloads LegalBERT and the sentence-transformer embedding model from Hugging Face. Ensure network access is available for that first run, or pre-cache the models.

## Local setup (PowerShell)

Run these commands from the repository root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set a strong local Neo4j password in `.env` and use the same credentials when starting the database. `.env` is ignored by Git; keep real credentials there and never commit them.

Start Neo4j and seed the fictional demo graph:

```powershell
docker compose up -d neo4j
python -m agents.coi.seed_demo_graph
```

Neo4j Browser is available at `http://localhost:7475`; Bolt uses `bolt://localhost:7688`. The graph seeder uses fictional demo entities and relationships.

Install and start Ollama separately, then download the configured model:

```powershell
ollama pull qwen2.5:1.5b
```

Start the API and frontend from the project root:

```powershell
python -m uvicorn api:app --reload
```

Open `http://127.0.0.1:8000` for the browser UI or `http://127.0.0.1:8000/docs` for Swagger. Models initialize in the background when the UI opens. The readiness panel and health checkpoints show each agent's state. Keep one Uvicorn process running; each worker would load its own model copies.

## API and analysis inputs

- `POST /analyze-contract` runs CRA, CL, and COI. Set `include_litigation_exposure` to `true` to request LE.
- `POST /build-le-intake` validates the form-style LE flags and numeric inputs and returns the corresponding JSON shape.
- `POST /initialize` starts model initialization; `GET /initialization-status` reports progress.
- `POST /agent-health-check` and `GET /agent-health` run and report agent health checks; COI's check needs Neo4j.
- `GET /health` checks the API process.

Swagger accepts plaintext in `contract_text`, optional party hints in `parties.client`, `parties.counterparty`, and `parties.additional`, and optional LE fields. See [`sample_json/example_contract_intake.json`](sample_json/example_contract_intake.json). COI searches supplied names alongside NER entities. Both primary party names should resolve to graph entities for a meaningful relationship search.

The browser output shows the CRA clause LLM fields, CL confidentiality score/counts/findings, and COI/LE result cards. LE features are manually entered; the COI conflict flag is managed by the pipeline. When COI does not provide a conflict result, the current LE pipeline uses a documented fallback value of `0`; that fallback means no positive conflict result was available, not that the graph verified no conflict.

Supported contract ingestion includes UTF-8 TXT, text-based PDF, and DOCX. Scanned PDFs require OCR before ingestion. Contract-level analysis is in-memory and does not persist submitted contracts to Neo4j.

## Models and GitHub artifacts

The large CRA checkpoint is excluded by `.gitignore` because GitHub's normal Git object limits are unsuitable for a 1.3 GB file. A clone needs this file at `agents/cra/checkpoints/best_model.pt` before CRA initialization. Arrange a separately approved model artifact distribution (for example, an access-controlled model store or Git LFS with sufficient quota); do not put private contracts, credentials, model caches, or generated analysis outputs into the repository.

The LE `litigation_model.joblib` is a small required model artifact and remains tracked with its agent. Its predictions are based on the training data and should be treated as experimental, not as calibrated real-world litigation probabilities.

## Notes for contributors

- Root `requirements.txt` lists direct runtime dependencies. Install into a virtual environment.
- Generated caches, local credentials, CRA checkpoints/outputs, and the nested CRA Git metadata are excluded by `.gitignore`.
- Review `.env.example` before deployment and change the demo credentials/password.
- Do not commit real contracts or personal data. Use synthetic examples in issues and pull requests.
