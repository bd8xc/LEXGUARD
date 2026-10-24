# Confidentiality Leakage (CL)

The CL agent detects personal, sensitive, and business-confidential content in clauses. The root coordinator sends it every contract paragraph directly and redacts finding values in the web API response. Direct analysis does not require ChromaDB.

The unified Swagger UI exposes direct text analysis at `/api/cl/analyze` and indexed document analysis at `/api/ingestion/confidentiality/analyze`.

`confidentiality_leakage/` contains detection, classification, scoring, schemas, and the optional standalone router. Indexed document ingestion and search live in [the shared LDI pipeline](../../ingestion_pipeline/ldi/README.md). All dependencies are listed in the root `requirements.txt`.

Run focused tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q ingestion_pipeline/ldi/tests/test_confidentiality_leakage_agent.py ingestion_pipeline/ldi/tests/test_confidentiality_document_resolution.py
```
