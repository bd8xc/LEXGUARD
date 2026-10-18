import json
import os
import re
from typing import Dict, List


class IndianLegalSourceIngester:
    """
    Loads and validates structured Indian legal source documents.

    This layer preserves the distinction between:

        RAW LEGAL SOURCE
                ↓
        STRUCTURED SOURCE RECORD
                ↓
        DERIVED LEGAL PRINCIPLE

    It does not classify contract risk and does not generate
    legal interpretations by itself.
    """

    REQUIRED_DOCUMENT_FIELDS = [
        "title",
        "jurisdiction",
        "authority_type",
        "source_name",
    ]

    REQUIRED_PROVISION_FIELDS = [
        "section",
        "heading",
        "text",
    ]

    def __init__(
        self,
        source_path: str,
    ):

        self.source_path = source_path

    ##########################################################
    # LOAD JSON
    ##########################################################

    def load(self) -> Dict:

        if not os.path.exists(
            self.source_path
        ):

            raise FileNotFoundError(
                f"Source file not found: "
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

        return data

    ##########################################################
    # VALIDATE DOCUMENT METADATA
    ##########################################################

    def validate_document(
        self,
        document: Dict,
    ):

        for field in (
            self.REQUIRED_DOCUMENT_FIELDS
        ):

            if not document.get(
                field
            ):

                raise ValueError(
                    f"Missing document field: "
                    f"{field}"
                )

        if (
            document["jurisdiction"]
            .strip()
            .lower()
            != "india"
        ):

            raise ValueError(
                "Only Indian legal sources are "
                "allowed in this knowledge base."
            )

    ##########################################################
    # VALIDATE PROVISION
    ##########################################################

    def validate_provision(
        self,
        provision: Dict,
    ):

        for field in (
            self.REQUIRED_PROVISION_FIELDS
        ):

            if not provision.get(
                field
            ):

                raise ValueError(
                    f"Missing provision field: "
                    f"{field}"
                )

    ##########################################################
    # NORMALIZE TEXT
    ##########################################################

    @staticmethod
    def normalize_text(
        text: str,
    ) -> str:

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    ##########################################################
    # BUILD SOURCE RECORD
    ##########################################################

    def build_record(
        self,
        document: Dict,
        provision: Dict,
    ) -> Dict:

        section = str(
            provision["section"]
        ).strip()

        normalized_id = re.sub(
            r"[^A-Za-z0-9]+",
            "_",
            section,
        ).strip("_")

        record_id = (
            f"ICA_{normalized_id.zfill(3)}"
        )

        return {

            "id":
                record_id,

            "jurisdiction":
                document[
                    "jurisdiction"
                ],

            "authority_type":
                document[
                    "authority_type"
                ],

            "source_title":
                document[
                    "title"
                ],

            "source_name":
                document[
                    "source_name"
                ],

            "act_number":
                document.get(
                    "act_number"
                ),

            "source_section":
                f"Section {section}",

            "section_heading":
                self.normalize_text(
                    provision[
                        "heading"
                    ]
                ),

            "raw_provision":
                self.normalize_text(
                    provision[
                        "text"
                    ]
                ),

            "source_verified":
                False,
        }

    ##########################################################
    # INGEST
    ##########################################################

    def ingest(
        self,
    ) -> List[Dict]:

        data = self.load()

        if "document" not in data:

            raise ValueError(
                "Source JSON must contain "
                "'document' metadata."
            )

        if "provisions" not in data:

            raise ValueError(
                "Source JSON must contain "
                "'provisions'."
            )

        document = data[
            "document"
        ]

        provisions = data[
            "provisions"
        ]

        self.validate_document(
            document
        )

        if not isinstance(
            provisions,
            list,
        ):

            raise TypeError(
                "'provisions' must be a list."
            )

        records = []

        seen_ids = set()

        for provision in provisions:

            self.validate_provision(
                provision
            )

            record = self.build_record(
                document=document,
                provision=provision,
            )

            if record["id"] in seen_ids:

                raise ValueError(
                    f"Duplicate source record ID: "
                    f"{record['id']}"
                )

            seen_ids.add(
                record["id"]
            )

            records.append(
                record
            )

        return records


##############################################################
# TEST
##############################################################

if __name__ == "__main__":

    source_path = (
        "knowledge_base/"
        "sources/"
        "indian_contract_act.json"
    )

    ingester = IndianLegalSourceIngester(
        source_path=source_path
    )

    records = ingester.ingest()

    print(
        "=" * 70
    )

    print(
        "INDIAN LEGAL SOURCE INGESTION"
    )

    print(
        "=" * 70
    )

    print(
        f"\nSource records : "
        f"{len(records)}"
    )

    for record in records:

        print(
            "\n"
            + "-" * 70
        )

        print(
            f"ID        : "
            f"{record['id']}"
        )

        print(
            f"Source    : "
            f"{record['source_title']}"
        )

        print(
            f"Section   : "
            f"{record['source_section']}"
        )

        print(
            f"Heading   : "
            f"{record['section_heading']}"
        )

        print(
            f"Verified  : "
            f"{record['source_verified']}"
        )

        print(
            "\nRaw provision:"
        )

        print(
            record[
                "raw_provision"
            ]
        )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "Source ingestion completed successfully."
    )

    print(
        "=" * 70
    )