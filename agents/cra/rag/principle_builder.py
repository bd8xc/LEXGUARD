import json
import os
from datetime import datetime, timezone
from typing import Dict, List

from rag.source_ingestion import IndianLegalSourceIngester


class LegalPrincipleBuilder:
    """
    Builds retrieval-ready legal principle records from
    structured Indian legal source records.

    Architecture:

        Raw legal source
                ↓
        Source ingestion
                ↓
        Source record
                ↓
        Derived legal principle
                ↓
        Review / validation
                ↓
        Retrieval-ready knowledge record

    IMPORTANT:

    This class does NOT automatically generate legal
    interpretations.

    A derived principle must be explicitly supplied and
    remains in 'pending' review status until validated.
    """

    VALID_REVIEW_STATUSES = {
        "pending",
        "approved",
        "rejected",
    }

    REQUIRED_DERIVATION_FIELDS = [
        "topic",
        "subtopic",
        "principle",
        "risk_factors",
        "mitigating_factors",
        "analysis_note",
    ]

    def __init__(
        self,
        source_path: str,
    ):

        self.source_path = source_path

        ######################################################
        # LOAD SOURCE RECORDS
        ######################################################

        self.ingester = IndianLegalSourceIngester(
            source_path=self.source_path
        )

        self.source_records = (
            self.ingester.ingest()
        )

        ######################################################
        # INDEX SOURCES BY ID
        ######################################################

        self.source_index = {

            record["id"]: record

            for record in self.source_records
        }

    ##########################################################
    # GET SOURCE
    ##########################################################

    def get_source(
        self,
        source_id: str,
    ) -> Dict:

        if source_id not in self.source_index:

            raise KeyError(
                f"Unknown source ID: "
                f"{source_id}"
            )

        return self.source_index[
            source_id
        ]

    ##########################################################
    # VALIDATE DERIVATION
    ##########################################################

    def validate_derivation(
        self,
        derivation: Dict,
    ):

        for field in (
            self.REQUIRED_DERIVATION_FIELDS
        ):

            if field not in derivation:

                raise ValueError(
                    f"Missing derivation field: "
                    f"{field}"
                )

        ######################################################
        # STRING FIELDS
        ######################################################

        string_fields = [
            "topic",
            "subtopic",
            "principle",
            "analysis_note",
        ]

        for field in string_fields:

            value = derivation[
                field
            ]

            if (
                not isinstance(
                    value,
                    str,
                )
                or not value.strip()
            ):

                raise ValueError(
                    f"'{field}' must be a "
                    f"non-empty string."
                )

        ######################################################
        # LIST FIELDS
        ######################################################

        list_fields = [
            "risk_factors",
            "mitigating_factors",
        ]

        for field in list_fields:

            value = derivation[
                field
            ]

            if not isinstance(
                value,
                list,
            ):

                raise TypeError(
                    f"'{field}' must be a list."
                )

            for item in value:

                if (
                    not isinstance(
                        item,
                        str,
                    )
                    or not item.strip()
                ):

                    raise ValueError(
                        f"All items in '{field}' "
                        f"must be non-empty strings."
                    )

    ##########################################################
    # BUILD PRINCIPLE ID
    ##########################################################

    @staticmethod
    def build_principle_id(
        source_id: str,
        sequence: int = 1,
    ) -> str:

        if sequence <= 0:

            raise ValueError(
                "sequence must be greater than 0."
            )

        return (
            f"{source_id}_P"
            f"{sequence:02d}"
        )

    ##########################################################
    # BUILD PRINCIPLE
    ##########################################################

    def build_principle(
        self,
        source_id: str,
        derivation: Dict,
        sequence: int = 1,
        review_status: str = "pending",
    ) -> Dict:

        ######################################################
        # SOURCE VALIDATION
        ######################################################

        source = self.get_source(
            source_id
        )

        ######################################################
        # DERIVATION VALIDATION
        ######################################################

        self.validate_derivation(
            derivation
        )

        ######################################################
        # REVIEW STATUS
        ######################################################

        review_status = (
            review_status
            .strip()
            .lower()
        )

        if (
            review_status
            not in self.VALID_REVIEW_STATUSES
        ):

            raise ValueError(
                f"Invalid review status: "
                f"{review_status}"
            )

        ######################################################
        # PRINCIPLE ID
        ######################################################

        principle_id = (
            self.build_principle_id(
                source_id=source_id,
                sequence=sequence,
            )
        )

        ######################################################
        # TIMESTAMP
        ######################################################

        created_at = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

        ######################################################
        # BUILD RECORD
        ######################################################

        principle = {

            "id":
                principle_id,

            "source_id":
                source["id"],

            ##################################################
            # DERIVED LEGAL KNOWLEDGE
            ##################################################

            "topic":
                derivation[
                    "topic"
                ].strip(),

            "subtopic":
                derivation[
                    "subtopic"
                ].strip(),

            "principle":
                derivation[
                    "principle"
                ].strip(),

            "risk_factors": [

                item.strip()

                for item in derivation[
                    "risk_factors"
                ]
            ],

            "mitigating_factors": [

                item.strip()

                for item in derivation[
                    "mitigating_factors"
                ]
            ],

            "analysis_note":
                derivation[
                    "analysis_note"
                ].strip(),

            ##################################################
            # SOURCE PROVENANCE
            ##################################################

            "jurisdiction":
                source[
                    "jurisdiction"
                ],

            "authority_type":
                source[
                    "authority_type"
                ],

            "source_title":
                source[
                    "source_title"
                ],

            "source_name":
                source[
                    "source_name"
                ],

            "act_number":
                source.get(
                    "act_number"
                ),

            "source_section":
                source[
                    "source_section"
                ],

            "section_heading":
                source[
                    "section_heading"
                ],

            "raw_provision":
                source[
                    "raw_provision"
                ],

            "source_verified":
                source[
                    "source_verified"
                ],

            ##################################################
            # REVIEW / GOVERNANCE
            ##################################################

            "review_status":
                review_status,

            "created_at":
                created_at,
        }

        return principle

    ##########################################################
    # BUILD MANY
    ##########################################################

    def build_many(
        self,
        definitions: List[Dict],
    ) -> List[Dict]:

        principles = []

        seen_ids = set()

        for definition in definitions:

            principle = (
                self.build_principle(
                    source_id=definition[
                        "source_id"
                    ],
                    derivation=definition[
                        "derivation"
                    ],
                    sequence=definition.get(
                        "sequence",
                        1,
                    ),
                    review_status=definition.get(
                        "review_status",
                        "pending",
                    ),
                )
            )

            if principle["id"] in seen_ids:

                raise ValueError(
                    f"Duplicate principle ID: "
                    f"{principle['id']}"
                )

            seen_ids.add(
                principle["id"]
            )

            principles.append(
                principle
            )

        return principles

    ##########################################################
    # SAVE
    ##########################################################

    @staticmethod
    def save(
        principles: List[Dict],
        output_path: str,
    ):

        directory = os.path.dirname(
            output_path
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True,
            )

        output = {

            "knowledge_base": {

                "name":
                    "COI Indian Legal Risk "
                    "Knowledge Base",

                "jurisdiction":
                    "India",

                "principle_count":
                    len(principles),

                "generated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
            },

            "principles":
                principles,
        }

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                output,
                file,
                indent=2,
                ensure_ascii=False,
            )


