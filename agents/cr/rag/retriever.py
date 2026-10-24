from typing import Dict, List

import numpy as np

from rag.knowledge_loader import LegalKnowledgeLoader
from rag.embeddings import LegalEmbeddingModel
from rag.reranker import LegalPrincipleReranker


class LegalPrincipleRetriever:
    """
    Semantic retriever for the Legal Risk Knowledge Base.

    Current prototype:
        Clause/query
            ↓
        Query embedding
            ↓
        Cosine similarity against principle embeddings
            ↓
        Top-K relevant legal principles

    Because embeddings are normalized, dot product is
    equivalent to cosine similarity.

    This prototype intentionally performs in-memory search.
    FAISS will be introduced after retrieval quality has
    been validated on the small corpus.
    """
    def __init__(
        self,
        knowledge_path="knowledge_base/legal_principles.json",
        embedding_model_name=(
            "sentence-transformers/all-MiniLM-L6-v2"
        ),
    ):

        ######################################################
        # LOAD KNOWLEDGE BASE
        ######################################################

        self.loader = LegalKnowledgeLoader(
            knowledge_path=knowledge_path
        )

        self.principles = (
            self.loader.load_principles()
        )

        if not self.principles:

            raise ValueError(
                "Knowledge base contains no principles."
            )

        ######################################################
        # LOAD EMBEDDING MODEL
        ######################################################

        self.embedding_model = LegalEmbeddingModel(
            model_name=embedding_model_name
        )

        ######################################################
        # EMBED KNOWLEDGE BASE
        ######################################################

        print(
            f"Embedding {len(self.principles)} "
            f"legal principles..."
        )

        self.principle_embeddings = (
            self.embedding_model.embed_principles(
                self.principles
            )
        )

        # self.reranker = LegalPrincipleReranker()

        # print(
        #     "Legal principle reranker ready."
        # )

    ##########################################################
    # RETRIEVE
    ##########################################################

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.0,
    ) -> List[Dict]:

        if not isinstance(
            query,
            str,
        ):

            raise TypeError(
                "Query must be a string."
            )

        query = query.strip()

        if not query:

            raise ValueError(
                "Query cannot be empty."
            )

        if top_k <= 0:

            raise ValueError(
                "top_k must be greater than 0."
            )

        ######################################################
        # QUERY EMBEDDING
        ######################################################

        query_embedding = (
            self.embedding_model.embed_query(
                query
            )
        )

        ######################################################
        # COSINE SIMILARITY
        #
        # Both query and principle embeddings were normalized,
        # therefore dot product = cosine similarity.
        ######################################################

        scores = np.dot(
            self.principle_embeddings,
            query_embedding,
        )

        ######################################################
        # SORT HIGHEST → LOWEST
        ######################################################

        ranked_indices = np.argsort(
            scores
        )[::-1]

        ######################################################
        # BUILD RESULTS
        ######################################################

        results = []

        for index in ranked_indices:

            score = float(
                scores[index]
            )

            if score < min_score:
                continue

            principle = self.principles[
                int(index)
            ]

            result = {

                "rank":
                    len(results) + 1,

                "score":
                    score,

                "id":
                    principle["id"],

                "topic":
                    principle["topic"],

                "subtopic":
                    principle["subtopic"],

                "principle":
                    principle["principle"],

                "risk_factors":
                    principle["risk_factors"],

                "mitigating_factors":
                    principle[
                        "mitigating_factors"
                    ],

                "jurisdiction":
                    principle["jurisdiction"],

                "authority_type":
                    principle["authority_type"],

                "source_title":
                    principle["source_title"],

                "source_section":
                    principle["source_section"],

                "source_reference":
                    principle["source_reference"],

                "analysis_note":
                    principle["analysis_note"],
            }

            results.append(
                result
            )

            if len(results) >= top_k:
                break

        return results
    
    def retrieve_and_rerank(
    self,
    query: str,
    candidate_k: int = 8,
    final_k: int = 3,
    ):

        candidates = self.retrieve(
            query=query,
            top_k=min(
                candidate_k,
                len(self.principles),
            ),
        )

        return self.reranker.rerank(
            query=query,
            candidates=candidates,
            top_k=min(
                final_k,
                len(candidates),
            ),
        )

##############################################################
# INTERACTIVE RETRIEVAL TEST
##############################################################

if __name__ == "__main__":

    retriever = LegalPrincipleRetriever()

    print(
        "\n"
        + "=" * 70
    )

    print(
        "LEGAL PRINCIPLE SEMANTIC RETRIEVER"
    )

    print(
        "=" * 70
    )

    print(
        "\nEnter a contract clause."
    )

    print(
        "Type 'quit' to exit."
    )

    while True:

        query = input(
            "\nClause: "
        ).strip()

        if query.lower() in {
            "quit",
            "exit",
            "q",
        }:

            print(
                "\nExiting."
            )

            break

        if not query:

            print(
                "Please enter a clause."
            )

            continue

        try:

            results = retriever.retrieve_and_rerank(
                        query=query,
                        candidate_k=8,
                    )

            print(
                "\n"
                + "=" * 70
            )

            print(
                "RETRIEVED LEGAL PRINCIPLES"
            )

            print(
                "=" * 70
            )

            for result in results:

                print(
                    "\n"
                    + "-" * 70
                )

                print(
                    f"Original rank : "
                    f"{result['retrieval_rank']}"
                )

                print(
                    f"Bi-encoder    : "
                    f"{result['retrieval_score']:.4f}"
                )

                print(
                    f"Reranker      : "
                    f"{result['rerank_score']:.4f}"
                )

                print(
                    f"Similarity   : "
                    f"{result['score']:.4f}"
                )

                print(
                    f"ID           : "
                    f"{result['id']}"
                )

                print(
                    f"Topic        : "
                    f"{result['topic']}"
                )

                print(
                    f"Subtopic     : "
                    f"{result['subtopic']}"
                )

                print(
                    f"Jurisdiction : "
                    f"{result['jurisdiction']}"
                )

                print(
                    f"Authority    : "
                    f"{result['authority_type']}"
                )

                print(
                    "\nPrinciple:"
                )

                print(
                    result[
                        "principle"
                    ]
                )

                print(
                    "\nSource:"
                )

                print(
                    result[
                        "source_title"
                    ]
                )

                print(
                    result[
                        "source_section"
                    ]
                )

                print(
                    result[
                        "source_reference"
                    ]
                )

            print(
                "\n"
                + "=" * 70
            )

        except Exception as error:

            print(
                f"\nRetrieval failed: "
                f"{error}"
            )