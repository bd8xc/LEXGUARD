# Conflict of Interest (COI)

`ConflictOfInterestAgent` searches a Neo4j graph for bounded relationship paths among the entered client, counterparty, and additional entities. It reads existing graph facts. The current contract is not ingested into the graph.

## Local Neo4j

From the repository root, create a local `.env` from `.env.example` and replace `NEO4J_PASSWORD=replace_me` with a unique password. Keep `.env` private. Then start the dedicated container:

```powershell
docker compose --env-file .env -f agents/coi/compose.yaml up -d
```

The Compose service uses `neo4j:5.26-community`, persists data in named Docker volumes, and binds Bolt and Neo4j Browser to `127.0.0.1:7687` and `127.0.0.1:7474`. The same password in `.env` configures the container and the Python graph client. Neo4j's initial password applies only to a new data volume; changing `.env` later does not change an existing database password.

Check `http://127.0.0.1:8000/api/status` after starting the LexGuard backend. `coi: ready` means the configured Bolt connection authenticated successfully. The specialist API is `POST /api/tools/conflicts`; the guided review is at `/review`.

The new graph starts empty. Unknown names produce an unresolved COI result and cannot supply the conflict flag required by LE. Add relationship records from an approved source before using COI for a real review. `synthetic_graph.py` is a separate test fixture and should not be mistaken for real evidence.
