"""Neo4j storage. No database is opened at import time."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from functools import lru_cache
import hashlib
import json
import os

from neo4j import GraphDatabase, unit_of_work
from dotenv import load_dotenv
from pathlib import Path
from .domain import Edge, ENTITY_RELATIONSHIPS, TRAVERSABLE_RELATIONSHIPS, entity_key, entity_match_key


class GraphQueryError(RuntimeError):
    pass


class SearchLimitError(GraphQueryError):
    pass


class LexGraph:
    def __init__(self, *, uri=None, user=None, password=None, database=None, driver=None):
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        self.timeout = float(os.getenv("COI_QUERY_TIMEOUT", "15"))
        if driver is None:
            password = password or os.getenv("NEO4J_PASSWORD")
            if not password:
                raise GraphQueryError("Set NEO4J_PASSWORD before connecting")
            driver = GraphDatabase.driver(
                uri or os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                auth=(user or os.getenv("NEO4J_USER", "neo4j"), password),
                connection_timeout=5, connection_acquisition_timeout=5,
                max_transaction_retry_time=5)
        self.driver = driver

    def close(self):
        self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def setup_schema(self):
        with self.driver.session(database=self.database) as session:
            for label, prop in (("COIEntity", "key"), ("COISource", "doc_id"), ("COIClause", "key")):
                session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE").consume()

    @contextmanager
    def read_view(self):
        # One bounded transaction and a per-run neighbor cache.
        with self.driver.session(database=self.database) as session:
            with session.begin_transaction(timeout=self.timeout) as tx:
                yield GraphView(tx)

    def replace_document(self, doc: dict, clauses: list[dict]):
        """Validate first, then replace this document's facts in one transaction."""
        doc_id = str(doc.get("id", "")).strip()
        if not doc_id or not clauses:
            raise ValueError("A document id and at least one clause are required")
        rows = []
        ids = set()
        for clause in clauses:
            cid = str(clause.get("clause_id", "")).strip()
            if not cid or cid in ids or not isinstance(clause.get("text"), str):
                raise ValueError("Clauses require unique ids and string text")
            ids.add(cid)
            entities = {entity_key(e["name"]): {"key": entity_key(e["name"]),
                        "match_key": entity_match_key(e["name"]),
                        "name": e["name"].strip(), "label": e.get("label", "Entity")}
                        for e in clause.get("entities", [])}
            relations = []
            for rel in clause.get("relationships", []):
                source, target = entity_key(rel["from"]), entity_key(rel["to"])
                kind = rel["type"]
                if source not in entities or target not in entities or source == target or kind not in ENTITY_RELATIONSHIPS:
                    raise ValueError("Relationship endpoints or type are invalid")
                if type(rel.get("verified", False)) is not bool:
                    raise ValueError("verified must be Boolean")
                for key in ("valid_from", "valid_until"):
                    if rel.get(key):
                        date.fromisoformat(rel[key])
                if rel.get("valid_from") and rel.get("valid_until") and rel["valid_from"] > rel["valid_until"]:
                    raise ValueError("Invalid relationship date interval")
                relations.append({"source": source, "target": target, "type": kind,
                                  "verified": rel.get("verified", False), "evidence": rel.get("evidence", ""),
                                  "valid_from": rel.get("valid_from"), "valid_until": rel.get("valid_until")})
            key = hashlib.sha256(json.dumps([doc_id, cid]).encode()).hexdigest()
            rows.append({"key": key, "clause_id": cid, "text": clause["text"],
                         "entities": list(entities.values()), "relationships": relations})
        version = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

        @unit_of_work(timeout=self.timeout)
        def write(tx):
            # Lock the source before replacement to serialize updates to the same document.
            tx.run("MERGE (s:COISource {doc_id:$id}) SET s.version=$version, s.filename=$filename, "
                   "s.doc_type=$doc_type, s.updated_at=datetime()",
                   id=doc_id, version=version, filename=doc.get("filename", ""), doc_type=doc.get("type", "")).consume()
            prior_keys = [record["key"] for record in tx.run(
                "MATCH (s:COISource {doc_id:$id})-[:CONTAINS_CLAUSE]->(c:COIClause)"
                "<-[:EXTRACTED_FROM]-(n:COIEntity) RETURN DISTINCT n.key AS key", id=doc_id)]
            tx.run("MATCH ()-[r:COI_RELATES_TO {doc_id:$id}]->() DELETE r", id=doc_id).consume()
            tx.run("MATCH (s:COISource {doc_id:$id})-[:CONTAINS_CLAUSE]->(c:COIClause) DETACH DELETE c", id=doc_id).consume()
            for row in rows:
                tx.run("MATCH (s:COISource {doc_id:$id}) CREATE (c:COIClause {key:$key, clause_id:$cid, text:$text}) "
                       "CREATE (s)-[:CONTAINS_CLAUSE]->(c)", id=doc_id, key=row["key"], cid=row["clause_id"], text=row["text"]).consume()
                tx.run("UNWIND $entities AS e MERGE (n:COIEntity {key:e.key}) "
                       "ON CREATE SET n.name=e.name, n.label=e.label "
                       "SET n.match_key=e.match_key "
                       "WITH n MATCH (c:COIClause {key:$key}) MERGE (n)-[:EXTRACTED_FROM]->(c)",
                       entities=row["entities"], key=row["key"]).consume()
                tx.run("UNWIND $rels AS r MATCH (a:COIEntity {key:r.source}), (b:COIEntity {key:r.target}) "
                       "MERGE (a)-[e:COI_RELATES_TO {doc_id:$id, clause_id:$cid, type:r.type}]->(b) "
                       "SET e.verified=r.verified, e.evidence=r.evidence, e.valid_from=r.valid_from, e.valid_until=r.valid_until",
                       rels=row["relationships"], id=doc_id, cid=row["clause_id"]).consume()
            tx.run("MATCH (n:COIEntity) WHERE n.key IN $keys "
                   "AND NOT EXISTS { MATCH (n)-[:EXTRACTED_FROM]->(:COIClause) } "
                   "AND NOT EXISTS { MATCH (n)-[:COI_RELATES_TO]-() } DELETE n",
                   keys=prior_keys).consume()
            return {"status": "complete", "doc_id": doc_id, "version": version, "clauses": len(rows)}
        with self.driver.session(database=self.database) as session:
            return session.execute_write(write)


