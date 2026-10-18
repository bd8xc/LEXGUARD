"""Contract document extraction and clause segmentation."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .document_input import MAX_FILE_BYTES, extract_text
from .ldi.chunking import split_clauses


def ingest_contract_bytes(filename: str, content: bytes) -> dict[str, Any]:
    """Extract contract plaintext and structured clauses from uploaded bytes."""
    plaintext = extract_text(filename, content)
    clauses = split_clauses(plaintext)
    if not clauses:
        clauses = [{
            "clause_id": "P1",
            "section": "Document",
            "level": "clause",
            "text": plaintext,
        }]

    return {
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


def ingest_contract_file(file_path: str | Path) -> dict[str, Any]:
    """Read and ingest a local TXT, PDF, or DOCX contract within upload limits."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Contract file not found: {path}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File must be at most {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    return ingest_contract_bytes(path.name, path.read_bytes())
