# Conflict of Interest (COI)

`ConflictOfInterestAgent` searches a Neo4j graph for bounded, evidence-bearing paths between a client, counterparty, and other named entities. Incomplete or unresolved searches do not produce a safe conflict flag. The web app invokes the agent through the root coordinator.

From the repository root, set the Neo4j values in `.env`, then run:

```powershell
docker compose --env-file .env -f agents/coi/compose.yaml up -d
.\.venv\Scripts\python.exe -m coi --client "Alpha Corp" --counterparty "Beta Technologies" --doc-id DEMO
```

The root Swagger UI exposes the same routes as `/api/coi/check`, `/api/risk/assess`, and `/api/le/predict`. The standalone API remains `coi.api.main:app` with the original paths. The isolated LE route accepts caller-supplied graph results; use the combined routes for a COI-verified handoff. `graph_manager.py` owns database access, `conflict_agent.py` owns search policy, and `extractor.py` plus `ingester.py` handle optional document ingestion. `ldi/pipeline.py` is the COI PDF-to-graph wrapper; the shared indexed LDI pipeline is at `../../ingestion_pipeline/ldi`.

`legacy-export.json` and `lexguard_db` preserve the Kuzu migration source. Imported legacy relationships lack source clauses and stay unverified. `migrate_kuzu.py` provides export and import commands; the local `.legacy-export` environment is only for the one-time export. Tests live in [tests](tests/README.md).