class GraphView:
    def __init__(self, tx):
        self.tx = tx

    def resolve_entities(self, names):
        requested = list(dict.fromkeys(names))
        exact_keys = [entity_key(name) for name in requested]
        match_keys = list(dict.fromkeys(entity_match_key(name) for name in requested))
        records = list(self.tx.run(
            "MATCH (e:COIEntity) WHERE (e.key IN $keys OR e.match_key IN $match_keys) "
            "AND EXISTS { MATCH (e)-[:EXTRACTED_FROM]->(:COIClause) } "
            "RETURN e.key AS key, e.name AS name",
            keys=exact_keys, match_keys=match_keys,
        ))
        by_key = {record["key"]: record["name"] for record in records}
        resolved = {}
        for name, exact in zip(requested, exact_keys):
            if exact in by_key:
                resolved[exact] = by_key[exact]
                continue
            normalized = entity_match_key(name)
            matches = {
                key: stored_name
                for key, stored_name in by_key.items()
                if entity_match_key(stored_name) == normalized
            }
            # Do not guess if punctuation normalization makes multiple graph
            # entities indistinguishable; leave the name unresolved instead.
            if len(matches) == 1:
                resolved.update(matches)
        return resolved

    def get_neighbors(self, key, *, as_of, limit):
        records = list(self.tx.run(
            "MATCH (a:COIEntity {key:$key})-[r:COI_RELATES_TO]-(b:COIEntity) "
            "WHERE r.type IN $types WITH r, properties(r) AS props "
            "WHERE (props.valid_from IS NULL OR props.valid_from <= $as_of) "
            "AND (props.valid_until IS NULL OR props.valid_until >= $as_of) "
            "RETURN startNode(r).key AS source, endNode(r).key AS target, r.type AS type, "
            "r.doc_id AS doc_id, r.clause_id AS clause_id, coalesce(r.verified,false) AS verified, "
            "coalesce(r.evidence,'') AS evidence, props.valid_from AS valid_from, props.valid_until AS valid_until "
            "ORDER BY source,target,type,doc_id,clause_id LIMIT $limit",
            key=key, types=sorted(TRAVERSABLE_RELATIONSHIPS), as_of=as_of, limit=limit + 1))
        if len(records) > limit:
            raise SearchLimitError("neighbor_limit")
        return [Edge(**dict(r)) for r in records]


@lru_cache(maxsize=1)
def get_graph():
    return LexGraph()


def close_graph():
    if get_graph.cache_info().currsize:
        get_graph().close()
        get_graph.cache_clear()
