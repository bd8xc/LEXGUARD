# LDI API

`main.py` defines a reusable router for upload, chunking, embedding, and search endpoints. The root app includes it under `/api/ingestion/` in the unified Swagger UI. The optional standalone `ingestion_pipeline.ldi.app.main:app` still serves the same routes at their original paths and includes the indexed CL router. Install the root `requirements.txt` before starting either app.
