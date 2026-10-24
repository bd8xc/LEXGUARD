import json
import os
import re
import hashlib
from datetime import datetime, timezone
from typing import Dict, List


class IndianLegalSourceAcquirer:
    """
    Acquires and validates structured Indian legal source material
    before it enters the COI legal knowledge pipeline.

    Responsibilities:

        1. Validate source identity and jurisdiction.
        2. Validate extracted legal provisions.
        3. Normalize text safely.
        4. Preserve provenance metadata.
        5. Detect duplicate sections.
        6. Generate integrity hashes.
        7. Save a source-ingestion-compatible JSON file.

    IMPORTANT:

    This component does NOT:
        - interpret legal meaning
        - classify contractual risk
        - generate legal principles
        - automatically mark sources as verified

    Verification is a separate governance step.
    """

    REQUIRED_SOURCE_FIELDS = [
        "title",
        "jurisdiction",
        "authority_type",
        "act_number",
        "source_name",
        "source_reference",
    ]

    REQUIRED_PROVISION_FIELDS = [
        "section",
        "heading",
        "text",
    ]

    def __init__(
        self,
        source_metadata: Dict,
    ):

        self.source_metadata = (
            source_metadata.copy()
        )

        self.validate_source_metadata()

    ##########################################################
    # NORMALIZATION
    ##########################################################

    @staticmethod
    def normalize_text(
        text: str,
    ) -> str:

        if not isinstance(
            text,
            str,
        ):

            raise TypeError(
                "Legal source text must be a string."
            )

        text = text.replace(
            "\u00a0",
            " ",
        )

        text = re.sub(
            r"[ \t]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s*\n\s*",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    ##########################################################
    # SOURCE METADATA VALIDATION
    ##########################################################

    def validate_source_metadata(
        self,
    ):

        for field in (
            self.REQUIRED_SOURCE_FIELDS
        ):

            value = self.source_metadata.get(
                field
            )

            if (
                not isinstance(
                    value,
                    str,
                )
                or not value.strip()
            ):

                raise ValueError(
                    f"Missing or invalid source "
                    f"metadata field: {field}"
                )

        jurisdiction = (
            self.source_metadata[
                "jurisdiction"
            ]
            .strip()
            .lower()
        )

        if jurisdiction != "india":

            raise ValueError(
                "Only Indian legal sources are "
                "permitted in this knowledge base."
            )

    ##########################################################
    # PROVISION VALIDATION
    ##########################################################

    def validate_provision(
        self,
        provision: Dict,
    ):

        for field in (
            self.REQUIRED_PROVISION_FIELDS
        ):

            if field not in provision:

                raise ValueError(
                    f"Missing provision field: "
                    f"{field}"
                )

        section = str(
            provision[
                "section"
            ]
        ).strip()

        heading = self.normalize_text(
            provision[
                "heading"
            ]
        )

        text = self.normalize_text(
            provision[
                "text"
            ]
        )

        if not section:

            raise ValueError(
                "Section number cannot be empty."
            )

        if not heading:

            raise ValueError(
                f"Section {section} has no heading."
            )

        if not text:

            raise ValueError(
                f"Section {section} has no text."
            )

        # Guard against obviously failed extraction.
        if len(text) < 20:

            raise ValueError(
                f"Section {section} text appears "
                f"too short to be a valid provision."
            )

    ##########################################################
    # CONTENT HASH
    ##########################################################

    @staticmethod
    def build_hash(
        text: str,
    ) -> str:

        return hashlib.sha256(
            text.encode(
                "utf-8"
            )
        ).hexdigest()

    ##########################################################
    # NORMALIZE PROVISION
    ##########################################################

    def normalize_provision(
        self,
        provision: Dict,
    ) -> Dict:

        self.validate_provision(
            provision
        )

        section = str(
            provision[
                "section"
            ]
        ).strip()

        heading = self.normalize_text(
            provision[
                "heading"
            ]
        )

        text = self.normalize_text(
            provision[
                "text"
            ]
        )

        return {

            "section":
                section,

            "heading":
                heading,

            "text":
                text,

            "content_sha256":
                self.build_hash(
                    text
                ),
        }

    ##########################################################
    # BUILD SOURCE DOCUMENT
    ##########################################################

    def build_document(
        self,
        provisions: List[Dict],
    ) -> Dict:

        if not isinstance(
            provisions,
            list,
        ):

            raise TypeError(
                "provisions must be a list."
            )

        if not provisions:

            raise ValueError(
                "No legal provisions supplied."
            )

        normalized_provisions = []

        seen_sections = set()

        for provision in provisions:

            normalized = (
                self.normalize_provision(
                    provision
                )
            )

            section = normalized[
                "section"
            ]

            if section in seen_sections:

                raise ValueError(
                    f"Duplicate section detected: "
                    f"{section}"
                )

            seen_sections.add(
                section
            )

            normalized_provisions.append(
                normalized
            )

        acquired_at = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

        document_metadata = {

            "title":
                self.source_metadata[
                    "title"
                ].strip(),

            "jurisdiction":
                "India",

            "authority_type":
                self.source_metadata[
                    "authority_type"
                ].strip(),

            "act_number":
                self.source_metadata[
                    "act_number"
                ].strip(),

            "source_name":
                self.source_metadata[
                    "source_name"
                ].strip(),

            "source_reference":
                self.source_metadata[
                    "source_reference"
                ].strip(),

            "acquired_at":
                acquired_at,

            # Acquisition alone does NOT establish
            # authoritative verification.
            "source_verified":
                False,

            "verification_status":
                "pending",
        }

        return {

            "document":
                document_metadata,

            "provisions":
                normalized_provisions,
        }

    ##########################################################
    # SAVE
    ##########################################################

    @staticmethod
    def save_document(
        document: Dict,
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

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                document,
                file,
                indent=2,
                ensure_ascii=False,
            )

    ##########################################################
    # SUMMARY
    ##########################################################

    @staticmethod
    def print_summary(
        document: Dict,
        output_path: str,
    ):

        metadata = document[
            "document"
        ]

        provisions = document[
            "provisions"
        ]

        print(
            "=" * 70
        )

        print(
            "INDIAN LEGAL SOURCE ACQUISITION"
        )

        print(
            "=" * 70
        )

        print(
            f"\nTitle       : "
            f"{metadata['title']}"
        )

        print(
            f"Jurisdiction: "
            f"{metadata['jurisdiction']}"
        )

        print(
            f"Authority   : "
            f"{metadata['authority_type']}"
        )

        print(
            f"Act number  : "
            f"{metadata['act_number']}"
        )

        print(
            f"Source      : "
            f"{metadata['source_name']}"
        )

        print(
            f"Verified    : "
            f"{metadata['source_verified']}"
        )

        print(
            f"Status      : "
            f"{metadata['verification_status']}"
        )

        print(
            f"Provisions  : "
            f"{len(provisions)}"
        )

        print(
            f"Output      : "
            f"{output_path}"
        )

        for provision in provisions:

            print(
                "\n"
                + "-" * 70
            )

            print(
                f"Section : "
                f"{provision['section']}"
            )

            print(
                f"Heading : "
                f"{provision['heading']}"
            )

            print(
                f"SHA256  : "
                f"{provision['content_sha256'][:16]}"
                f"..."
            )

            print(
                "\nText:"
            )

            print(
                provision[
                    "text"
                ]
            )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "Source acquisition completed successfully."
        )

        print(
            "=" * 70
        )


