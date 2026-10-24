import os
import json
import csv
from collections import Counter
from pathlib import Path

from processing.document_processor import DocumentProcessor
from processing.clause_segmenter import ClauseSegmenter
from models.inference import ContractRiskPredictor
from reporting.document_report import generate_pdf_report

##############################################################
# CONFIGURATION
##############################################################

DEFAULT_DOCUMENT = "sample_contracts/contract.pdf"

OUTPUT_DIR = Path("outputs")

CSV_OUTPUT = OUTPUT_DIR / "contract_analysis.csv"

JSON_OUTPUT = OUTPUT_DIR / "contract_analysis.json"

SUMMARY_OUTPUT = OUTPUT_DIR / "contract_summary.json"


##############################################################
# SECTIONS THAT SHOULD NOT BE CLASSIFIED
##############################################################

SKIP_HEADINGS = {
    "SIGNATURE",
    "SIGNATURES",
    "EXECUTION",
    "EXECUTION PAGE",
    "SIGNATURE PAGE",
}


##############################################################
# CONTRACT ANALYZER
##############################################################

class ContractAnalyzer:

    def __init__(self):

        print(
            "=" * 70
        )

        print(
            "CONTRACT RISK ANALYZER"
        )

        print(
            "=" * 70
        )

        ######################################################
        # DOCUMENT PROCESSOR
        ######################################################

        print(
            "\nInitializing document processor..."
        )

        self.document_processor = (
            DocumentProcessor()
        )

        ######################################################
        # CLAUSE SEGMENTER
        ######################################################

        print(
            "Initializing clause segmenter..."
        )

        self.clause_segmenter = (
            ClauseSegmenter()
        )

        ######################################################
        # LOAD MODEL ONCE
        ######################################################

        print(
            "Loading Contract Risk Predictor..."
        )

        self.predictor = (
            ContractRiskPredictor()
        )

        print(
            "\nSystem ready."
        )

    ##########################################################
    # DETERMINE WHETHER CLAUSE SHOULD BE SKIPPED
    ##########################################################

    @staticmethod
    def should_skip_clause(
        clause,
    ):

        heading = (
            clause.get(
                "heading"
            )
            or ""
        )

        heading = (
            heading
            .strip()
            .upper()
        )

        ######################################################
        # SKIP KNOWN NON-RISK SECTIONS
        ######################################################

        if heading in SKIP_HEADINGS:

            return True

        ######################################################
        # SKIP EMPTY TEXT
        ######################################################

        text = (
            clause.get(
                "text"
            )
            or ""
        ).strip()

        if not text:

            return True

        ######################################################
        # SKIP VERY SHORT FRAGMENTS
        ######################################################

        if len(
            text.split()
        ) < 5:

            return True

        return False

    ##########################################################
    # ANALYZE DOCUMENT
    ##########################################################

    def analyze(
        self,
        file_path,
    ):

        print(
            "\n"
            + "=" * 70
        )

        print(
            "PROCESSING DOCUMENT"
        )

        print(
            "=" * 70
        )

        ######################################################
        # STEP 1
        # EXTRACT DOCUMENT TEXT
        ######################################################

        document = (
            self.document_processor.process(
                file_path
            )
        )

        print(
            f"\nFile       : "
            f"{document['file_name']}"
        )

        print(
            f"Type       : "
            f"{document['file_type']}"
        )

        print(
            f"Pages      : "
            f"{document['page_count']}"
        )

        print(
            f"Words      : "
            f"{document['word_count']}"
        )

        ######################################################
        # STEP 2
        # SEGMENT CLAUSES
        ######################################################

        clauses = (
            self.clause_segmenter.segment(
                document["text"]
            )
        )

        print(
            f"Units found: "
            f"{len(clauses)}"
        )

        ######################################################
        # STEP 3
        # FILTER NON-RISK BLOCKS
        ######################################################

        clauses_to_analyze = []

        skipped_clauses = []

        for clause in clauses:

            if self.should_skip_clause(
                clause
            ):

                skipped_clauses.append(
                    clause
                )

            else:

                clauses_to_analyze.append(
                    clause
                )

        print(
            f"Analyzing  : "
            f"{len(clauses_to_analyze)}"
        )

        print(
            f"Skipped    : "
            f"{len(skipped_clauses)}"
        )

        ######################################################
        # STEP 4
        # RUN LEGALBERT ON EACH CLAUSE
        ######################################################

        results = []

        print(
            "\n"
            + "=" * 70
        )

        print(
            "RUNNING CLAUSE-LEVEL RISK ANALYSIS"
        )

        print(
            "=" * 70
            + "\n"
        )

        total = len(
            clauses_to_analyze
        )

        for position, clause in enumerate(
            clauses_to_analyze,
            start=1,
        ):

            clause_number = (
                clause.get(
                    "clause_number"
                )
                or "N/A"
            )

            heading = (
                clause.get(
                    "heading"
                )
                or "UNSPECIFIED"
            )

            text = (
                clause.get(
                    "text"
                )
                or ""
            )

            ##################################################
            # PROGRESS
            ##################################################

            print(
                f"[{position}/{total}] "
                f"{clause_number} - "
                f"{heading}"
            )

            ##################################################
            # MODEL PREDICTION
            ##################################################

            try:

                prediction = (
                    self.predictor.predict(
                        text
                    )
                )

            except Exception as error:

                print(
                    f"    ERROR: {error}"
                )

                results.append(
                    {
                        "index":
                            clause.get(
                                "index"
                            ),

                        "clause_number":
                            clause_number,

                        "section":
                            clause.get(
                                "section"
                            ),

                        "heading":
                            heading,

                        "text":
                            text,

                        "prediction":
                            "ERROR",

                        "model_score":
                            None,

                        "num_windows":
                            None,

                        "class_scores":
                            {},

                        "error":
                            str(error),
                    }
                )

                continue

            ##################################################
            # NORMALIZE PREDICTOR OUTPUT
            ##################################################

            predicted_class = (
                prediction.get(
                    "prediction",
                    prediction.get(
                        "predicted_class",
                        prediction.get(
                            "label",
                            "UNKNOWN",
                        ),
                    ),
                )
            )

            model_score = (
                prediction.get(
                    "model_score",
                    prediction.get(
                        "confidence",
                        prediction.get(
                            "score"
                        ),
                    ),
                )
            )

            num_windows = (
                prediction.get(
                    "num_windows",
                    prediction.get(
                        "windows"
                    ),
                )
            )

            class_scores = (
                prediction.get(
                    "class_scores",
                    prediction.get(
                        "scores",
                        {},
                    ),
                )
            )

            ##################################################
            # SAVE RESULT
            ##################################################

            result = {

                "index":
                    clause.get(
                        "index"
                    ),

                "clause_number":
                    clause_number,

                "section":
                    clause.get(
                        "section"
                    ),

                "heading":
                    heading,

                "text":
                    text,

                "prediction":
                    predicted_class,

                "model_score":
                    model_score,

                "num_windows":
                    num_windows,

                "class_scores":
                    class_scores,
            }

            results.append(
                result
            )

            ##################################################
            # PRINT RESULT
            ##################################################

            if model_score is not None:

                try:

                    score_value = float(
                        model_score
                    )

                    ################################################
                    # Handle either:
                    #
                    # 0.9953
                    #
                    # or:
                    #
                    # 99.53
                    ################################################

                    if score_value <= 1:

                        display_score = (
                            score_value
                            * 100
                        )

                    else:

                        display_score = (
                            score_value
                        )

                    print(
                        f"    -> "
                        f"{predicted_class} "
                        f"({display_score:.2f}%)"
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    print(
                        f"    -> "
                        f"{predicted_class}"
                    )

            else:

                print(
                    f"    -> "
                    f"{predicted_class}"
                )

        ######################################################
        # STEP 5
        # CREATE SUMMARY
        ######################################################

        summary = (
            self._create_summary(
                document=document,
                all_clauses=clauses,
                analyzed_clauses=results,
                skipped_clauses=skipped_clauses,
            )
        )

        ######################################################
        # STEP 6
        # SAVE REPORTS
        ######################################################

        self._save_reports(
            document=document,
            results=results,
            summary=summary,
        )

        ######################################################
        # STEP 7
        # PRINT SUMMARY
        ######################################################

        self._print_summary(
            summary
        )

        return {

            "document":
                document,

            "results":
                results,

            "summary":
                summary,

            "skipped":
                skipped_clauses,
        }

    ##########################################################
    # CREATE CONTRACT SUMMARY
    ##########################################################

    @staticmethod
    def _create_summary(
        document,
        all_clauses,
        analyzed_clauses,
        skipped_clauses,
    ):

        ######################################################
        # COUNT PREDICTIONS
        ######################################################

        predictions = [

            result["prediction"]

            for result in analyzed_clauses

            if result[
                "prediction"
            ] != "ERROR"

        ]

        counts = Counter(
            predictions
        )

        ######################################################
        # EXTRACT HIGH-RISK CLAUSES
        ######################################################

        high_risk_clauses = [

            {
                "clause_number":
                    result[
                        "clause_number"
                    ],

                "heading":
                    result[
                        "heading"
                    ],

                "text":
                    result[
                        "text"
                    ],

                "model_score":
                    result[
                        "model_score"
                    ],
            }

            for result in analyzed_clauses

            if (
                str(
                    result[
                        "prediction"
                    ]
                )
                .strip()
                .lower()
                == "high"
            )

        ]

        ######################################################
        # MEDIUM-RISK CLAUSES
        ######################################################

        medium_risk_clauses = [

            {
                "clause_number":
                    result[
                        "clause_number"
                    ],

                "heading":
                    result[
                        "heading"
                    ],

                "text":
                    result[
                        "text"
                    ],

                "model_score":
                    result[
                        "model_score"
                    ],
            }

            for result in analyzed_clauses

            if (
                str(
                    result[
                        "prediction"
                    ]
                )
                .strip()
                .lower()
                == "medium"
            )

        ]

        ######################################################
        # ERRORS
        ######################################################

        errors = [

            result

            for result in analyzed_clauses

            if result[
                "prediction"
            ] == "ERROR"

        ]

        ######################################################
        # SUMMARY
        ######################################################

        summary = {

            "file_name":
                document[
                    "file_name"
                ],

            "page_count":
                document[
                    "page_count"
                ],

            "word_count":
                document[
                    "word_count"
                ],

            "total_extracted_units":
                len(
                    all_clauses
                ),

            "analyzed_clauses":
                len(
                    analyzed_clauses
                ),

            "skipped_clauses":
                len(
                    skipped_clauses
                ),

            "prediction_counts":
                {
                    "Seed":
                        counts.get(
                            "Seed",
                            0,
                        ),

                    "Low":
                        counts.get(
                            "Low",
                            0,
                        ),

                    "Medium":
                        counts.get(
                            "Medium",
                            0,
                        ),

                    "High":
                        counts.get(
                            "High",
                            0,
                        ),
                },

            "high_risk_count":
                len(
                    high_risk_clauses
                ),

            "medium_risk_count":
                len(
                    medium_risk_clauses
                ),

            "high_risk_clauses":
                high_risk_clauses,

            "medium_risk_clauses":
                medium_risk_clauses,

            "prediction_errors":
                len(
                    errors
                ),
        }

        return summary

    ##########################################################
    # SAVE REPORTS
    ##########################################################

    @staticmethod
    def _save_reports(
        document,
        results,
        summary,
    ):

        ######################################################
        # CREATE OUTPUT DIRECTORY
        ######################################################

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        ######################################################
        # SAVE FULL JSON REPORT
        ######################################################

        json_report = {

            "document":
                {
                    "file_name":
                        document[
                            "file_name"
                        ],

                    "file_type":
                        document[
                            "file_type"
                        ],

                    "page_count":
                        document[
                            "page_count"
                        ],

                    "character_count":
                        document[
                            "character_count"
                        ],

                    "word_count":
                        document[
                            "word_count"
                        ],
                },

            "summary":
                summary,

            "clauses":
                results,
        }

        with open(
            JSON_OUTPUT,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                json_report,
                file,
                indent=4,
                ensure_ascii=False,
                default=str,
            )

        ######################################################
        # SAVE SUMMARY JSON
        ######################################################

        with open(
            SUMMARY_OUTPUT,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                summary,
                file,
                indent=4,
                ensure_ascii=False,
                default=str,
            )

        ######################################################
        # SAVE CSV
        ######################################################

        csv_rows = []

        for result in results:

            class_scores = (
                result.get(
                    "class_scores"
                )
                or {}
            )

            row = {

                "index":
                    result.get(
                        "index"
                    ),

                "clause_number":
                    result.get(
                        "clause_number"
                    ),

                "section":
                    result.get(
                        "section"
                    ),

                "heading":
                    result.get(
                        "heading"
                    ),

                "prediction":
                    result.get(
                        "prediction"
                    ),

                "model_score":
                    result.get(
                        "model_score"
                    ),

                "num_windows":
                    result.get(
                        "num_windows"
                    ),

                "seed_score":
                    class_scores.get(
                        "Seed",
                        class_scores.get(
                            "seed"
                        ),
                    ),

                "low_score":
                    class_scores.get(
                        "Low",
                        class_scores.get(
                            "low"
                        ),
                    ),

                "medium_score":
                    class_scores.get(
                        "Medium",
                        class_scores.get(
                            "medium"
                        ),
                    ),

                "high_score":
                    class_scores.get(
                        "High",
                        class_scores.get(
                            "high"
                        ),
                    ),

                "text":
                    result.get(
                        "text"
                    ),
            }

            csv_rows.append(
                row
            )

        fieldnames = [

            "index",

            "clause_number",

            "section",

            "heading",

            "prediction",

            "model_score",

            "num_windows",

            "seed_score",

            "low_score",

            "medium_score",

            "high_score",

            "text",

        ]

        with open(
            CSV_OUTPUT,
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )

            writer.writeheader()

            writer.writerows(
                csv_rows
            )

    ##########################################################
    # PRINT SUMMARY
    ##########################################################

    @staticmethod
    def _print_summary(
        summary,
    ):

        counts = summary[
            "prediction_counts"
        ]

        print(
            "\n"
            + "=" * 70
        )

        print(
            "CONTRACT RISK ANALYSIS COMPLETE"
        )

        print(
            "=" * 70
        )

        print(
            f"\nDocument          : "
            f"{summary['file_name']}"
        )

        print(
            f"Extracted units   : "
            f"{summary['total_extracted_units']}"
        )

        print(
            f"Analyzed clauses  : "
            f"{summary['analyzed_clauses']}"
        )

        print(
            f"Skipped clauses   : "
            f"{summary['skipped_clauses']}"
        )

        print(
            "\nRISK DISTRIBUTION"
        )

        print(
            "-" * 40
        )

        print(
            f"Seed    : "
            f"{counts['Seed']}"
        )

        print(
            f"Low     : "
            f"{counts['Low']}"
        )

        print(
            f"Medium  : "
            f"{counts['Medium']}"
        )

        print(
            f"High    : "
            f"{counts['High']}"
        )

        ######################################################
        # HIGH RISK CLAUSES
        ######################################################

        print(
            "\nHIGH-RISK CLAUSES"
        )

        print(
            "-" * 40
        )

        high_risk = summary[
            "high_risk_clauses"
        ]

        if not high_risk:

            print(
                "No clauses were classified "
                "as High."
            )

        else:

            for clause in high_risk:

                print(
                    f"\n"
                    f"{clause['clause_number']} "
                    f"- "
                    f"{clause['heading']}"
                )

                score = clause.get(
                    "model_score"
                )

                if score is not None:

                    try:

                        score = float(
                            score
                        )

                        if score <= 1:

                            score *= 100

                        print(
                            f"Model score: "
                            f"{score:.2f}%"
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):

                        pass

                print(
                    clause[
                        "text"
                    ]
                )

        ######################################################
        # FILES
        ######################################################

        print(
            "\n"
            + "=" * 70
        )

        print(
            "GENERATED FILES"
        )

        print(
            "=" * 70
        )

        print(
            f"\n{CSV_OUTPUT}"
        )

        print(
            JSON_OUTPUT
        )

        print(
            SUMMARY_OUTPUT
        )

        print()


##############################################################
# MAIN: shared Ingestion Pipeline 2 coordinator
##############################################################

if __name__ == "__main__":
    from agents.contract_coordinator import run_cli

    try:
        run_cli()
    except KeyboardInterrupt:
        print("\nAnalysis cancelled.")
