import json
import os
import re
from typing import Dict, List

import pdfplumber


class IndianActExtractor:
    """
    Extract structured statutory sections from the official
    Indian Contract Act, 1872 PDF.

    Pipeline:

        Official PDF
            ↓
        Extract page text
            ↓
        Remove front matter / Table of Contents
            ↓
        Detect real statutory section headings
            ↓
        Split text into sections
            ↓
        Validate / deduplicate sections
            ↓
        Save structured JSON

    Important:
    The official PDF contains section-number references in its
    Table of Contents before the actual statutory provisions.

    Therefore, parsing the entire PDF directly may cause the
    Table of Contents entry to be selected instead of the real
    statutory section.

    This extractor first identifies the actual beginning of
    Section 1 and removes the preceding front matter.
    """

    def __init__(
        self,
        pdf_path: str,
    ):

        self.pdf_path = pdf_path

        if not os.path.exists(
            self.pdf_path
        ):

            raise FileNotFoundError(
                f"PDF not found: "
                f"{self.pdf_path}"
            )

    ##########################################################
    # EXTRACT FULL PDF TEXT
    ##########################################################

    def extract_full_text(
        self,
    ) -> str:

        pages = []

        with pdfplumber.open(
            self.pdf_path
        ) as pdf:

            for page_number, page in enumerate(
                pdf.pages,
                start=1,
            ):

                text = page.extract_text()

                if not text:
                    continue

                text = text.strip()

                if not text:
                    continue

                pages.append(
                    text
                )

        full_text = "\n".join(
            pages
        )

        if not full_text.strip():

            raise ValueError(
                "No text could be extracted "
                "from the PDF."
            )

        return full_text

    ##########################################################
    # REMOVE FRONT MATTER / TABLE OF CONTENTS
    ##########################################################

    def _remove_front_matter(
        self,
        text: str,
    ) -> str:

        """
        Locate the actual statutory Section 1 and remove
        everything before it.

        The PDF contains an earlier Table of Contents entry
        for Section 1, so we search for all plausible
        '1. Short title' occurrences and select the latest
        plausible occurrence.

        This avoids treating TOC entries such as:

            73. Compensation for loss...
            124. Contract of indemnity defined.

        as actual statutory provisions.
        """

        patterns = [

            # Example:
            # 1.Short title.—This Act may be called...
            r"""
            (?m)
            ^
            \s*
            1
            \s*
            \.
            \s*
            Short
            \s+
            title
            \s*
            [.—-]
            """,

            # More permissive fallback
            r"""
            (?m)
            ^
            \s*
            1
            \s*
            \.
            \s*
            Short
            \s+
            title
            """,
        ]

        candidates = []

        for pattern in patterns:

            matches = re.finditer(
                pattern,
                text,
                flags=re.VERBOSE
                | re.IGNORECASE,
            )

            for match in matches:

                candidates.append(
                    match.start()
                )

        ######################################################
        # FALLBACK
        ######################################################

        if not candidates:

            print(
                "Warning: Could not reliably "
                "locate actual Section 1."
            )

            print(
                "Front matter was not removed."
            )

            return text

        ######################################################
        # USE LATEST SECTION 1 OCCURRENCE
        #
        # Earlier occurrence should be the TOC.
        # Later occurrence should be the actual Act body.
        ######################################################

        body_start = max(
            candidates
        )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "FRONT MATTER DETECTION"
        )

        print(
            "=" * 70
        )

        print(
            f"Section 1 candidates : "
            f"{len(set(candidates))}"
        )

        print(
            f"Act body starts at   : "
            f"character {body_start}"
        )

        print(
            "Front matter / Table of Contents "
            "removed."
        )

        return text[
            body_start:
        ]

    ##########################################################
    # NORMALIZE TEXT
    ##########################################################

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:

        """
        Perform conservative normalization.

        We intentionally preserve line breaks because they are
        useful for identifying statutory section boundaries.
        """

        text = text.replace(
            "\r\n",
            "\n",
        )

        text = text.replace(
            "\r",
            "\n",
        )

        ######################################################
        # NORMALIZE NON-BREAKING SPACES
        ######################################################

        text = text.replace(
            "\u00a0",
            " ",
        )

        ######################################################
        # REMOVE TRAILING SPACES PER LINE
        ######################################################

        lines = []

        for line in text.splitlines():

            line = line.rstrip()

            lines.append(
                line
            )

        text = "\n".join(
            lines
        )

        ######################################################
        # COLLAPSE EXCESSIVE BLANK LINES
        ######################################################

        text = re.sub(
            r"\n{3,}",
            "\n\n",
            text,
        )

        return text.strip()

    ##########################################################
    # SECTION HEADING PATTERN
    ##########################################################

    @staticmethod
    def _section_pattern():

        """
        Match statutory section starts.

        Supports examples such as:

            39. Effect of refusal...
            73.Compensation for loss...
            124.“Contract of indemnity” defined.
            178A. Pledge by person...
            3[178. Pledge by mercantile agent...

        The optional amendment marker such as '3[' is allowed
        before the section number.

        We require the section to begin at the start of a line
        to reduce false matches from citations and prose.
        """

        return re.compile(

            r"""
            (?m)

            ^

            [ \t]*

            # Optional amendment / footnote marker:
            # e.g. 1[, 2[, 3[
            (?:
                \d+
                \[
            )?

            # Section number
            (?P<section>
                \d+
                [A-Z]?
            )

            # Period after section number
            \s*
            \.

            # Text must follow the section number
            (?=
                \s*
                \S
            )
            """,

            re.VERBOSE,
        )

    ##########################################################
    # CHECK WHETHER SECTION NUMBER IS PLAUSIBLE
    ##########################################################

    @staticmethod
    def _is_plausible_section_number(
        section_number: str,
    ) -> bool:

        """
        The Indian Contract Act section range is finite.

        We use a broad upper bound to reject obvious false
        matches such as years, page numbers, monetary values,
        etc.

        Lettered sections such as 178A are supported.
        """

        match = re.match(
            r"^(\d+)([A-Z]?)$",
            section_number,
        )

        if not match:

            return False

        numeric_part = int(
            match.group(1)
        )

        if numeric_part < 1:

            return False

        # Broad safety bound.
        # The Act's operative numbering does not approach 1000.
        if numeric_part > 300:

            return False

        return True

    ##########################################################
    # EXTRACT HEADING
    ##########################################################

    @staticmethod
    def _extract_heading(
        section_text: str,
    ) -> str:

        """
        Extract a readable heading from the beginning of a
        statutory section.

        Prefer text before an em dash because Indian statutes
        commonly use:

            Heading.—Body text

        Otherwise use the first line.
        """

        text = section_text.strip()

        if not text:

            return ""

        ######################################################
        # HEADING BEFORE EM DASH
        ######################################################

        em_dash_positions = []

        for marker in [
            ".—",
            "—",
        ]:

            position = text.find(
                marker
            )

            if position != -1:

                em_dash_positions.append(
                    position
                )

        if em_dash_positions:

            end = min(
                em_dash_positions
            )

            heading = text[
                :end
            ]

            heading = heading.strip(
                " .—-\n\t"
            )

            if heading:

                return heading

        ######################################################
        # FALLBACK: FIRST LINE
        ######################################################

        first_line = (
            text
            .splitlines()[0]
            .strip()
        )

        ######################################################
        # LIMIT VERY LONG HEADING FALLBACKS
        ######################################################

        if len(first_line) > 250:

            first_line = (
                first_line[:250]
                .rstrip()
            )

        return first_line

    ##########################################################
    # EXTRACT SECTIONS
    ##########################################################

    def extract_sections(
        self,
    ) -> List[Dict]:

        ######################################################
        # EXTRACT RAW TEXT
        ######################################################

        full_text = (
            self.extract_full_text()
        )

        ######################################################
        # REMOVE TABLE OF CONTENTS / FRONT MATTER
        ######################################################

        full_text = (
            self._remove_front_matter(
                full_text
            )
        )

        ######################################################
        # NORMALIZE
        ######################################################

        full_text = (
            self._normalize_text(
                full_text
            )
        )

        ######################################################
        # FIND SECTION STARTS
        ######################################################

        pattern = (
            self._section_pattern()
        )

        raw_matches = list(
            pattern.finditer(
                full_text
            )
        )

        if not raw_matches:

            raise ValueError(
                "No statutory section headings "
                "were detected."
            )

        ######################################################
        # FILTER IMPLAUSIBLE SECTION NUMBERS
        ######################################################

        matches = []

        for match in raw_matches:

            section_number = (
                match.group(
                    "section"
                )
            )

            if not (
                self._is_plausible_section_number(
                    section_number
                )
            ):
                continue

            matches.append(
                match
            )

        if not matches:

            raise ValueError(
                "No plausible statutory sections "
                "were detected."
            )

        ######################################################
        # BUILD SECTION RECORDS
        ######################################################

        sections = []

        for index, match in enumerate(
            matches
        ):

            section_number = (
                match.group(
                    "section"
                )
            )

            ##################################################
            # SECTION BODY START
            #
            # Start after:
            #
            #   73.
            #   124.
            #
            ##################################################

            content_start = (
                match.end()
            )

            ##################################################
            # SECTION BODY END
            ##################################################

            if (
                index + 1
                < len(matches)
            ):

                content_end = (
                    matches[
                        index + 1
                    ].start()
                )

            else:

                content_end = len(
                    full_text
                )

            section_text = (
                full_text[
                    content_start:
                    content_end
                ]
                .strip()
            )

            ##################################################
            # SKIP EMPTY RECORDS
            ##################################################

            if not section_text:

                continue

            heading = (
                self._extract_heading(
                    section_text
                )
            )

            record = {

                "section":
                    section_number,

                "heading":
                    heading,

                "text":
                    section_text,
            }

            sections.append(
                record
            )

        ######################################################
        # DEDUPLICATE
        #
        # Front matter removal should already eliminate the
        # TOC problem, but this is an additional safeguard.
        #
        # If duplicate section numbers remain, prefer the
        # record containing more substantive text.
        ######################################################

        sections = (
            self._deduplicate_sections(
                sections
            )
        )

        ######################################################
        # SORT BY SECTION NUMBER
        ######################################################

        sections = sorted(
            sections,
            key=self._section_sort_key,
        )

        return sections

    ##########################################################
    # SECTION SORT KEY
    ##########################################################

    @staticmethod
    def _section_sort_key(
        record: Dict,
    ):

        section = record[
            "section"
        ]

        match = re.match(
            r"^(\d+)([A-Z]?)$",
            section,
        )

        if not match:

            return (
                999999,
                section,
            )

        number = int(
            match.group(1)
        )

        suffix = (
            match.group(2)
            or ""
        )

        return (
            number,
            suffix,
        )

    ##########################################################
    # DEDUPLICATE SECTIONS
    ##########################################################

    @staticmethod
    def _deduplicate_sections(
        sections: List[Dict],
    ) -> List[Dict]:

        """
        Keep one record per section number.

        If duplicates exist, prefer the record with the
        longest substantive text.

        This is a safeguard only; front matter removal should
        prevent most TOC duplicates.
        """

        best = {}

        for record in sections:

            section_number = (
                record[
                    "section"
                ]
            )

            if (
                section_number
                not in best
            ):

                best[
                    section_number
                ] = record

                continue

            current = best[
                section_number
            ]

            current_length = len(
                current.get(
                    "text",
                    "",
                )
            )

            new_length = len(
                record.get(
                    "text",
                    "",
                )
            )

            if (
                new_length
                > current_length
            ):

                best[
                    section_number
                ] = record

        return list(
            best.values()
        )

    ##########################################################
    # SAVE JSON
    ##########################################################

    def save(
        self,
        sections: List[Dict],
        output_path: str,
    ):

        output_directory = (
            os.path.dirname(
                output_path
            )
        )

        if output_directory:

            os.makedirs(
                output_directory,
                exist_ok=True,
            )

        output = {

            "document": {
                "title":
                    "The Indian Contract Act, 1872",

                "jurisdiction":
                    "India",

                "authority_type":
                    "Primary legislation",

                "source":
                    "Official legislative PDF",

                "verified":
                    True,

                "extraction_method":
                    (
                        "PDF text extraction with "
                        "front-matter removal and "
                        "section-boundary parsing"
                    ),
            },

            "section_count":
                len(sections),

            "sections":
                sections,
        }

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                output,
                file,
                ensure_ascii=False,
                indent=2,
            )

    ##########################################################
    # FIND SECTION
    ##########################################################

    @staticmethod
    def find_section(
        sections: List[Dict],
        section_number: str,
    ):

        section_number = str(
            section_number
        )

        for section in sections:

            if (
                section[
                    "section"
                ]
                == section_number
            ):

                return section

        return None

    ##########################################################
    # PRINT ONE SECTION
    ##########################################################

    @staticmethod
    def _print_section(
        section: Dict,
    ):

        print(
            "\n"
            + "-" * 70
        )

        print(
            f"Section : "
            f"{section['section']}"
        )

        print(
            f"Heading : "
            f"{section['heading']}"
        )

        print(
            "\nPreview:"
        )

        preview = (
            section[
                "text"
            ][:700]
        )

        print(
            preview
        )

    ##########################################################
    # PRINT SUMMARY
    ##########################################################

    def print_summary(
        self,
        sections: List[Dict],
        output_path: str,
    ):

        print(
            "\n"
            + "=" * 70
        )

        print(
            "INDIAN ACT PDF EXTRACTION"
        )

        print(
            "=" * 70
        )

        print(
            f"\nSections detected : "
            f"{len(sections)}"
        )

        print(
            f"Output            : "
            f"{output_path}"
        )

        ######################################################
        # IMPORTANT TEST SECTIONS
        ######################################################

        test_sections = [
            "10",
            "39",
            "55",
            "73",
            "74",
            "75",
            "124",
            "125",
        ]

        print(
            "\n"
            + "=" * 70
        )

        print(
            "SAMPLE EXTRACTED SECTIONS"
        )

        print(
            "=" * 70
        )

        missing = []

        for section_number in test_sections:

            section = (
                self.find_section(
                    sections,
                    section_number,
                )
            )

            if section is None:

                missing.append(
                    section_number
                )

                continue

            self._print_section(
                section
            )

        ######################################################
        # TEST RESULT
        ######################################################

        print(
            "\n"
            + "=" * 70
        )

        if missing:

            print(
                "Missing expected sections:"
            )

            print(
                ", ".join(
                    missing
                )
            )

        else:

            print(
                "All expected test sections "
                "were detected."
            )

        print(
            "\nExtraction completed."
        )

        print(
            "=" * 70
        )


##############################################################
# COMMAND-LINE TEST
##############################################################

if __name__ == "__main__":

    pdf_path = (
        "knowledge_base/"
        "raw_sources/"
        "indian_contract_act_1872.pdf"
    )

    output_path = (
        "knowledge_base/"
        "processed/"
        "indian_contract_act_sections.json"
    )

    ##########################################################
    # CREATE EXTRACTOR
    ##########################################################

    extractor = IndianActExtractor(
        pdf_path=pdf_path
    )

    ##########################################################
    # EXTRACT REAL STATUTORY SECTIONS
    ##########################################################

    sections = (
        extractor.extract_sections()
    )

    ##########################################################
    # SAVE ONCE
    ##########################################################

    extractor.save(
        sections=sections,
        output_path=output_path,
    )

    ##########################################################
    # PRINT SUMMARY ONCE
    ##########################################################

    extractor.print_summary(
        sections=sections,
        output_path=output_path,
    )