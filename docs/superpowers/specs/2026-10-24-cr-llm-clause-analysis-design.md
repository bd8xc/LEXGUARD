# CR LLM Clause Analysis Design

## Intent

Add grounded LLM analysis to the integrated contract workflow. For every clause, combine CR's LegalBERT signal with candidate provisions retrieved from the Indian Contract Act RAG, then ask the configured local LLM to produce the established clause-analysis format. Keep CL, COI, and LE outside the LLM; retain their independent results and status flags in the final contract JSON.

## Goals

- Reuse the existing CR predictor, `IndianLegalRAG`, `LocalLegalLLM`, and the remembered clause-analysis structure.
- Load the predictor, RAG corpus, and LLM client once per contract run; process each clause through them and retain clause ID and section metadata.
- Store each clause's clause text, LegalBERT risk signal, retrieved Indian-law passages, and grounded LLM analysis in the CR result.
- Preserve separate top-level CL, COI, and LE outputs and statuses in the final JSON; do not send those outputs to the LLM.
- Keep the clause-level LLM's human-review requirement and evidence/relevance distinctions.

## Non-goals

- No cross-agent synthesis or LLM review of CL, COI, or LE.
- No combined numerical score across agents.
- No changes to model training, RAG corpus, or other agents' decision logic.
- No switch to remote/GPU inference in this change; keep the LLM endpoint configurable for a later host change.

## Approaches

1. **One request per clause (selected).** Reuse the existing clause-level LLM schema and process each clause independently. This directly preserves the established analysis format and makes results traceable, at the cost of one LLM request per clause.
2. **One batched request for all clauses.** This reduces request overhead but requires a larger response and makes per-clause parsing and failure recovery more complex. It does not match the current standalone analyzer's interaction pattern as closely.

## Workflow

1. Extract and split the contract once using the shared ingestion pipeline.
2. Initialize CR's predictor and Indian Contract Act RAG once, then for each non-empty clause run the CR hybrid prediction and retrieve candidate legal provisions.
3. Send only that clause, its CR signal, and its retrieved provisions to `LocalLegalLLM`. Do not include CL, COI, or LE outputs or flags in this request.
4. Attach the LLM response to that clause's CR record, preserving the existing display format fields: clause; LegalBERT prediction, score, class scores, and window count; retrieved law with rank, section, heading, and similarity; grounded analysis with assessed risk, model agreement, evidence sufficiency, human-review status, summary, reasoning, relevant and weak sections, concern, and mitigation; and the interpretation note.
5. Save the clause analyses under `cr` in the contract JSON. Keep `cl`, `coi`, and `le` sections, their statuses/flags, warnings, and outputs as separate top-level fields. An unavailable LLM or a failed clause analysis must be represented as an explicit CR/LLM error status for that clause and must not erase other agent results.

## Constraints and safety

- Retrieved provisions are candidate legal context; similarity alone does not establish relevance or a violation.
- CR scores are learned model signals, not calibrated probabilities or legal conclusions.
- Preserve the existing masking of confidentiality findings in exported results.
- Keep human review required for automated legal analysis.
- Keep current local Ollama use while allowing endpoint/model configuration for a future GPU-hosted compatible service.

## Approval boundary

This document describes the requested behavior and the selected one-request-per-clause approach. Implementation starts after the user approves this design.
