# Legal Document Intelligence (LDI)

This optional service extracts PDF and DOCX content, splits clauses, creates sentence embeddings, stores them in ChromaDB, and exposes semantic search. It also mounts the CL indexed-document router. The root web app uses `ingestion_pipeline/document_input.py` and direct CL analysis without starting this service.

From the repository root, install `requirements.txt`, then start `python -m uvicorn ingestion_pipeline.ldi.app.main:app --host 127.0.0.1 --port 8001`. Routes include `/ingest/`, `/chunk/`, `/ingest-multi/`, `/chunk-multi/`, `/embed-multi/`, `/search/`, and `/confidentiality/*`. The default index lives under `ingestion_pipeline/chroma`.

Run focused CL tests with `python -m pytest -q ingestion_pipeline/ldi/tests/test_confidentiality_leakage_agent.py ingestion_pipeline/ldi/tests/test_confidentiality_document_resolution.py`. The chunk-quality test may download a sentence model and reads the PDF fixtures in `tests/sample legal docs/`.
