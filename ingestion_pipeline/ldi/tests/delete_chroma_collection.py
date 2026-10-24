"""
Utility script to delete the ChromaDB 'clauses' collection for test/dev purposes.
"""
from __future__ import annotations

import os

import chromadb
from chromadb.config import Settings

try:
    from chromadb.errors import NotFoundError
except Exception:  # pragma: no cover
    NotFoundError = Exception  # type: ignore


def _resolve_persist_directory(persist_directory: str) -> str:
    if os.path.isabs(persist_directory):
        return persist_directory
    # Interpret relative paths from this file's location, not the current working directory.
    base_dir = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(base_dir, persist_directory))


def delete_chroma_collection(
    persist_directory: str = "../../chroma",
    collection_name: str = "clauses",
) -> None:
    persist_directory = _resolve_persist_directory(persist_directory)
    client = chromadb.PersistentClient(
        path=persist_directory,
        settings=Settings(allow_reset=True),
    )
    try:
        client.delete_collection(collection_name)
        print(f"Deleted collection '{collection_name}' from {persist_directory}")
    except NotFoundError:
        print(f"Collection '{collection_name}' does not exist in {persist_directory} (nothing to delete)")

if __name__ == "__main__":
    delete_chroma_collection()
