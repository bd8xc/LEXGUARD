# Local Contract Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a localhost browser interface to the integrated contract workflow while keeping the CLI and its terminal progress output.

**Architecture:** Add structured progress events to the existing coordinator and continue printing each message in the terminal. A FastAPI service runs one analysis job at a time, streams events with SSE, and serves a small HTML/CSS/JavaScript frontend from the same origin. The page submits a contract and optional agent inputs, then renders the existing result and report downloads.

**Tech Stack:** Python, FastAPI, Uvicorn, Starlette static files/streaming responses, HTML, CSS, browser JavaScript, existing analysis coordinator.

**Spec:** `docs/superpowers/specs/2026-10-24-local-contract-web-app-design.md`

## Global Constraints

- Bind the service to `127.0.0.1`; do not enable LAN sharing or CORS.
- Preserve the CLI and print the same progress events to its terminal while publishing them to the browser.
- Process no more than one analysis at a time.
- Do not send CL, COI, or LE results to the LLM; render them separately from CR clause results.
- Constrain uploads and report downloads to the configured contract and output directories.
- Do not log contract clause text or LLM prompts in progress events.
- Keep CL masking, human-review status, and existing agent warnings intact.
- Do not add or run tests unless requested; verify with syntax checks and a manual local run when the Python environment is available.

## Review Focus

- Browser connects after the job has already emitted events: SSE must replay stored progress, then continue live events.
- Browser refreshes or disconnects: progress history and completed result remain accessible by job ID while the server process remains running.
- Two users submit quickly: the single worker queues the second analysis rather than loading a second set of models concurrently.
- Unsupported or too-large upload: reject before queuing analysis and return a useful validation error.
- User-controlled filenames/job IDs: never allow path traversal when saving or downloading files.
- Worker raises an error: publish a terminal error event and expose a safe job error without losing any result already produced by the coordinator.
- User-entered contract text or agent output contains HTML: render as text, never executable markup.

## Files

- Modify `agents/contract_coordinator.py`: accept a progress callback, emit structured progress while preserving terminal printing, provide a reusable CR/RAG runtime loader, and emit extraction/segmentation/agent completion updates.
- Create `backend/__init__.py`, `backend/jobs.py`, and `backend/app.py`: warm reusable CR/RAG/LLM-client state once at server startup, then provide the serialized in-memory job manager, FastAPI routes, SSE event history, upload validation, and constrained report downloads.
- Create `web/index.html`, `web/app.js`, and `web/styles.css`: implement upload/input form, progress bar/log, results view, and report links.
- Modify `requirements-agents.txt`: add FastAPI, Uvicorn, and multipart form dependencies.
- Modify `agents/README.md`: document install, local server command, URL, form inputs, and retained CLI command.

---

### Task 1: Add a reusable structured progress callback to the coordinator

**Files:**
- Modify: `agents/contract_coordinator.py`

**Interfaces:**
- Change signature to `analyze_contract(file_path: str | Path, operator_input: dict[str, Any] | None = None, progress_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]`.
- Each event contains `stage`, `message`, `percent`, and optional `clause_index`, `clause_total`, and `clause_id`.
- Every event is printed with `flush=True`; when provided, the callback receives the same event. Callback failures must not stop analysis.

- [ ] Add a single progress emission helper and route existing CR/RAG/LLM progress lines through it.
- [ ] Add `ContractAnalysisRuntime` and `load_contract_runtime()` to load LegalBERT, India-law RAG corpus/embeddings, and the LLM client once; allow `_run_cr` to reuse an injected runtime or load one for standalone CLI use.
- [ ] Emit start/completion events for document extraction, segmentation, each agent, report generation, and overall completion.
- [ ] Keep percent coarse: overall pipeline events are descriptive; CR clause progress is based on completed clauses, not estimated duration.
- [ ] Leave `run_cli()` calling `analyze_contract()` without a callback so current terminal progress remains visible.

