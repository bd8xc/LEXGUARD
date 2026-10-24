# Contract Agent Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route one shared clause list from Ingestion Pipeline 2 to CR and CL, query existing Neo4j relationships for COI without Groq, and run LE only with a complete COI result and all operator-supplied features. Do not call a final synthesis LLM.

**Architecture:** Keep ingestion shared at the repository root. CR and CL consume the common clause list. COI searches the existing Neo4j graph using manually entered parties; the submitted contract is not ingested into that graph. LE receives the COI conflict flag plus prompted feature values. The CR CLI calls the coordinator.

**Tech Stack:** Python 3.14 environment already present, pypdf/python-docx/pdfplumber, the existing LegalBERT PyTorch stack, Pydantic, Neo4j Python driver, requests-based Groq client, joblib/XGBoost/SHAP, and the supplied Neo4j Compose file.

**Spec:** `docs/superpowers/specs/2026-10-24-contract-agent-integration-design.md`

## Global Constraints

- Current user direction supersedes the initial Groq extraction design below: the contract runner keeps Groq disconnected and performs COI graph search against existing Neo4j relationships only. It does not ingest relationships from the submitted contract. The synthetic demo graph is labeled and isolated for demonstration.
- Ingestion Pipeline 2 extracts once and `split_clauses` creates the shared clauses consumed by CR, COI, and CL.
- Do not call Groq or a final synthesis LLM from the integrated contract CLI.
- COI uses existing Neo4j graph facts only and never calls Groq or ingests the submitted contract.
- LE runs only with a complete COI status, known conflict flag, and all eight operator-supplied inputs; otherwise mark it skipped.
- Do not combine scores across agents. LE is trained from synthetic labels and must not be described as calibrated real-world probability.
- Mask CL-sensitive values in exported results; preserve finding categories and source offsets.
- Do not guess unprovided COI or LE inputs.

## Review Focus

- Unsupported, encrypted, scanned, oversized, or empty documents produce a clear ingestion status and do not call downstream agents.
- Each clause ID and section remain identical across CR and CL outputs.
- Neo4j unavailable or unresolved parties produce COI `unavailable`/`unknown`, never a clean conflict flag.
- Groq-extracted but unverified relationships retain COI's unknown/incomplete behavior; LE is skipped.
- Missing or out-of-range LE feature values skip LE without changing CR, CL, or COI results.

## File Structure

- Create `ingestion_pipeline/` from the supplied ZIP at the repository root.
- Keep the existing project in `agents/cr/`.
- Create `agents/cl/`, `agents/coi/`, and `agents/le/` from the supplied archives, excluding bytecode, caches, logs, and egg-info.
- Create `agents/contract_coordinator.py` for shared extraction results, agent calls, status handling, and aggregate JSON output.
- Create `agents/coi/groq_client.py` and update COI's imports to provide the missing Groq client interface.
- Create root `requirements-agents.txt`, `.env.example`, and `agents/README.md` for integrated setup.
- Modify `agents/cr/analyze_contract.py` and the existing CR report path to call the coordinator and render its separate result sections.

## Task 1: Add the shared ingestion pipeline

**Files:**
- Create: `ingestion_pipeline/**` from `D:\team142\ingestion_pipeline.zip`
- Exclude: `__pycache__`, `.pyc`, `.git`, and local indexes/caches

**Interfaces:**
- Consumes: filename and document bytes.
- Produces: `extract_text(filename: str, content: bytes) -> str`; `split_clauses(text: str) -> list[dict]` with `clause_id`, `section`, `level`, and `text`.

- [x] Copy the source package without generated caches and retain its README/license files.
- [x] Confirm the extraction and splitter function signatures match this interface by reading the copied source.
- [ ] Manually inspect one supplied TXT/PDF/DOCX fixture through extraction and segmentation; runtime Python is blocked by Windows access control in this workspace.

## Task 2: Place the agent packages

**Files:**
- Create: `agents/cl/**` from `D:\team142\agents\cl.zip`
- Create: `agents/coi/**` from `D:\team142\agents\coi.zip`
- Create: `agents/le/**` from `D:\lexguard\le.zip`
- Create: `agents/__init__.py`
- Create: `agents/cr/__init__.py` to keep the legacy CR import roots available when launched as `python -m agents.cr.analyze_contract`

**Interfaces:**
- CL consumes shared clause dictionaries through `ConfidentialityLeakageAgent.analyze(doc_id, clauses=...)`.
- COI consumes clause dictionaries through `extract_from_text(...)`, then graph writes through `ingest_document(...)`; search uses `ConflictOfInterestAgent.run(...)`.
- LE consumes a `LexState` through `LitigationExposureAgent.predict_with_explanation(...)`.

