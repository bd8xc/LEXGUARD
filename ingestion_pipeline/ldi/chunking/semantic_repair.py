from __future__ import annotations

from functools import lru_cache
from typing import List

import numpy as np
import re

# Used for semantic similarity to merge broken lines (PDF artifacts)
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore


@lru_cache(maxsize=1)
def _get_cleanup_embedder():
    if SentenceTransformer is None:
        return None
    return SentenceTransformer("all-MiniLM-L6-v2")


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """
    Calculates cosine similarity between two vectors.
    Range: -1 (opposite) to 1 (identical).
    """
    #
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def semantic_cleanup(text: str, threshold: float = 0.7) -> str:
    """
    Merges lines within a clause if they are semantically continuous.

    HOW:
    - If Line A and Line B have similarity > 0.8, we assume Line B
      is a continuation of Line A (broken by PDF formatting).
    - If similarity is lower, Line B is likely a new thought/bullet.
    """
    # Normalize PDF/contract placeholders that can create artificial sentence breaks
    # in downstream scoring (e.g., "_____. 2024" or long ellipsis runs).
    cleaned = str(text)
    cleaned = re.sub(r"(_{2,})\.(\s+)", r"\1\2", cleaned)  # _____ . 2024 -> _____ 2024
    cleaned = re.sub(r"[…]+", " ", cleaned)  # unicode ellipsis
    cleaned = re.sub(r"\.{2,}", " ", cleaned)  # .........
    cleaned = re.sub(r"\b(dt|no)\.", r"\1", cleaned, flags=re.IGNORECASE)  # dt. / No.

    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
    if len(lines) <= 1:
        return cleaned.strip()

    embedder = _get_cleanup_embedder()
    if embedder is None:
        # Fallback: keep structure but lightly repair obvious broken lines.
        merged: List[str] = [lines[0]]
        for i in range(1, len(lines)):
            prev = merged[-1]
            curr = lines[i]
            if prev and curr and (prev[-1].isalnum() and curr[:1].islower()):
                merged[-1] = prev + " " + curr
            else:
                merged.append(curr)
        return "\n".join(merged).strip()

    emb = embedder.encode(lines)
    merged = [lines[0]]

    for i in range(1, len(lines)):
        if cosine(emb[i - 1], emb[i]) > threshold:
            merged[-1] += " " + lines[i]
        else:
            merged.append(lines[i])

    return "\n".join(merged)