##############################################################
# PROTOTYPE TEST
##############################################################

if __name__ == "__main__":

    ##########################################################
    # SOURCE METADATA
    #
    # This identifies the intended authoritative source.
    # The actual provisions below remain test fixtures until
    # independently verified against that source.
    ##########################################################

    source_metadata = {

        "title":
            "The Indian Contract Act, 1872",

        "jurisdiction":
            "India",

        "authority_type":
            "Primary legislation",

        "act_number":
            "9 of 1872",

        "source_name":
            "India Code",

        "source_reference":
            "Official India Code record for "
            "The Indian Contract Act, 1872",
    }

    ##########################################################
    # TEST PROVISIONS
    #
    # These validate acquisition mechanics only.
    ##########################################################

    provisions = [

        {
            "section":
                "39",

            "heading":
                (
                    "Effect of refusal of party "
                    "to perform promise wholly"
                ),

            "text":
                (
                    "When a party to a contract has "
                    "refused to perform, or disabled "
                    "himself from performing, his promise "
                    "in its entirety, the promisee may "
                    "put an end to the contract, unless "
                    "he has signified, by words or "
                    "conduct, his acquiescence in its "
                    "continuance."
                ),
        },

        {
            "section":
                "73",

            "heading":
                (
                    "Compensation for loss or damage "
                    "caused by breach of contract"
                ),

            "text":
                (
                    "When a contract has been broken, "
                    "the party who suffers by such breach "
                    "is entitled to receive, from the "
                    "party who has broken the contract, "
                    "compensation for any loss or damage "
                    "caused to him thereby, which "
                    "naturally arose in the usual course "
                    "of things from such breach, or which "
                    "the parties knew, when they made the "
                    "contract, to be likely to result "
                    "from the breach of it."
                ),
        },
    ]

    output_path = (
        "knowledge_base/"
        "sources/"
        "indian_contract_act_acquired.json"
    )

    acquirer = IndianLegalSourceAcquirer(
        source_metadata=source_metadata
    )

    document = acquirer.build_document(
        provisions=provisions
    )

    acquirer.save_document(
        document=document,
        output_path=output_path,
    )

    acquirer.print_summary(
        document=document,
        output_path=output_path,
    )