### Task 2: Add a local serialized job manager and FastAPI API

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/jobs.py`
- Create: `backend/app.py`

**Interfaces:**
- `POST /api/contracts` accepts multipart `file`, optional `client_entity`, `counterparty_entity`, and seven optional LE features plus `clause_deviation_score`; returns `{"job_id": "...", "status": "queued"}`.
- `GET /api/jobs/{job_id}` returns `job_id`, `status` (`queued`, `running`, `complete`, or `failed`), latest progress, result when complete, and error when failed.
- `GET /api/jobs/{job_id}/events` streams named SSE events with monotonic event IDs and replays events emitted before the connection opened.
- `GET /api/jobs/{job_id}/reports/{kind}` serves only that job's `json` or `pdf` output.
- Job state and progress history are held in memory; one `ThreadPoolExecutor(max_workers=1)` runs contract analysis.
- On analysis, the coordinator prints each callback event once, then the callback appends it to that job's history/condition.

- [ ] Implement job state/history with a per-job condition so SSE can replay missed events and wait for new ones without polling the analysis.
- [ ] Load the reusable model/RAG runtime once in FastAPI lifespan and pass it to every serialized job; a server restart reloads it once.
- [ ] Validate extension (`.pdf`, `.docx`, `.txt`) and a 50 MiB upload limit before enqueueing; save with UUID-derived safe names under `contracts/uploads/`.
- [ ] Validate LE ranges using the existing `LE_FEATURES` ranges; if required LE inputs are incomplete, pass only supplied values so the existing coordinator marks LE skipped.
- [ ] Mark queued/running/complete/failed states and publish terminal events; retain a coordinator result if report generation only produced a warning.
- [ ] Resolve and verify download paths are inside `agents/cr/outputs/`; reject unknown job IDs or report kinds.
- [ ] Serve `/` and `/assets/*` from the `web/` directory; bind behavior is documented to run with `127.0.0.1`.

### Task 3: Build the simple browser interface

**Files:**
- Create: `web/index.html`
- Create: `web/app.js`
- Create: `web/styles.css`

**Interfaces:**
- The form submits multipart data to `POST /api/contracts`.
- On response, browser opens `EventSource` for `/api/jobs/{job_id}/events`, displays queued/running stage and clause updates, and updates progress from event `percent`.
- On complete, fetch `/api/jobs/{job_id}` and render the result.

- [ ] Add upload control, client/counterparty fields, LE range fields, optional inputs, and submit state.
- [ ] Show progress bar plus append-only progress messages without exposing clause text.
- [ ] Render document metadata, `agent_statuses`, warnings, clause model scores/retrieved law/grounded analysis, COI flags/findings, and LE result as separate sections.
- [ ] Render CL summary counts separately and CL findings in a table with clause, type, sensitivity, category, masked value, and source; render processing activities in a compact table.
- [ ] Render user data with `textContent`/DOM nodes rather than injecting result strings as HTML.
- [ ] Add JSON/PDF links using the report endpoint; show useful error/skip states and support a page refresh by checking job status from its job ID if retained in the page.

### Task 4: Add dependencies and run instructions

**Files:**
- Modify: `requirements-agents.txt`
- Modify: `agents/README.md`

- [ ] Add bounded FastAPI, Uvicorn, and `python-multipart` dependencies.
- [ ] Document install and run commands using `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000` and opening `http://127.0.0.1:8000`.
- [ ] Document the browser form, serialized processing, progress output in the backend terminal, and retained CLI command.

### Task 5: Manual verification

**Files:**
- No additional files unless a verification finding requires an implementation correction.

- [ ] Run syntax/import checks for coordinator and backend when a runnable Python interpreter is available.
- [ ] Start the server locally and confirm the landing page and upload form load.
- [ ] Submit the synthetic demo contract with Alpha Org / Alpha Labs and the same valid LE values used in the successful CLI run.
- [ ] Confirm clause progress appears both in the server terminal and browser, including each clause's LLM send/receive messages.
- [ ] Confirm all agent statuses, separate results, and JSON/PDF download links appear after completion.
- [ ] Confirm a second submitted job waits in the queue and an unsupported extension is rejected before starting analysis.

---
