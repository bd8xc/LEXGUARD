# Conflict of Interest (COI)

COI extracts named entities from the contract and searches Neo4j for known relationships between the client and counterparty. The API can also accept explicit party hints; those names are searched alongside NER results. A clause-text shared-director pattern is reported as a potential finding and is labeled as unverified graph evidence.

## Configuration

Set these values in the repository root `.env` file:

```dotenv
NEO4J_URI=bolt://localhost:7688
NEO4J_USER=neo4j
NEO4J_PASSWORD=replace-with-a-strong-random-password
NEO4J_DATABASE=neo4j
COI_QUERY_TIMEOUT=15
```

Start the local Neo4j Community instance from the repository root:

```powershell
docker compose up -d neo4j
```

The browser is at `http://localhost:7475`; the application connects over Bolt on port `7688`. Configure the same password in `.env` before the database's first start. Do not commit `.env`.

## Seed a fictional graph

```powershell
python -m agents.coi.seed_demo_graph
```

The seeder creates 50 fictional companies, 50 fictional people, and 200 synthetic relationships. It is intended for local demonstration, not production data.

## Contract API

`POST /analyze-contract` accepts optional party hints:

```json
{
  "parties": {
    "client": "Alpha Orb Technologies Ltd",
    "counterparty": "Acme Components Pvt. Ltd",
    "additional": ["Aarav Mehta"]
  }
}
```

NER-detected names from `contract_text` are included in the graph search. COI returns `party_roles`, `entities`, `clause_findings`, and `graph_result`. `graph_result.status: "unknown"` or `entity_resolution_failed` indicates the lookup could not establish the requested party relationship; it is not a verified negative conflict result. Review graph status and evidence together.

The LE agent consumes the COI conflict flag. If the COI result has no conflict value, the current contract pipeline sends a fallback `0` to LE and labels its source in the response. This fallback means no positive COI result was available; it is not proof that the graph found no conflict.

## Data and limitations

- Ensure client and counterparty names match nodes in the graph, or add explicit aliases through the graph manager.
- NER can miss, merge, or misclassify names. Supplied party hints improve entity resolution but do not establish a relationship by themselves.
- Clause-text potential findings are not graph-verified.
- Relationship results depend on the completeness and freshness of the Neo4j data.
- Use synthetic data for demos; graph nodes and edges may contain personal or confidential information.
