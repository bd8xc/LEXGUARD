from typing import Dict, List

from sentence_transformers import CrossEncoder


class LegalPrincipleReranker:
    """
    Reranks legal-principle candidates by evaluating
    the contract clause and each candidate principle
    together.

    IMPORTANT:
    This component does NOT predict legal risk.

    Its only purpose is relevance ranking:

        Clause
            +
        Candidate legal principle
            ↓
        Relevance score
    """

    def __init__(
        self,
        model_name="cross-encoder/ms-marco-MiniLM-L6-v2",
    ):

        self.model_name = model_name

        print(
            f"Loading reranker model: "
            f"{self.model_name}"
        )

        self.model = CrossEncoder(
            self.model_name
        )

        print(
            "Reranker model loaded successfully."
        )

    ##########################################################
    # BUILD CANDIDATE TEXT
    ##########################################################

    def build_candidate_text(
        self,
        candidate: Dict,
    ) -> str:
        """
        Builds the text presented to the cross-encoder.

        We intentionally focus on semantic legal content
        rather than source metadata such as jurisdiction
        or source title.
        """

        risk_factors = " ".join(
            candidate.get(
                "risk_factors",
                [],
            )
        )

        mitigating_factors = " ".join(
            candidate.get(
                "mitigating_factors",
                [],
            )
        )

        text = (
            f"Topic: "
            f"{candidate.get('topic', '')}. "

            f"Subtopic: "
            f"{candidate.get('subtopic', '')}. "

            f"Principle: "
            f"{candidate.get('principle', '')} "

            f"Risk factors: "
            f"{risk_factors}. "

            f"Mitigating factors: "
            f"{mitigating_factors}."
        )

        return " ".join(
            text.split()
        )

    ##########################################################
    # RERANK
    ##########################################################

    def rerank(
        self,
        query: str,
        candidates: List[Dict],
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

        if not candidates:

            return []

        if top_k <= 0:

            raise ValueError(
                "top_k must be greater than 0."
            )

        ######################################################
        # BUILD QUERY-CANDIDATE PAIRS
        ######################################################

        pairs = []

        for candidate in candidates:

            candidate_text = (
                self.build_candidate_text(
                    candidate
                )
            )

            pairs.append(
                (
                    query,
                    candidate_text,
                )
            )

        ######################################################
        # CROSS-ENCODER SCORING
        ######################################################

        scores = self.model.predict(
            pairs
        )

        ######################################################
        # COPY RESULTS + ADD RERANK SCORE
        ######################################################

        reranked = []

        for candidate, score in zip(
            candidates,
            scores,
        ):

            item = candidate.copy()

            # Preserve original bi-encoder rank/score
            item[
                "retrieval_rank"
            ] = candidate.get(
                "rank"
            )

            item[
                "retrieval_score"
            ] = candidate.get(
                "score"
            )

            # Cross-encoder relevance score
            item[
                "rerank_score"
            ] = float(
                score
            )

            reranked.append(
                item
            )

        ######################################################
        # SORT BY RERANKER SCORE
        ######################################################

        reranked.sort(
            key=lambda item:
                item["rerank_score"],
            reverse=True,
        )

        ######################################################
        # ASSIGN FINAL RANK
        ######################################################

        final_results = []

        for index, item in enumerate(
            reranked[:top_k],
            start=1,
        ):

            item[
                "rank"
            ] = index

            final_results.append(
                item
            )

        return final_results


##############################################################
# SIMPLE TEST
##############################################################

if __name__ == "__main__":

    reranker = LegalPrincipleReranker()

    query = (
        "Either party may end this arrangement "
        "following a material default by the other "
        "party, provided that the defaulting party "
        "is first given thirty days to remedy the "
        "failure."
    )

    candidates = [

        {
            "rank": 1,
            "score": 0.3351,
            "id": "TERM_002",
            "topic": "Termination and Remedies",
            "subtopic": "Time-Critical Performance",
            "principle": (
                "Failure to perform an obligation at "
                "a fixed time may affect whether the "
                "contract is voidable."
            ),
            "risk_factors": [
                "strict performance deadlines",
            ],
            "mitigating_factors": [
                "clear identification of "
                "time-critical obligations",
            ],
        },

        {
            "rank": 2,
            "score": 0.3232,
            "id": "TERM_003",
            "topic": "Termination and Remedies",
            "subtopic": (
                "Termination Escalation "
                "and Rectification"
            ),
            "principle": (
                "Performance-related termination "
                "mechanisms should generally use "
                "proportionate escalation and allow "
                "an opportunity to rectify performance "
                "problems."
            ),
            "risk_factors": [
                "no opportunity to rectify "
                "remediable performance problems",
            ],
            "mitigating_factors": [
                "defined rectification process",
                "reasonable opportunity to cure",
            ],
        },

    ]

    results = reranker.rerank(
        query=query,
        candidates=candidates,
        top_k=2,
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "LEGAL PRINCIPLE RERANKER TEST"
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
            f"Final rank     : "
            f"{result['rank']}"
        )

        print(
            f"ID             : "
            f"{result['id']}"
        )

        print(
            f"Original rank  : "
            f"{result['retrieval_rank']}"
        )

        print(
            f"Retrieval score: "
            f"{result['retrieval_score']:.4f}"
        )

        print(
            f"Reranker score : "
            f"{result['rerank_score']:.4f}"
        )