import json
from pathlib import Path
from typing import Dict, List


class LegalKnowledgeLoader:
    """
    Loads and validates the structured legal-principle
    knowledge base used by the Legal RAG pipeline.
    """

    REQUIRED_FIELDS = {
        "id",
        "topic",
        "subtopic",
        "jurisdiction",
        "authority_type",
        "principle",
        "risk_factors",
        "mitigating_factors",
        "source_title",
        "source_section",
        "source_reference",
        "analysis_note",
    }

    def __init__(
        self,
        knowledge_path=(
            "knowledge_base/legal_principles.json"
        ),
    ):

        self.knowledge_path = Path(
            knowledge_path
        )

    def load(self) -> Dict:

        if not self.knowledge_path.exists():

            raise FileNotFoundError(
                f"Knowledge base not found: "
                f"{self.knowledge_path}"
            )

        with open(
            self.knowledge_path,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        self._validate_root(
            data
        )

        principles = data[
            "principles"
        ]

        for index, principle in enumerate(
            principles
        ):

            self._validate_principle(
                principle,
                index,
            )

        return data

    def load_principles(
        self,
    ) -> List[Dict]:

        data = self.load()

        return data[
            "principles"
        ]

    def _validate_root(
        self,
        data,
    ):

        if not isinstance(
            data,
            dict,
        ):

            raise ValueError(
                "Knowledge base root must "
                "be a JSON object."
            )

        if "metadata" not in data:

            raise ValueError(
                "Missing 'metadata' section."
            )

        if "principles" not in data:

            raise ValueError(
                "Missing 'principles' list."
            )

        if not isinstance(
            data["principles"],
            list,
        ):

            raise ValueError(
                "'principles' must be a list."
            )

    def _validate_principle(
        self,
        principle,
        index,
    ):

        if not isinstance(
            principle,
            dict,
        ):

            raise ValueError(
                f"Principle {index} "
                "must be an object."
            )

        missing = (
            self.REQUIRED_FIELDS
            - set(
                principle.keys()
            )
        )

        if missing:

            raise ValueError(
                f"Principle {index} missing "
                f"fields: {sorted(missing)}"
            )

        if not isinstance(
            principle["risk_factors"],
            list,
        ):

            raise ValueError(
                f"Principle {index}: "
                "'risk_factors' must be a list."
            )

        if not isinstance(
            principle["mitigating_factors"],
            list,
        ):

            raise ValueError(
                f"Principle {index}: "
                "'mitigating_factors' must "
                "be a list."
            )


if __name__ == "__main__":

    loader = LegalKnowledgeLoader()

    data = loader.load()

    print(
        "=" * 70
    )

    print(
        "LEGAL KNOWLEDGE BASE"
    )

    print(
        "=" * 70
    )

    print(
        f"\nName       : "
        f"{data['metadata']['name']}"
    )

    print(
        f"Version    : "
        f"{data['metadata']['version']}"
    )

    print(
        f"Principles : "
        f"{len(data['principles'])}"
    )

    print(
        "\nKnowledge base loaded "
        "and validated successfully."
    )