##############################################################
# TEST
##############################################################

if __name__ == "__main__":

    source_path = (
        "knowledge_base/"
        "sources/"
        "indian_contract_act.json"
    )

    output_path = (
        "knowledge_base/"
        "processed/"
        "test_principles.json"
    )

    builder = LegalPrincipleBuilder(
        source_path=source_path
    )

    ##########################################################
    # TEST DERIVATIONS
    #
    # These are prototype derived records used to validate
    # the transformation pipeline.
    #
    # They remain review_status = pending.
    ##########################################################

    definitions = [

        {
            "source_id":
                "ICA_039",

            "sequence":
                1,

            "review_status":
                "pending",

            "derivation": {

                "topic":
                    "Termination and Remedies",

                "subtopic":
                    "Refusal to Perform Contract",

                "principle": (
                    "A complete refusal by a party "
                    "to perform its contractual promise, "
                    "or conduct disabling that party from "
                    "performing it in its entirety, may "
                    "give the other party a right to end "
                    "the contract, subject to the effect "
                    "of acquiescence in continuation."
                ),

                "risk_factors": [

                    (
                        "complete refusal to perform "
                        "contractual obligations"
                    ),

                    (
                        "conduct disabling a party "
                        "from performing its promise "
                        "in its entirety"
                    ),
                ],

                "mitigating_factors": [

                    (
                        "clear contractual mechanisms "
                        "for responding to serious "
                        "non-performance"
                    ),

                    (
                        "documented handling of any "
                        "decision to continue the "
                        "contract after refusal"
                    ),
                ],

                "analysis_note": (
                    "Derived from Section 39 of the "
                    "Indian Contract Act, 1872. "
                    "This prototype principle must "
                    "be reviewed before production use."
                ),
            },
        },

        {
            "source_id":
                "ICA_073",

            "sequence":
                1,

            "review_status":
                "pending",

            "derivation": {

                "topic":
                    "Liability and Damages",

                "subtopic":
                    "Compensation for Breach",

                "principle": (
                    "Compensation for breach may extend "
                    "to loss or damage that naturally "
                    "arises in the usual course from "
                    "the breach or that was within the "
                    "parties' contemplation when the "
                    "contract was made."
                ),

                "risk_factors": [

                    (
                        "contractual exposure to losses "
                        "arising naturally from breach"
                    ),

                    (
                        "foreseeable losses contemplated "
                        "when the contract was formed"
                    ),
                ],

                "mitigating_factors": [

                    (
                        "clear allocation of contractual "
                        "liability"
                    ),

                    (
                        "careful definition of recoverable "
                        "loss and available remedies"
                    ),
                ],

                "analysis_note": (
                    "Derived from Section 73 of the "
                    "Indian Contract Act, 1872. "
                    "This prototype principle must "
                    "be reviewed before production use."
                ),
            },
        },
    ]

    principles = builder.build_many(
        definitions
    )

    builder.save(
        principles=principles,
        output_path=output_path,
    )

    print(
        "=" * 70
    )

    print(
        "LEGAL PRINCIPLE BUILDER TEST"
    )

    print(
        "=" * 70
    )

    print(
        f"\nSource records      : "
        f"{len(builder.source_records)}"
    )

    print(
        f"Principles generated: "
        f"{len(principles)}"
    )

    print(
        f"Output              : "
        f"{output_path}"
    )

    for principle in principles:

        print(
            "\n"
            + "-" * 70
        )

        print(
            f"ID            : "
            f"{principle['id']}"
        )

        print(
            f"Source ID     : "
            f"{principle['source_id']}"
        )

        print(
            f"Topic         : "
            f"{principle['topic']}"
        )

        print(
            f"Subtopic      : "
            f"{principle['subtopic']}"
        )

        print(
            f"Review status : "
            f"{principle['review_status']}"
        )

        print(
            f"Verified      : "
            f"{principle['source_verified']}"
        )

        print(
            "\nPrinciple:"
        )

        print(
            principle[
                "principle"
            ]
        )

        print(
            "\nSource provision preserved:"
        )

        print(
            principle[
                "raw_provision"
            ]
        )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "Principle transformation completed successfully."
    )

    print(
        "=" * 70
    )