import re


class ClauseSegmenter:
    """
    Splits extracted legal contract text into structured clauses.

    Supports numbered legal structures such as:

        1. SERVICES
        1.1 The Supplier shall...
        1.2 The Customer shall...

        7. TERMINATION
        7.1 Either party may...
        7.2 The Supplier may...

    Output example:

        {
            "index": 1,
            "clause_number": "1.1",
            "section": "1",
            "heading": "SERVICES",
            "text": "The Supplier shall..."
        }

    If no numbered clauses are detected, paragraph-based
    fallback segmentation is used.
    """

    ##########################################################
    # MAIN SEGMENTATION METHOD
    ##########################################################

    def segment(self, text):

        ######################################################
        # VALIDATION
        ######################################################

        if not isinstance(text, str):

            raise TypeError(
                "Document text must be a string."
            )

        text = text.strip()

        if not text:

            return []

        ######################################################
        # NORMALIZE PDF LINE WRAPPING
        ######################################################

        text = self._normalize_lines(
            text
        )

        ######################################################
        # FIND NUMBERED SECTIONS / CLAUSES
        #
        # Examples:
        #
        # 1. SERVICES
        #
        # 1.1 The Supplier shall...
        #
        # 7.2 The Customer shall...
        #
        # 10. FORCE MAJEURE
        ######################################################

        pattern = re.compile(

            r"(?m)^"

            r"(\d+(?:\.\d+)*)"

            r"\.?\s+"

            r"(.+?)"

            r"(?="

            r"\n\d+(?:\.\d+)*\.?\s+"

            r"|\Z"

            r")",

            re.DOTALL,
        )

        matches = list(
            pattern.finditer(
                text
            )
        )

        ######################################################
        # STORAGE
        ######################################################

        clauses = []

        current_section = None

        current_heading = None

        clause_index = 0

        ######################################################
        # PROCESS EVERY MATCH
        ######################################################

        for match in matches:

            ##################################################
            # CLAUSE NUMBER
            #
            # Example:
            #
            # 7
            # 7.1
            # 7.1.2
            ##################################################

            clause_number = (
                match
                .group(1)
                .strip()
            )

            ##################################################
            # CLAUSE CONTENT
            ##################################################

            content = (
                match
                .group(2)
                .strip()
            )

            content = self._clean_clause(
                content
            )

            ##################################################
            # DETERMINE CLAUSE DEPTH
            #
            # 7
            # depth = 1
            #
            # 7.1
            # depth = 2
            #
            # 7.1.1
            # depth = 3
            ##################################################

            depth = len(
                clause_number.split(
                    "."
                )
            )

            ##################################################
            # TOP-LEVEL SECTION
            #
            # Examples:
            #
            # 7. TERMINATION
            #
            # 8. INDEMNIFICATION
            #
            # 9. LIMITATION OF LIABILITY
            ##################################################

            if depth == 1:

                heading, body = (
                    self._extract_heading_and_body(
                        content
                    )
                )

                ################################################
                # VALID SECTION HEADING
                ################################################

                if heading:

                    current_section = (
                        clause_number
                    )

                    current_heading = (
                        heading
                    )

                    ################################################
                    # SOME PDFS MERGE:
                    #
                    # 14. SIGNATURES
                    #
                    # IN WITNESS WHEREOF...
                    #
                    # INTO:
                    #
                    # 14. SIGNATURES IN WITNESS WHEREOF...
                    #
                    # If this happens, preserve the body.
                    ################################################

                    if body:

                        clause_index += 1

                        clauses.append(
                            {
                                "index":
                                    clause_index,

                                "clause_number":
                                    clause_number,

                                "section":
                                    current_section,

                                "heading":
                                    current_heading,

                                "text":
                                    body,
                            }
                        )

                    ################################################
                    # Heading itself is metadata.
                    #
                    # Do not classify:
                    #
                    # "TERMINATION"
                    #
                    # as its own clause.
                    ################################################

                    continue

            ##################################################
            # NORMAL SUBCLAUSE
            ##################################################

            clause_index += 1

            clauses.append(
                {
                    "index":
                        clause_index,

                    "clause_number":
                        clause_number,

                    "section":
                        current_section,

                    "heading":
                        current_heading,

                    "text":
                        content,
                }
            )

        ######################################################
        # FALLBACK FOR UNNUMBERED CONTRACTS
        ######################################################

        if not clauses:

            clauses = (
                self._fallback_segmentation(
                    text
                )
            )

        return clauses

    ##########################################################
    # NORMALIZE PDF LINE WRAPPING
    ##########################################################

    @staticmethod
    def _normalize_lines(text):
        """
        Repairs PDF soft line wrapping while preserving
        numbered clause boundaries.

        Example input:

            7.1 Either party may terminate this Agreement
            for material breach if the breaching party fails
            to cure the breach.

            7.2 The Supplier may terminate this Agreement
            at any time.

        Becomes:

            7.1 Either party may terminate this Agreement
            for material breach if the breaching party fails
            to cure the breach.

            7.2 The Supplier may terminate this Agreement
            at any time.

        Internally each wrapped clause is joined into a
        single clean line before segmentation.

        Most importantly, spaces are inserted between
        wrapped lines so we do NOT produce errors such as:

            itsinternal

            noticedescribing

            monetarycap
        """

        lines = text.splitlines()

        normalized = []

        buffer = ""

        ######################################################
        # DETECT NUMBERED CLAUSE START
        #
        # Matches:
        #
        # 1. SERVICES
        # 1.1 Text
        # 7.2 Text
        # 10. FORCE MAJEURE
        ######################################################

        clause_start = re.compile(
            r"^\d+(?:\.\d+)*\.?\s+"
        )

        for raw_line in lines:

            ##################################################
            # CLEAN CURRENT LINE
            ##################################################

            line = raw_line.strip()

            ##################################################
            # BLANK LINE
            ##################################################

            if not line:

                if buffer:

                    normalized.append(
                        buffer.strip()
                    )

                    buffer = ""

                continue

            ##################################################
            # NEW NUMBERED SECTION OR CLAUSE
            ##################################################

            if clause_start.match(
                line
            ):

                ################################################
                # SAVE PREVIOUS BUFFER
                ################################################

                if buffer:

                    normalized.append(
                        buffer.strip()
                    )

                ################################################
                # START NEW BUFFER
                ################################################

                buffer = line

            ##################################################
            # CONTINUATION OF PREVIOUS PDF LINE
            ##################################################

            else:

                if buffer:

                    ################################################
                    # ALWAYS INSERT A SPACE.
                    #
                    # Prevent:
                    #
                    # "its" + "internal"
                    #
                    # becoming:
                    #
                    # "itsinternal"
                    ################################################

                    buffer += (
                        " "
                        + line
                    )

                else:

                    ################################################
                    # TEXT BEFORE FIRST NUMBERED CLAUSE
                    #
                    # Example:
                    #
                    # MASTER SERVICES AGREEMENT
                    #
                    # This Master Services Agreement...
                    ################################################

                    normalized.append(
                        line
                    )

        ######################################################
        # SAVE FINAL BUFFER
        ######################################################

        if buffer:

            normalized.append(
                buffer.strip()
            )

        ######################################################
        # REBUILD DOCUMENT
        ######################################################

        return "\n".join(
            normalized
        )

    ##########################################################
    # CLEAN INDIVIDUAL CLAUSE
    ##########################################################

    @staticmethod
    def _clean_clause(text):
        """
        Cleans whitespace inside a single clause.

        Example:

            The Supplier   shall
            perform services.

        becomes:

            The Supplier shall perform services.
        """

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    ##########################################################
    # EXTRACT SECTION HEADING AND BODY
    ##########################################################

    @staticmethod
    def _extract_heading_and_body(content):
        """
        Detects top-level section headings.

        Handles normal headings:

            TERMINATION

            LIMITATION OF LIABILITY

        Also handles PDF extraction where heading and body
        have been merged:

            SIGNATURES IN WITNESS WHEREOF, the parties...

        Returns:

            (
                heading,
                body
            )

        Example:

            content:
                "SIGNATURES IN WITNESS WHEREOF..."

            result:

                heading:
                    "SIGNATURES"

                body:
                    "IN WITNESS WHEREOF..."
        """

        if not content:

            return (
                None,
                "",
            )

        content = content.strip()

        ######################################################
        # CASE 1
        #
        # ENTIRE CONTENT IS A HEADING
        #
        # Example:
        #
        # LIMITATION OF LIABILITY
        ######################################################

        if ClauseSegmenter._looks_like_heading(
            content
        ):

            return (
                content,
                "",
            )

        ######################################################
        # CASE 2
        #
        # HEADING + BODY MERGED ON SAME LINE
        #
        # We look for common legal sentence starters.
        ######################################################

        known_body_starters = [

            "IN WITNESS",

            "THIS AGREEMENT",

            "WHEREAS",

            "THE PARTIES",

            "EACH PARTY",

            "EITHER PARTY",

            "THE SUPPLIER",

            "THE CUSTOMER",

            "NEITHER PARTY",

            "NOTWITHSTANDING",

            "UPON",

            "EXCEPT",

            "SUBJECT TO",

            "IF ",

            "NO ",

            "ALL ",

        ]

        ######################################################
        # TRY EACH BODY STARTER
        ######################################################

        for starter in known_body_starters:

            search_value = (
                " "
                + starter
            )

            position = content.find(
                search_value
            )

            ##################################################
            # BODY STARTER FOUND AFTER POSSIBLE HEADING
            ##################################################

            if position > 0:

                possible_heading = (
                    content[
                        :position
                    ]
                    .strip()
                )

                body = (
                    content[
                        position + 1:
                    ]
                    .strip()
                )

                ################################################
                # VERIFY PREFIX LOOKS LIKE A HEADING
                ################################################

                if ClauseSegmenter._looks_like_heading(
                    possible_heading
                ):

                    return (
                        possible_heading,
                        body,
                    )

        ######################################################
        # CASE 3
        #
        # REGEX FALLBACK
        #
        # Detect a short uppercase prefix followed by
        # normal sentence text.
        #
        # Example:
        #
        # SIGNATURES In witness...
        ######################################################

        match = re.match(

            r"^"

            r"([A-Z][A-Z &,\-/]{2,}?)"

            r"(?="

            r"\s+[A-Z][a-z]"

            r"|$"

            r")",

            content,
        )

        if match:

            heading = (
                match
                .group(1)
                .strip()
            )

            body = (
                content[
                    match.end():
                ]
                .strip()
            )

            ##################################################
            # VERIFY HEADING
            ##################################################

            if (
                heading
                and
                ClauseSegmenter._looks_like_heading(
                    heading
                )
            ):

                return (
                    heading,
                    body,
                )

        ######################################################
        # NOT RECOGNIZED AS A HEADING
        ######################################################

        return (
            None,
            content,
        )

    ##########################################################
    # HEADING DETECTION
    ##########################################################

    @staticmethod
    def _looks_like_heading(text):
        """
        Determines whether text looks like a legal
        section heading.

        Examples that return True:

            SERVICES

            TERMINATION

            LIMITATION OF LIABILITY

            GOVERNING LAW AND DISPUTES

        Examples that return False:

            The Supplier shall provide services.

            Either party may terminate this Agreement.
        """

        if not text:

            return False

        text = text.strip()

        ######################################################
        # HEADINGS SHOULD BE SHORT
        ######################################################

        if len(text) > 100:

            return False

        ######################################################
        # HEADINGS USUALLY SHOULD NOT END LIKE SENTENCES
        ######################################################

        if text.endswith(
            (
                ".",
                ";",
            )
        ):

            return False

        ######################################################
        # GET ONLY LETTERS
        ######################################################

        letters = [

            character

            for character in text

            if character.isalpha()

        ]

        ######################################################
        # MUST CONTAIN LETTERS
        ######################################################

        if not letters:

            return False

        ######################################################
        # COUNT UPPERCASE LETTERS
        ######################################################

        uppercase_count = sum(

            character.isupper()

            for character in letters

        )

        ######################################################
        # UPPERCASE RATIO
        ######################################################

        uppercase_ratio = (

            uppercase_count

            / len(
                letters
            )

        )

        ######################################################
        # REQUIRE AT LEAST 80% UPPERCASE
        ######################################################

        return (
            uppercase_ratio
            >= 0.80
        )

    ##########################################################
    # FALLBACK SEGMENTATION
    ##########################################################

    @staticmethod
    def _fallback_segmentation(text):
        """
        Used when the contract contains no recognizable
        numbered sections.

        Example:

            CONFIDENTIALITY

            Each party agrees to keep...

            The receiving party shall...

        In that situation, split using paragraphs instead.
        """

        ######################################################
        # SPLIT PARAGRAPHS
        ######################################################

        paragraphs = re.split(
            r"\n\s*\n",
            text,
        )

        clauses = []

        index = 0

        ######################################################
        # PROCESS PARAGRAPHS
        ######################################################

        for paragraph in paragraphs:

            ##################################################
            # NORMALIZE WHITESPACE
            ##################################################

            paragraph = re.sub(
                r"\s+",
                " ",
                paragraph,
            ).strip()

            ##################################################
            # IGNORE TINY FRAGMENTS
            ##################################################

            if len(
                paragraph
            ) < 20:

                continue

            ##################################################
            # ADD FALLBACK CLAUSE
            ##################################################

            index += 1

            clauses.append(
                {
                    "index":
                        index,

                    "clause_number":
                        None,

                    "section":
                        None,

                    "heading":
                        None,

                    "text":
                        paragraph,
                }
            )

        return clauses


