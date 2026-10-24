"""
ClauseEmbedder: Generates embeddings for legal clauses using SentenceTransformers.
"""
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer

class ClauseEmbedder:
    """
    Embeds legal clause texts using a pre-trained SentenceTransformer model.
    Loads the model once per instance.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for a list of texts.
        Args:
            texts (List[str]): List of clause texts.
        Returns:
            np.ndarray: Embeddings array of shape (len(texts), embedding_dim)
        """
        if not texts:
            return np.empty((0, self._model.get_sentence_embedding_dimension()))
        return np.asarray(self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True))
