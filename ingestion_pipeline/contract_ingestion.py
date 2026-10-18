"""Contract document extraction and clause segmentation."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .document_input import MAX_FILE_BYTES, extract_text
from .ldi.chunking import split_clauses
from .graph_facts import clauses_to_graph_facts


def ingest_contract_bytes(filename: str, content: bytes) -> dict[str, Any]:
    """Extract a contract and persist its clause-scoped facts to the COI graph.

    Ingestion succeeds only after Neo4j accepts the graph update. Reingesting
    identical bytes replaces the same source document and its prior evidence.
    """
    plaintext = extract_text(filename, content)
    clauses = split_clauses(plaintext)
    if not clauses:
        clauses = [{
            "clause_id": "P1",
            "section": "Document",
            "level": "clause",
            "text": plaintext,
        }]

    document = {
        "contract_id": hashlib.sha256(content).hexdigest()[:20],
        "filename": Path(filename).name,
        "file_type": Path(filename).suffix.casefold().lstrip("."),
        "plaintext": plaintext,
        "clauses": clauses,
        "metadata": {
            "file_bytes": len(content),
            "characters": len(plaintext),
            "word_count": len(plaintext.split()),
            "clause_count": len(clauses),
            "table_count": sum(item.get("level") == "table" for item in clauses),
        },
    }
    from agents.coi.graph_manager import get_graph

    facts = clauses_to_graph_facts(clauses)
    graph = get_graph()
    graph.setup_schema()
    update = graph.replace_document(
        {"id": document["contract_id"], "filename": document["filename"],
         "type": document["file_type"]}, facts,
    )
    document["metadata"]["graph_update"] = {
        "status": update["status"],
        "entities": len({entity["name"].casefold() for clause in facts for entity in clause["entities"]}),
        "relationships": sum(len(clause["relationships"]) for clause in facts),
        "clauses": update["clauses"],
    }
    return document


def ingest_contract_file(file_path: str | Path) -> dict[str, Any]:
    """Read and ingest a local TXT, PDF, or DOCX contract within upload limits."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Contract file not found: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File must be at most {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    return ingest_contract_bytes(path.name, path.read_bytes())
