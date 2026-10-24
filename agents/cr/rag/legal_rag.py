import json
import os
from typing import Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer


class IndianLegalRAG:
    """
    Retrieval system over extracted provisions of
    The Indian Contract Act, 1872.

    Pipeline:

        Extracted statutory sections
                ↓
        Build searchable representations
                ↓
        SentenceTransformer embeddings
                ↓
        Clause/query embedding
                ↓
        Cosine similarity
                ↓
        Top-K relevant Indian legal provisions
    """

    DEFAULT_SOURCE_PATH = (
        "knowledge_base/"
        "processed/"
        "indian_contract_act_sections.json"
    )

    DEFAULT_MODEL = (
        "sentence-transformers/"
        "all-MiniLM-L6-v2"
    )

    def __init__(
        self,
        source_path=None,
        model_name=None,
    ):

        if source_path is None:
            source_path = (
                self.DEFAULT_SOURCE_PATH
            )

        if model_name is None:
            model_name = (
                self.DEFAULT_MODEL
            )

        self.source_path = source_path
        self.model_name = model_name

        ######################################################
        # LOAD CORPUS
        ######################################################

        self.sections = (
            self._load_sections()
        )

        print(
            f"Loaded "
            f"{len(self.sections)} "
            f"legal sections."
        )

        ######################################################
        # LOAD EMBEDDING MODEL
        ######################################################

        print(
            f"Loading embedding model: "
            f"{self.model_name}"
        )

        self.model = (
            SentenceTransformer(
                self.model_name
            )
        )

        print(
            "Embedding model loaded."
        )

        ######################################################
        # BUILD SEARCHABLE TEXT
        ######################################################

        self.search_documents = [

            self._build_search_text(
                section
            )

            for section
            in self.sections
        ]

        ######################################################
        # EMBED CORPUS
        ######################################################

        print(
            "Embedding Indian legal corpus..."
        )

        self.embeddings = (
            self.model.encode(
                self.search_documents,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=True,
            )
        )

        print(
            "Legal corpus ready."
        )

    ##########################################################
    # LOAD SECTIONS
    ##########################################################

    def _load_sections(
        self,
    ) -> List[Dict]:

        if not os.path.exists(
            self.source_path
        ):

            raise FileNotFoundError(
                f"Legal corpus not found: "
                f"{self.source_path}"
            )

        with open(
            self.source_path,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        ######################################################
        # SUPPORT CURRENT EXTRACTOR FORMAT
        ######################################################

        sections = data.get(
            "sections"
        )

        if sections is None:

            # Compatibility with older structure.

            sections = data.get(
                "provisions"
            )

        if not sections:

            raise ValueError(
                "No legal sections found "
                "in extracted corpus."
            )

        return sections

    ##########################################################
    # BUILD SEARCHABLE REPRESENTATION
    ##########################################################

    @staticmethod
    def _build_search_text(
        section: Dict,
    ) -> str:

        section_number = str(
            section.get(
                "section",
                "",
            )
        )

        heading = section.get(
            "heading",
            "",
        )

        text = section.get(
            "text",
            "",
        )

        return (
            f"Indian Contract Act, 1872. "
            f"Section {section_number}. "
            f"Topic: {heading}. "
            f"Legal provision: {text}"
        )

    ##########################################################
    # RETRIEVE
    ##########################################################

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
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

        query_embedding = (
            self.model.encode(
                query,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        )

        ######################################################
        # NORMALIZED EMBEDDINGS:
        #
        # dot product == cosine similarity
        ######################################################

        scores = np.dot(
            self.embeddings,
            query_embedding,
        )

        ranked_indices = (
            np.argsort(
                scores
            )[::-1]
        )

        results = []

        for rank, index in enumerate(
            ranked_indices[
                :top_k
            ],
            start=1,
        ):

            section = (
                self.sections[
                    int(index)
                ]
            )

            results.append(
                {
                    "rank":
                        rank,

                    "score":
                        float(
                            scores[
                                index
                            ]
                        ),

                    "section":
                        section.get(
                            "section"
                        ),

                    "heading":
                        section.get(
                            "heading"
                        ),

                    "text":
                        section.get(
                            "text"
                        ),

                    "source":
                        (
                            "The Indian "
                            "Contract Act, 1872"
                        ),
                }
            )

        return results


##############################################################
# COMMAND-LINE DEMO
##############################################################

if __name__ == "__main__":

    rag = IndianLegalRAG()

    print(
        "\n"
        + "=" * 70
    )

    print(
        "INDIAN CONTRACT LAW RAG"
    )

    print(
        "=" * 70
    )

    while True:

        print(
            "\nPaste a contract clause."
        )

        print(
            "Type 'quit' to exit.\n"
        )

        clause = input(
            "Clause: "
        ).strip()

        if clause.lower() in {
            "quit",
            "exit",
            "q",
        }:

            break

        if not clause:

            continue

        results = rag.retrieve(
            query=clause,
            top_k=3,
        )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "RETRIEVED INDIAN LAW"
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
                f"Rank       : "
                f"{result['rank']}"
            )

            print(
                f"Similarity : "
                f"{result['score']:.4f}"
            )

            print(
                f"Section    : "
                f"{result['section']}"
            )

            print(
                f"Heading    : "
                f"{result['heading']}"
            )

            print(
                f"Source     : "
                f"{result['source']}"
            )

            print(
                "\nProvision:"
            )

            text = (
                result[
                    "text"
                ]
            )

            print(
                text[:1200]
            )

        print(
            "\n"
            + "=" * 70
        )