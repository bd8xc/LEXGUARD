from typing import Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer

from rag.knowledge_loader import LegalKnowledgeLoader


class LegalEmbeddingModel:
    """
    Creates semantic embeddings for legal knowledge-base
    principles and contract clauses.

    The embedding text intentionally combines:
        - topic
        - subtopic
        - principle
        - risk factors
        - mitigating factors

    Source metadata is retained separately and is not relied
    upon as the main semantic content.
    """

    def __init__(
        self,
        model_name="sentence-transformers/all-MiniLM-L6-v2",
    ):

        self.model_name = model_name

        print(
            f"Loading embedding model: "
            f"{self.model_name}"
        )

        self.model = SentenceTransformer(
            self.model_name
        )

        print(
            "Embedding model loaded successfully."
        )

    ##########################################################
    # BUILD SEARCHABLE TEXT
    ##########################################################

    def build_principle_text(
        self,
        principle: Dict,
    ) -> str:

        risk_factors = " ".join(
            principle.get(
                "risk_factors",
                [],
            )
        )

        mitigating_factors = " ".join(
            principle.get(
                "mitigating_factors",
                [],
            )
        )

        text = (
            f"Topic: "
            f"{principle['topic']}. "

            f"Subtopic: "
            f"{principle['subtopic']}. "

            f"Legal principle: "
            f"{principle['principle']} "

            f"Risk factors: "
            f"{risk_factors}. "

            f"Mitigating factors: "
            f"{mitigating_factors}."
        )

        return " ".join(
            text.split()
        )

    ##########################################################
    # EMBED ONE QUERY / CLAUSE
    ##########################################################

    def embed_query(
        self,
        text: str,
    ) -> np.ndarray:

        if not isinstance(
            text,
            str,
        ):

            raise TypeError(
                "Query must be a string."
            )

        text = text.strip()

        if not text:

            raise ValueError(
                "Query cannot be empty."
            )

        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        return embedding.astype(
            np.float32
        )

    ##########################################################
    # EMBED ALL PRINCIPLES
    ##########################################################

    def embed_principles(
        self,
        principles: List[Dict],
    ) -> np.ndarray:

        if not principles:

            return np.empty(
                (
                    0,
                    self.model.get_sentence_embedding_dimension(),
                ),
                dtype=np.float32,
            )

        texts = [

            self.build_principle_text(
                principle
            )

            for principle in principles
        ]

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True,
        )

        return embeddings.astype(
            np.float32
        )


##############################################################
# TEST
##############################################################

if __name__ == "__main__":

    loader = LegalKnowledgeLoader()

    principles = (
        loader.load_principles()
    )

    embedding_model = (
        LegalEmbeddingModel()
    )

    embeddings = (
        embedding_model.embed_principles(
            principles
        )
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "LEGAL EMBEDDING TEST"
    )

    print(
        "=" * 70
    )

    print(
        f"\nPrinciples : "
        f"{len(principles)}"
    )

    print(
        f"Shape      : "
        f"{embeddings.shape}"
    )

    if len(principles) > 0:

        print(
            f"Dimension  : "
            f"{embeddings.shape[1]}"
        )

        print(
            "\nFirst principle:"
        )

        print(
            principles[0][
                "id"
            ]
        )

        print(
            "\nSearchable representation:"
        )

        print(
            embedding_model.build_principle_text(
                principles[0]
            )
        )

    print(
        "\nEmbeddings generated successfully."
    )