# Confidentiality detection package

`agent.py` combines detector findings for a document. `detectors/` identifies structured personal data, sensitive data, business-confidential content, and context entities. `classifier.py` labels and deduplicates findings, `scorer.py` produces a bounded risk score, and `schemas.py` defines the response. `router.py` supports the optional indexed LDI API.

The LEXGUARD terminal pipeline calls `ConfidentialityLeakageAgent.analyze`
with the submitted clause. Its display masks finding values. The optional
router can read clauses from ChromaDB through the shared
`ingestion_pipeline/ldi` vector store, which is not included in this project.
