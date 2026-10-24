# CR LLM Clause Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-clause grounded LLM analysis to the integrated contract JSON using only CR and India Contract Act RAG context.

**Architecture:** Extend the existing contract coordinator to initialize CR, RAG, and the local LLM once for a contract. For each clause, run CR prediction, retrieve law, and invoke the LLM; keep CL, COI, and LE independent and outside the prompt. Store all per-clause output under `cr.clauses` and preserve other agent outputs as separate top-level sections.

**Tech Stack:** Python, existing PyTorch/Transformers CR inference, SentenceTransformers RAG, requests-based Ollama client, existing JSON/PDF reports.

**Spec:** `docs/superpowers/specs/2026-10-24-cr-llm-clause-analysis-design.md`

## Global Constraints

- Only the current clause's text, CR signal, and its retrieved Indian Contract Act passages may be sent to the LLM.
- CL, COI, and LE outputs/flags remain independent and are never added to the LLM prompt.
- A clause's output retains the remembered LegalBERT, retrieved-law, grounded-analysis, and interpretation-note fields.
- A failed LLM clause analysis is explicit and must not erase other clause results or agent results.
- Keep human review required; LegalBERT outputs are not calibrated probabilities and RAG matches are candidate context.

## Review Focus

- CR checkpoint absent or initialization failure: CR status should be unavailable and other agents should still complete.
- LLM server/model unavailable: per-clause LLM state should be explicit without dropping raw CR and RAG results.
- Empty/failed retrieval: LLM must receive the no-provisions condition and avoid unsupported statutory claims.
- Malformed or incomplete LLM JSON: preserve safe fallback analysis and require human review.
- CL masking: sensitive values must remain masked in saved JSON and PDF after CR text/analysis is attached.

## Files

- Modify `agents/contract_coordinator.py`: initialize and run clause-level CR → RAG → LLM; export the per-clause structure; preserve independent agent statuses and safe masking.
- Modify `llm/local_llm.py`: allow model and base URL configuration from environment while preserving its current defaults and clause JSON format; return a safe validated fallback for malformed responses.
- Modify `agents/cr/reporting/document_report.py` only if required to display the new per-clause LLM fields in the generated PDF without changing other agent sections.

---

### Task 1: Make the local LLM endpoint configurable and normalize its analysis result

**Files:**
- Modify: `llm/local_llm.py`

**Interfaces:**
- Preserve `LocalLegalLLM(model_name=None, base_url=None)` and `analyze(clause, model_result, retrieved_law)`.
- Keep defaults `qwen2.5:1.5b` and `http://localhost:11434`; read optional `LEXGUARD_LLM_MODEL` and `LEXGUARD_LLM_BASE_URL` environment values.
- Ensure all return paths contain the remembered analysis keys and enforce `human_review_required=True` unless valid parsed analysis explicitly has it true (the policy requires review, so output must remain true).

- [ ] Inspect existing response/fallback fields and map them to the design's clause schema.
- [ ] Implement environment-based defaults and safe response normalization without changing prompt semantics.
- [ ] Review the resulting module for import/runtime errors and confirm no agent output is accepted as prompt input.

### Task 2: Integrate CR, RAG, and LLM per clause in the coordinator

**Files:**
- Modify: `agents/contract_coordinator.py`

**Interfaces:**
- `_run_cr(clauses)` returns CR status plus ordered clause records including `clause_id`, `section`, original CR prediction, retrieved law, and `analysis`.
- Preserve top-level `cr`, `cl`, `coi`, and `le` fields and their status semantics.
- Each prompt receives one clause text, that clause's CR prediction, and that clause's retrieved provisions only.

- [ ] Inspect CR raw inference shape and current result masking/report export flow.
- [ ] Initialize the predictor, `IndianLegalRAG`, and `LocalLegalLLM` once; per clause call prediction, `retrieve(text, top_k=5)`, then LLM analysis.
- [ ] Retain successful CR/RAG results if an individual LLM request fails, recording a per-clause LLM error and requiring review.
- [ ] Ensure only clause analysis is added under `cr`; do not pass CL/COI/LE to any LLM method.
- [ ] Keep exported clause text/evidence subject to the existing CL masking path and retain all independent top-level agent results.

### Task 3: Align JSON and PDF reporting with the integrated clause result

**Files:**
- Modify: `agents/contract_coordinator.py`
- Modify only if needed: `agents/cr/reporting/document_report.py`

**Interfaces:**
- JSON clause records preserve CR signal, `retrieved_law`, `analysis`, and clause metadata.
- Final JSON keeps `cl`, `coi`, and `le` outside the CR clause list with statuses/flags intact.

- [ ] Inspect current PDF report inputs to determine whether the new nested fields are already rendered.
- [ ] Update report mapping only where needed to include each clause's remembered headings and structured analysis.
- [ ] Confirm PDF and JSON paths remain generated and PDF failure does not remove JSON output.

### Task 4: Verify the integration without adding tests

**Files:**
- No additional files unless verification finds a required implementation correction.

- [ ] Run syntax/import checks for modified modules.
- [ ] Use a small mocked/manual coordinator invocation to confirm one prompt per clause contains CR and RAG only, and top-level CL/COI/LE stay separate.
- [ ] Inspect an emitted JSON sample for all remembered per-clause fields, explicit per-clause failure handling, and masking.
- [ ] Report verification commands and any unavailable external dependency (checkpoint, Ollama, Neo4j) accurately.
