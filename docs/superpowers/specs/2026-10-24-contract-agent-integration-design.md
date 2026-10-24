# Contract Agent Integration Design

## Intent

Integrate the shared Ingestion Pipeline 2 with the existing contract risk analyzer (CR), Confidentiality Leakage (CL), Conflict of Interest (COI), and Litigation Exposure (LE) agents into one contract-level workflow. The first version produces structured, per-agent results without a final synthesis LLM. COI may use its existing Groq-backed relationship extraction while ingesting a contract.

## Goals

- Keep the current contract analyzer under `agents/cr` and make it the document/clauses entry point.
- Use Ingestion Pipeline 2 as the shared document extraction and clause segmentation layer so each agent sees the same contract text and clause IDs.
- Place the additional agent packages under `agents/cl`, `agents/coi`, and `agents/le`.
- Run CR over the segmented clauses and pass those same clauses to CL.
- Let COI ingest contract clauses into Neo4j, run its bounded conflict search, and preserve evidence and result status.
- Run LE only when its required feature values are supplied and COI returns a complete, known conflict flag.
- Produce one machine-readable contract result and include the agent-specific findings in existing reports.
- Prompt the operator for party names and LE feature values that the existing parser does not derive.

## Non-goals

- No final LLM synthesis or generated legal conclusion in this phase.
- No automatic extraction of the client, counterparty, or LE feature values. The COI relationship extraction call through Groq is the only LLM use in this phase.
- No combined numeric risk score across agents. Their scores have different meanings and scales.
- No retraining or recalibration of the supplied models.
- No duplicate document parsing or clause segmentation in agent adapters.
- No change to the source legal-risk or confidentiality policies beyond the adapters needed to run them together.

## Anti-goals

- Do not treat missing or incomplete COI evidence as a clean result or as `conflict_flag = 0`.
- Do not present LE's synthetic-data score as a calibrated real-world probability.
- Do not pass raw detected personal or confidential values into exported reports by default; use the CL masking helper while retaining type, category, section, and text offsets.
- Do not call the existing final LLM from the contract workflow.

## Approaches

1. **Call every package directly from `ContractAnalyzer`.** This is a small first patch, but it couples document processing, agent configuration, and report generation in one large file.
2. **Add a contract-level coordinator with explicit agent inputs and outputs (selected).** Ingestion Pipeline 2 reads and segments a document once; a coordinator invokes CR, CL, COI, and LE and returns structured results. This adds a small interface layer and gives later agents a stable place to connect.
3. **Run each agent as a separate CLI/service only.** This avoids shared code but does not provide the requested integrated contract review.

Approach 2 is selected because more agents will be added and their outputs need a consistent contract-level handoff.

## Proposed flow

1. Ingestion Pipeline 2 reads the supported PDF, DOCX, or TXT contract with `document_input.extract_text`, then segments the text once with `ldi.chunking.clause_splitter.split_clauses`.
2. The coordinator sends that same clause list, with stable clause IDs and section metadata, to CR, COI, and CL. CR predicts clause-level risk using LegalBERT; CL returns a document confidentiality report and its sensitive values are masked in exported output; COI uses Groq extraction to write evidence-bearing relationships to Neo4j before its bounded graph search. COI's duplicate PDF parser and LDI index are not used in this direct contract workflow.
3. The CLI collects the additional LE feature values separately and sends them directly to LE. COI's `conflict_flag` is supplied as the graph feature. LE runs `predict_with_explanation` with a proper `LexState` only when COI provides a complete, known flag.
4. The coordinator returns a structured result with separate CR, CL, COI, and LE sections, including per-agent status and warnings. Existing JSON/PDF reporting can render the result without combining scores or calling the final LLM.

If COI is incomplete, unknown, or unavailable, the result preserves that status and LE is skipped, even if the operator supplied the other LE fields. Groq-extracted relationships are unverified by default; an unverified-only possible conflict therefore remains unknown under the COI agent's current policy and cannot be converted into a known flag. If a required LE feature is invalid or missing, LE is marked as not run with a clear reason. The default COI graph container is Neo4j from the supplied Compose file.

