"""
Embedding pipeline for legal clause chunks.
"""
from typing import List, Dict, Any
import hashlib
from .embedder import ClauseEmbedder
from .vector_store import ClauseVectorStore


def _compute_document_hash(clauses: List[Dict[str, Any]]) -> str:
    hasher = hashlib.sha256()
    for clause in clauses:
        clause_id = str(clause.get("clause_id", "") or "").strip()
        section = str(clause.get("section", "") or "").strip()
        level = str(clause.get("level", "") or "").strip()
        text = str(clause.get("text", "") or "").strip()
        hasher.update(clause_id.encode("utf-8"))
        hasher.update(b"\x1f")
        hasher.update(section.encode("utf-8"))
        hasher.update(b"\x1f")
        hasher.update(level.encode("utf-8"))
        hasher.update(b"\x1f")
        hasher.update(text.encode("utf-8"))
        hasher.update(b"\x1e")
    return hasher.hexdigest()


def embed_and_store(clauses: List[Dict[str, Any]], file_name: str) -> Dict[str, Any]:
    """
    Embeds clauses and stores them in the vector store with metadata.
    Args:
        clauses (List[Dict]): List of clause dicts.
        file_name (str): Name of the source file.
    Returns:
        Dict: Stats about the embedding process.
    """
    if not clauses:
        return {"clauses": 0, "embedding_dim": 0}

    document_hash = _compute_document_hash(clauses)
    vector_store = ClauseVectorStore()
    if vector_store.is_document_indexed(document_hash):
        vector_store.register_document(document_hash, file_name)
        return {"clauses": 0, "embedding_dim": 0, "cached": True, "document_hash": document_hash}

    texts: List[str] = []
    ids: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    seen_ids = {}

    for idx, clause in enumerate(clauses):
        text = str(clause.get("text", "")).strip()
        if not text:
            continue

        clause_id = str(clause.get("clause_id") or f"IDX{idx}")
        base_vector_id = f"{file_name}::{clause_id}"
        vector_id = base_vector_id
        # Ensure uniqueness by appending a suffix if needed
        if vector_id in seen_ids:
            seen_ids[vector_id] += 1
            vector_id = f"{base_vector_id}__{seen_ids[vector_id]}"
        else:
            seen_ids[vector_id] = 0

        texts.append(text)
        ids.append(vector_id)

        metadata: Dict[str, Any] = {
            "clause_id": clause_id,
            "section": clause.get("section"),
            "level": clause.get("level"),
            "file_name": file_name,
            "text": text,
            "document_hash": document_hash,
        }
        for extra_key in ("type", "term", "table_context"):
            if extra_key in clause:
                metadata[extra_key] = clause.get(extra_key)
        metadatas.append(metadata)

    if not texts:
        return {"clauses": 0, "embedding_dim": 0}

    embedder = ClauseEmbedder()
    embeddings = embedder.embed(texts)
    vector_store.add(ids, texts, embeddings, metadatas)
    vector_store.register_document(document_hash, file_name)

    return {
        "clauses": len(texts),
        "embedding_dim": embeddings.shape[1] if embeddings.shape else 0,
        "cached": False,
        "document_hash": document_hash,
    }
