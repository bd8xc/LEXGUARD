# Local Contract Web App Design

## Intent

Move the integrated contract workflow from a prompt-only CLI to a local browser app while retaining the CLI and its terminal progress messages. The app will accept a contract and operator inputs, show live clause-by-clause progress, and display/download the existing JSON and PDF analysis outputs.

## Current State

- `agents.contract_coordinator.analyze_contract(file_path, operator_input)` already runs CR, CL, COI, and LE and writes JSON/PDF results.
- The CLI in `agents.contract_coordinator.run_cli()` currently gathers contract, COI, and LE inputs interactively.
- CR currently prints clause progress directly. The browser needs the same events without silencing terminal output.
- There is a separate COI API, but it does not expose the complete contract workflow or its CR/RAG/LLM results.
- There is no integrated frontend. The successful demo result contains the data needed for the clause and agent result views.

## Goals

- Serve a simple local web page from the Python backend, with contract upload and inputs for client/counterparty and LE fields.
- Start analyses as background jobs and show progress events in the page while the same progress messages continue appearing in the server terminal.
- Present overall agent statuses, each clause's remembered CR/RAG/LLM output, and the independent CL, COI, and LE findings.
- Let the user download the generated JSON and PDF reports.
- Keep the current CLI usable through the same coordinator flow.
- Keep the first version bound to localhost; process only one analysis at a time to avoid concurrent model memory pressure.
- Load LegalBERT, the Indian Contract Act RAG corpus/embeddings, and the configured LLM client once when the backend starts; reuse those objects for every uploaded contract until the server restarts.

## Non-goals

- No user accounts, public hosting, LAN sharing, or remote LLM changes in this version.
- No cross-agent final synthesis LLM.
- No rewriting or replacing any agent's inference or scoring logic.
- No persistent job database or analysis history beyond the generated contract and report files.
- No React, Node, or separate frontend build pipeline.

## Approaches

1. **FastAPI plus a small Python-served HTML/CSS/JavaScript frontend (selected).** One local service serves the page, API, analysis jobs, and progress stream. It adds a small amount of backend/frontend code without requiring Node or a separate deployment.
2. **FastAPI plus React/Vite.** This supports a richer application interface, but introduces a second toolchain and separate build/dev workflow before the current single-user workflow needs it.
3. **Run the CLI as a subprocess and tail its output.** This would preserve the current output with little coordinator work, but makes structured job states, progress event types, and error/report handling fragile.

Option 1 is selected because this is a local single-user tool and the desired interface is a contract form, live progress, results, and downloads.

## User flow

1. Open the local app in a browser.
2. Select a PDF, DOCX, or TXT contract; enter the COI parties and optional LE values, with validation matching current CLI ranges.
3. Submit and receive a job ID. The page opens a progress stream and shows initialization and clause-stage updates, including “Sending clause 1/N to the LLM” and “Received analysis for clause 1/N.”
4. The server terminal prints the same progress messages.
5. When complete, show CR/CL/COI/LE statuses, per-clause analysis, CL findings in a well-formatted table with summary counts, other agent findings and warnings, and JSON/PDF download buttons. On failure, show the error and retain other completed agent data where the coordinator provides it.

## Proposed architecture

- Add a FastAPI application under `backend/` that serves static web assets and the integrated contract API.
- Add a progress callback to the coordinator. Each event carries a stable job ID, stage, clause index/count where applicable, message, and coarse overall percent. Without a callback the CLI continues printing progress; the web job callback both prints and publishes the event.
- Warm the reusable CR predictor, RAG model/corpus embeddings, and LLM client during FastAPI startup. Print startup stages in the server terminal and inject the resulting runtime into each serialized analysis job.
- `POST /api/contracts` accepts a multipart upload and form values, validates supported file type and LE input ranges, stores the upload beneath the existing `contracts/` directory with a safe unique name, enqueues one job, and returns its ID.
- Run analysis jobs through a single-worker executor. Keep job status, progress subscribers, and final results in memory for this first local version.
- `GET /api/jobs/{job_id}/events` streams progress with Server-Sent Events. `GET /api/jobs/{job_id}` returns state and final agent result when complete.
- `GET /api/jobs/{job_id}/reports/{kind}` serves only that job's generated JSON or PDF report.
- Serve `web/index.html`, JavaScript, and CSS from the same FastAPI origin. The page submits the form, subscribes to SSE, renders results safely, and links to reports.
- Render CL findings as a table with clause, type, sensitivity, category, masked value, and source; show CL summary counts separately and processing-activity findings in a compact table.
- Bind the service to `127.0.0.1`. Do not enable CORS or listen on LAN interfaces in this version.
- Preserve `python -m agents.cr.analyze_contract` as the CLI entry point.

## Constraints and safety

- Preserve CL masking in exported data and the existing review-required warnings.
- Do not put contract text or full LLM prompts into progress logs; progress messages use job IDs, clause IDs, and stage labels only.
- Keep job/report paths constrained to the configured contracts and CR outputs directories.
- A service restart may clear in-memory job state; saved contract/report files remain on disk.
- Progress percentages are coarse clause-completion indicators, not estimates of remaining wall-clock time. Stage text remains visible for CR, RAG, and LLM work.
- Each new contract is still extracted and split separately; only process-wide model/client/corpus state is reused. Restarting the backend reloads that state once.

## Open implementation choices

- Exact HTML layout and styling are implementation choices; keep the form concise and make progress and agent status visible before the long clause details.
- Upload size limit is an implementation choice and should be conservative for a local demo.
- Existing JSON fields remain the source of truth for rendering; do not derive a combined score.

## Approval boundary

This design implements option 2 selected in the conversation: a local FastAPI service with a small Python-served frontend, shared terminal/browser progress, serialized background jobs, and no Node frontend. Implementation starts after the user approves this design.
