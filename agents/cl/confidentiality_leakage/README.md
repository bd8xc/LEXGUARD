# Confidentiality detection package

`agent.py` combines detector findings for a document. `detectors/` identifies structured personal data, sensitive data, business-confidential content, and context entities. `classifier.py` labels and deduplicates findings, `scorer.py` produces a bounded risk score, and `schemas.py` defines the response. `router.py` supports the optional indexed LDI API.

The root web app calls `ConfidentialityLeakageAgent.analyze` with clauses and redacts raw finding values before returning JSON. The optional router can read clauses from ChromaDB through the shared `ingestion_pipeline/ldi` vector store.