- [x] Extract source files into the specified folders, excluding generated bytecode, logs, egg-info, and embedded caches.
- [x] Preserve the CL license and each agent's README/model/feature artifacts.
- [x] Confirm the package roots and required entry point files by source inspection; runtime import verification is unavailable because the venv base interpreter is access denied.

## Task 3: Supply COI's Groq client and runtime configuration

**Files:**
- Create: `agents/coi/groq_client.py`
- Modify: `agents/coi/extractor.py`
- Modify: `agents/coi/models/llm.py` only where its import needs the same adapter
- Create: root `.env.example`
- Create: root `requirements-agents.txt`
- Use: `agents/coi/compose.yaml`

**Interfaces:**
- Produces `GroqError` and `groq_chat_completion(prompt, model=None, temperature=0, json_mode=False, timeout=...)` for the COI extraction and optional package helper call sites.
- Reads `GROQ_API_KEY`, `GROQ_API_BASE_URL`, `GROQ_MODEL`, `LLM_TIMEOUT`, and `LLM_MAX_RETRIES` from environment configuration.

- [x] Add the client adapter with JSON-mode handling, bounded retry/timeout behavior, and errors that do not include secrets.
- [x] Change COI imports to the local adapter while leaving its extraction prompts and verification policy intact.
- [x] Load the Groq model and base URL from COI's existing configuration; use its `LLM_TIMEOUT` and `LLM_MAX_RETRIES` values.
- [x] Document Neo4j and Groq variables without adding credentials.
- [x] List required direct dependencies once in `requirements-agents.txt` using compatible integrated dependency ranges.

## Task 4: Implement the contract coordinator

**Files:**
- Create: `agents/contract_coordinator.py`
- Modify: `agents/cr/analyze_contract.py`
- Modify: `agents/cr/models/inference.py` only if package import compatibility requires it

**Interfaces:**
- `analyze_contract(file_path: str, operator_input: dict) -> dict` returns `document`, `cr`, `cl`, `coi`, `le`, and `warnings`.
- Shared `clauses` are produced once and passed unchanged to CR, CL, and COI.
- `operator_input` contains `client_entity`, `counterparty_entity`, optional `additional_entities`, the seven LE entities, and `clause_deviation_score`.

- [x] Read bytes and filename, call shared `extract_text`, then call `split_clauses` once.
- [x] Run the existing LegalBERT predictor against each shared clause and retain clause IDs/sections in every result; absent checkpoints return an explicit unavailable status.
- [x] Call CL directly with the shared clauses; mask sensitive `value` fields when constructing saved/exported results.
- [x] Build COI entity aliases, extract relationships from the shared clauses through Groq, write the document to Neo4j, then run the bounded conflict analysis.
- [x] Construct `LexState` with the operator's LE feature values and COI graph result; call LE only when COI status is complete and `conflict_flag` is 0 or 1.
- [x] Return separate statuses and original agent evidence; do not calculate an aggregate score or invoke `LocalLegalLLM`.

## Task 5: Connect CLI and reports

**Files:**
- Modify: `agents/cr/analyze_contract.py`
- Modify: `agents/cr/reporting/document_report.py`
- Create: `agents/README.md`

**Interfaces:**
- The contract CLI accepts the existing file path, prompts for COI parties, then prompts for LE-only values with the LE schema's numeric bounds. Unknown LE values can be skipped.
- JSON/PDF output includes separate sections and per-agent statuses.

- [x] Route the existing contract entry point through `analyze_contract` in the coordinator.
- [x] Render CR, CL, COI, and LE findings separately; mask CL values in the report.
- [x] Add warnings for skipped/incomplete agents and the synthetic-data limit on the LE score.
- [x] Document setup, CR checkpoint path, Neo4j startup, Groq environment configuration, and the interactive prompts.
- [ ] Manually run one contract end-to-end; unavailable because `.env` credentials and `checkpoints/best_model.pt` are not configured, and the sandbox cannot execute the venv Python interpreter.

## Self-review

- Spec coverage: shared extraction, agent placement, direct Groq COI ingestion, COI completeness gating, LE feature routing, separate scores, masked CL output, and no final LLM are each assigned above.
- Interface consistency: `split_clauses` output is shared; COI receives the same clause shape; LE receives `LexState` rather than the dict currently used in the optional injected-agent branch.
- Limitations: Neo4j and Groq credentials/services are runtime configuration. The supplied LE score remains a synthetic-data model output. The optional LDI embedding API is not needed for direct one-contract analysis.