##############################################################
# OPTIONAL DIRECT TEST
##############################################################

if __name__ == "__main__":

    sample_text = """
1. SERVICES

1.1 The Supplier shall provide the services described in
the applicable statement of work.

1.2 The Supplier shall perform the services with reasonable
skill and care.

2. TERMINATION

2.1 Either party may terminate this Agreement for material
breach if the breaching party fails to cure such breach
within thirty days.

2.2 The Supplier may terminate this Agreement at any time
without cause.

3. LIMITATION OF LIABILITY

3.1 Neither party shall be liable for indirect or
consequential damages.

3.2 Each party's aggregate liability shall not exceed the
fees paid during the preceding twelve months.

4. SIGNATURES

IN WITNESS WHEREOF, the parties have executed this Agreement.
"""

    ##########################################################
    # CREATE SEGMENTER
    ##########################################################

    segmenter = ClauseSegmenter()

    ##########################################################
    # SEGMENT SAMPLE
    ##########################################################

    clauses = segmenter.segment(
        sample_text
    )

    ##########################################################
    # PRINT RESULTS
    ##########################################################

    print(
        "=" * 70
    )

    print(
        "CLAUSE SEGMENTER TEST"
    )

    print(
        "=" * 70
    )

    print(
        f"\nTotal clauses: "
        f"{len(clauses)}\n"
    )

    for clause in clauses:

        print(
            "-" * 70
        )

        print(
            f"Index   : "
            f"{clause['index']}"
        )

        print(
            f"Number  : "
            f"{clause['clause_number']}"
        )

        print(
            f"Section : "
            f"{clause['section']}"
        )

        print(
            f"Heading : "
            f"{clause['heading']}"
        )

        print(
            "\nText:"
        )

        print(
            clause["text"]
        )

        print()

    print(
        "=" * 70
    )