## Package and file layout

- `agents/cr/`: existing CRA code, datasets, model configuration, and reports.
- `ingestion_pipeline/`: shared document extraction and clause chunking from `ingestion_pipeline.zip`; keep it at the repository root so all agents can import it.
- `agents/cl/`: confidentiality detector package from `cl.zip`, excluding Python bytecode and generated caches.
- `agents/coi/`: COI package from `coi.zip`, excluding Python bytecode, logs, and generated caches.
- `agents/le/`: LE package and model artifact from `le.zip`, excluding Python bytecode and egg-info.
- `agents/contract_coordinator.py`: input collection, agent execution order, result envelope, and per-agent status handling.
- `agents/coi/groq_client.py`: the small Groq adapter required by the COI archive; COI's missing imports will be updated to use this local module. It reads credentials from environment configuration and is used only by relationship extraction.
- `agents/README.md`: setup, expected prompts, result structure, and Neo4j/Groq configuration.
- Root `.env.example`: names and descriptions for required Neo4j and Groq settings, with no credentials.

The current root `llm/` package remains separate and unused by this workflow.

## Input contract

The CLI continues to accept a contract path. Ingestion Pipeline 2 produces the shared clause list for CR, COI, and CL. The CLI then collects:

- COI: document ID (default from filename), client name, counterparty name, and optional additional entities.
- LE-only additional input: `deal_size`, `liability_cap`, `auto_renewal`, `jurisdiction_risk`, `indemnification_clause`, `dispute_history`, `governing_law_clarity`, and `clause_deviation_score`, using the ranges defined by the LE feature schema. These values are passed directly to LE; they are not sent to CR, COI, or CL.

The operator may skip LE if values are unknown. The coordinator must not invent or infer them. If COI cannot complete, LE is skipped regardless of entered LE values.

## Result shape

The top-level result contains document metadata and separate `cr`, `cl`, `coi`, and `le` sections. Each section includes a `status` (`complete`, `incomplete`, `unavailable`, or `not_run`) and its original agent output. A warnings list explains skipped agents and uncalibrated score limitations. Confidentiality finding values are masked in saved/exported reports.

No cross-agent `final_risk_score` is computed. LE's own probability and CL's bounded score remain labelled and interpreted independently.

## Constraints and known integration work

- COI requires a Neo4j service and environment configuration. Its archive calls `groq_client` but does not include that module, so the integration must supply the adapter before PDF/clauses can be ingested through Groq.
- Ingestion Pipeline 2's root `document_input.py` and `ldi/chunking/clause_splitter.py` provide the shared direct path. Its optional LDI API/index remains separate; the included `ldi/pipeline.py` is empty, so the coordinator will call the supplied extraction and chunking functions directly.
- COI's existing `le_integration.py` imports a package named `le` and constructs a dict for an injected model, while the supplied LE model expects a `LexState`. The coordinator will instantiate and call LE directly with `LexState` rather than rely on that incompatible optional handoff.
- CL's agent returns raw finding values; masking is currently a separate helper and must be applied by the coordinator when building exported results.
- LE documentation states its training labels are synthetic and its output is not a calibrated real-world litigation probability. Preserve that limitation in the result and report text.
- The integrated environment needs the existing CR dependencies plus COI's Neo4j/Groq and CL/LE dependencies. Dependency installation is part of implementation; model weights and secrets remain external configuration/artifacts where applicable.

## Open implementation choices

- Prompt wording, safe defaults, and validation messages for the CLI fields are implementation choices, using the ranges in the supplied LE schema.
- COI uses the existing graph schema, trigger relationships, and completeness rules without changing their semantics.
- Reports retain clause IDs/sections and COI evidence paths so a reviewer can trace each finding to its source.
