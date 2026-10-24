"""
ClauseVectorStore: Handles persistent storage and retrieval of clause embeddings using ChromaDB.
"""
from typing import List, Dict, Any
import json
import os
from pathlib import Path
import numpy as np
import chromadb
from chromadb.config import Settings

class ClauseVectorStore:
    """
    Stores and retrieves clause embeddings and metadata in a persistent ChromaDB collection.
    """
    def __init__(self, persist_directory: str = "./chroma", collection_name: str = "clauses"):
        if not os.path.isabs(persist_directory):
            repository_root = Path(__file__).resolve().parents[2]
            persist_directory = str(repository_root / persist_directory)
        self._client = chromadb.PersistentClient(path=persist_directory, settings=Settings(allow_reset=True))
        self._collection = self._client.get_or_create_collection(collection_name)
        self._document_cache_path = os.path.join(persist_directory, "document_hash_cache.json")
        self._document_cache = self._load_document_cache()

    def _load_document_cache(self) -> Dict[str, Any]:
        if not os.path.exists(self._document_cache_path):
            return {"known_hashes": [], "file_name_to_hash": {}}
        try:
            with open(self._document_cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {"known_hashes": [], "file_name_to_hash": {}}
        if not isinstance(data, dict):
            return {"known_hashes": [], "file_name_to_hash": {}}
        return {
            "known_hashes": list(data.get("known_hashes", [])),
            "file_name_to_hash": dict(data.get("file_name_to_hash", {})),
        }

    def _save_document_cache(self) -> None:
        temp_path = f"{self._document_cache_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self._document_cache, f, indent=2)
        os.replace(temp_path, self._document_cache_path)

    def is_document_indexed(self, document_hash: str) -> bool:
        return document_hash in self._document_cache.get("known_hashes", [])

    def register_document(self, document_hash: str, file_name: str) -> None:
        if document_hash not in self._document_cache["known_hashes"]:
            self._document_cache["known_hashes"].append(document_hash)
        self._document_cache["file_name_to_hash"][file_name] = document_hash
        self._save_document_cache()

    def get_document_clauses(self, file_name: str) -> List[Dict[str, Any]]:
        """
        Retrieve all stored clause chunks for a document identified by file name.

        The preferred lookup path is the cached document hash, with a fallback to
        direct file_name metadata matching for older or partially cached indexes.
        """
        if not file_name:
            return []

        self._document_cache = self._load_document_cache()
        clauses: List[Dict[str, Any]] = []
        seen_ids = set()
        file_hash = self._document_cache.get("file_name_to_hash", {}).get(file_name)
        lookups = []
        if file_hash:
            lookups.append({"where": {"document_hash": file_hash}})
        lookups.append({"where": {"file_name": file_name}})

        for lookup in lookups:
            try:
                result = self._collection.get(
                    include=["documents", "metadatas"],
                    **lookup,
                )
            except Exception:
                continue

            ids = result.get("ids") or []
            documents = result.get("documents") or []
            metadatas = result.get("metadatas") or []

            for index, vector_id in enumerate(ids):
                if vector_id in seen_ids:
                    continue
                seen_ids.add(vector_id)

                metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
                document_text = documents[index] if index < len(documents) else ""
                clauses.append(
                    {
                        "clause_id": metadata.get("clause_id") or str(vector_id).split("::")[-1],
                        "section": metadata.get("section") or "",
                        "level": metadata.get("level") or "clause",
                        "text": document_text or metadata.get("text") or "",
                        "file_name": metadata.get("file_name") or file_name,
                        "document_hash": metadata.get("document_hash") or file_hash or "",
                    }
                )

        return clauses

    def list_documents(self) -> List[Dict[str, Any]]:
        """Return embedded document filenames and hashes for discovery in the API."""

        self._document_cache = self._load_document_cache()
        documents: List[Dict[str, Any]] = []
        for file_name, document_hash in sorted(self._document_cache.get("file_name_to_hash", {}).items()):
            documents.append({"doc_id": file_name, "document_hash": document_hash})
        return documents

    def add(self, ids: List[str], texts: List[str], embeddings: np.ndarray, metadatas: List[Dict[str, Any]]):
        """
        Add embeddings and metadata to the vector store.
        Args:
            ids (List[str]): Unique IDs for each clause.
            texts (List[str]): Clause texts.
            embeddings (np.ndarray): Embeddings array.
            metadatas (List[Dict[str, Any]]): Metadata dicts for each clause.
        """
        if not ids or len(ids) != len(texts) or len(ids) != len(embeddings) or len(ids) != len(metadatas):
            raise ValueError("Input lists must be non-empty and of equal length.")
        # Use upsert so re-indexing the same IDs updates rows instead of failing.
        self._collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings.tolist(),
            metadatas=metadatas
        )

    def search(self, query_embedding: np.ndarray, k: int = 5):
        """
        Search for the top-k most similar clauses to the query embedding.
        Args:
            query_embedding (np.ndarray): Query embedding vector.
            k (int): Number of results to return.
        Returns:
            List[Dict]: List of matching clause metadata and scores.
        """
        results = self._collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=k
        )
        return results
