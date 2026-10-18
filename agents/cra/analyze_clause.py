from models.inference import (
    ContractRiskPredictor,
)

from rag.legal_rag import (
    IndianLegalRAG,
)

from llm.local_llm import (
    LocalLegalLLM,
)

from reporting.clause_report import generate_pdf_report


class ContractRiskAnalysisSystem:
    """
    End-to-end hybrid contract-risk analysis system.

    Architecture:

        Contract Clause
              |
        +-----+------+
        |            |
        v            v
    LegalBERT    Indian-law RAG
        |            |
        |            v
        |      Retrieved statutory
        |      candidate provisions
        |            |
        +-----+------+
              |
              v
          Local LLM
              |
              v
      Grounded risk analysis

    Responsibilities:

    LegalBERT:
        Produces a learned contractual-risk signal.

    RAG:
        Retrieves candidate statutory context from the
        Indian Contract Act, 1872.

    Local LLM:
        Reasons over the clause, ML signal, and retrieved
        statutory context.

    Important:
        Retrieved law is candidate context and does not
        automatically imply that a provision applies.

        The LegalBERT prediction is an ML risk signal and
        is not itself a legal conclusion.
    """

    def __init__(self):

        print(
            "\n"
            + "=" * 70
        )

        print(
            "INITIALIZING CONTRACT "
            "RISK ANALYSIS SYSTEM"
        )

        print(
            "=" * 70
        )

        ######################################################
        # STAGE 1 — LEGALBERT
        ######################################################

        print(
            "\n[1/3] Loading LegalBERT..."
        )

        self.predictor = (
            ContractRiskPredictor()
        )

        ######################################################
        # STAGE 2 — INDIAN-LAW RAG
        ######################################################

        print(
            "\n[2/3] Loading Indian-law RAG..."
        )

        self.rag = (
            IndianLegalRAG()
        )

        ######################################################
        # STAGE 3 — LOCAL LLM
        ######################################################

        print(
            "\n[3/3] Connecting local LLM..."
        )

        self.llm = (
            LocalLegalLLM()
        )

        # Loaded only when litigation intake is supplied, so the original
        # clause-only API remains usable without the LE dependencies.
        self.litigation_predictor = None

        if not (
            self.llm.check_connection()
        ):

            raise RuntimeError(
                "Ollama is not available. "
                "Make sure Ollama is running "
                "before starting the analysis system."
            )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "SYSTEM READY"
        )

        print(
            "=" * 70
        )

    ##########################################################
    # NORMALIZE RISK LABEL
    ##########################################################

    @staticmethod
    def _normalize_risk_label(
        label,
    ):

        if label is None:

            return ""

        label = (
            str(label)
            .strip()
        )

        # Seed is the internal training label.
        # Display it externally as Baseline.
        if label.lower() == "seed":

            return "Baseline"

        return label

    ##########################################################
    # ANALYZE ONE CLAUSE
    ##########################################################

    def analyze(
        self,
        clause: str,
        litigation_result=None,
        model_result=None,
    ):

        if not isinstance(
            clause,
            str,
        ):

            raise TypeError(
                "Clause must be a string."
            )

        clause = clause.strip()

        if not clause:

            raise ValueError(
                "Clause cannot be empty."
            )

        if litigation_result is not None:
            if not isinstance(litigation_result, dict):
                raise TypeError(
                    "Litigation result must be a dictionary."
                )

        ######################################################
        # STAGE 1 — LEGALBERT
        ######################################################

        if model_result is None:
            model_result = self.predict_model(clause)

        ######################################################
        # STAGE 2 — RAG
        #
        # Keep top_k=5.
        #
        # A broader candidate set is useful because semantic
        # retrieval may rank specialized provisions above a
        # more generally applicable provision.
        #
        # Example:
        #
        # An indemnity clause may retrieve agency-specific
        # indemnity sections before Sections 124 and 125.
        #
        # The LLM receives all five candidates and determines
        # which are actually relevant.
        ######################################################

        print(
            "Retrieving Indian law..."
        )

        retrieved_law = (
            self.rag.retrieve(
                query=clause,
                top_k=5,
            )
        )

        ######################################################
        # STAGE 3 — LOCAL LLM
        ######################################################

        print(
            "Generating grounded analysis..."
        )

        llm_analysis = (
            self.llm.analyze(
                clause=clause,
                model_result=model_result,
                retrieved_law=retrieved_law,
                litigation_result=litigation_result,
            )
        )

        ######################################################
        # DETERMINISTIC AGREEMENT CHECK
        #
        # Do NOT ask the LLM to determine whether:
        #
        #     LegalBERT = High
        #     LLM       = High
        #
        # means agreement.
        #
        # This is deterministic application logic.
        ######################################################

        model_prediction = (
            self._normalize_risk_label(
                model_result.get(
                    "prediction",
                    "",
                )
            )
        )

        llm_prediction = (
            self._normalize_risk_label(
                llm_analysis.get(
                    "assessed_risk",
                    "",
                )
            )
        )

        def normalize_risk(label):

            if not label:
                return ""

            label = (
                label
                .strip()
                .lower()
            )

            if label in {
                "baseline",
                "seed",
            }:
                return "low"

            return label


        normalized_model = normalize_risk(
            model_prediction
        )

        normalized_llm = normalize_risk(
            llm_prediction
        )

        agreement = (

            bool(
                normalized_model
            )

            and

            bool(
                normalized_llm
            )

            and

            normalized_model
            ==
            normalized_llm
        )

        # Override whatever boolean the small LLM generated.
        llm_analysis[
            "agreement_with_model"
        ] = agreement

        ######################################################
        # HUMAN REVIEW SAFETY LOGIC
        #
        # The LLM may recommend human review itself.
        #
        # We additionally require review when:
        #
        # 1. LegalBERT and LLM disagree.
        # 2. Either system assesses High risk.
        # 3. Evidence is insufficient.
        #
        # This is workflow logic, not legal reasoning.
        ######################################################

        llm_review = bool(
            llm_analysis.get(
                "human_review_required",
                False,
            )
        )

        evidence_sufficient = bool(
            llm_analysis.get(
                "evidence_sufficient",
                False,
            )
        )

        high_risk_detected = (

            normalized_model
            == "high"

            or

            normalized_llm
            == "high"
        )

        litigation_risk = ""
        litigation_agreement = True
        if litigation_result is not None:
            litigation_risk = str(
                litigation_result.get("risk_level", "")
            ).strip().lower()
            litigation_agreement = (
                bool(normalized_llm)
                and bool(litigation_risk)
                and normalized_llm == litigation_risk
            )
            llm_analysis["agreement_with_litigation"] = (
                litigation_agreement
            )
            high_risk_detected = (
                high_risk_detected or litigation_risk == "high"
            )

        final_review_required = (

            llm_review

            or

            not agreement

            or

            not litigation_agreement

            or

            high_risk_detected

            or

            not evidence_sufficient
        )

        llm_analysis[
            "human_review_required"
        ] = final_review_required

        ######################################################
        # COMPLETE RESULT
        ######################################################

        return {

            "clause":
                clause,

            "model":
                model_result,

            "retrieved_law":
                retrieved_law,

            "analysis":
                llm_analysis,

            "litigation":
                litigation_result,
        }

    def predict_model(self, clause: str):
        """Return the LegalBERT signal without running RAG or the LLM."""
        if not isinstance(clause, str):
            raise TypeError("Clause must be a string.")
        clause = clause.strip()
        if not clause:
            raise ValueError("Clause cannot be empty.")
        print("\nRunning LegalBERT...")
        return self.predictor.predict(clause)

    def predict_litigation(self, litigation_state):
        """Run the contract-level LE model once for the supplied intake."""
        if self.litigation_predictor is None:
            from litigation_agent.agent import LitigationExposureAgent

            print("Loading Litigation Exposure Agent...")
            self.litigation_predictor = LitigationExposureAgent()

        return self.litigation_predictor.predict_with_explanation(
            litigation_state
        )

    ##########################################################
    # DISPLAY COMPLETE RESULT
    ##########################################################

    @staticmethod
    def print_result(
        result,
    ):

        clause = result[
            "clause"
        ]

        model = result[
            "model"
        ]

        retrieved = result[
            "retrieved_law"
        ]

        analysis = result[
            "analysis"
        ]

        litigation = result.get("litigation")

        ######################################################
        # HEADER
        ######################################################

        print(
            "\n"
            + "=" * 70
        )

        print(
            "CONTRACT RISK & "
            "COMPLIANCE ANALYSIS"
        )

        print(
            "=" * 70
        )

        print(
            "\nCLAUSE:\n"
        )

        print(
            clause
        )

        ######################################################
        # 1. LEGALBERT
        ######################################################

        print(
            "\n"
            + "=" * 70
        )

        print(
            "1. LEGALBERT RISK SIGNAL"
        )

        print(
            "=" * 70
        )

        prediction = (
            model.get(
                "prediction",
                "Unknown",
            )
        )

        display_prediction = (

            "Baseline"

            if str(
                prediction
            ).lower() == "seed"

            else prediction
        )

        model_score = float(
            model.get(
                "model_score",
                0.0,
            )
        )

        print(
            f"\nPrediction  : "
            f"{display_prediction}"
        )

        print(
            f"Model score : "
            f"{model_score * 100:.2f}%"
        )

        ######################################################
        # CLASS SCORES
        ######################################################

        print(
            "\nClass scores:"
        )

        class_scores = (
            model.get(
                "class_scores",
                {},
            )
        )

        for label, score in (
            class_scores.items()
        ):

            display_label = (

                "Baseline"

                if str(
                    label
                ).lower() == "seed"

                else label
            )

            print(
                f"{display_label:<10}: "
                f"{float(score) * 100:.2f}%"
            )

        ######################################################
        # WINDOWS
        ######################################################

        num_windows = (
            model.get(
                "num_windows"
            )
        )

        if num_windows is not None:

            print(
                f"\nWindows     : "
                f"{num_windows}"
            )

        if litigation:
            print("\n" + "=" * 70)
            print("2. LITIGATION EXPOSURE MODEL SIGNAL (DEAL CONTEXT)")
            print("=" * 70)
            print(
                f"\nModel estimate  : "
                f"{litigation.get('litigation_probability', 0.0):.4f}"
            )
            print(
                f"Risk band       : "
                f"{litigation.get('risk_level', 'Unknown')}"
            )
            print(
                f"Model version   : "
                f"{litigation.get('model_fingerprint', 'Unknown')}"
            )
            print("Feature contributions (SHAP):")
            for name, value in litigation.get(
                "shap_explanation", {}
            ).items():
                print(f"- {name}: {value:+.6f}")
            print(
                "Note: this is deal-context exposure for the selected clause. "
                "The model was trained on synthetic data; this is not a "
                "validated real-world probability."
            )

        ######################################################
        # RETRIEVED LAW
        ######################################################

        print(
            "\n"
            + "=" * 70
        )

        print(
            "3. RETRIEVED INDIAN LAW"
        )

        print(
            "=" * 70
        )

        if not retrieved:

            print(
                "\nNo statutory provisions "
                "were retrieved."
            )

        else:

            for item in retrieved:

                print(
                    "\n"
                    + "-" * 70
                )

                rank = (
                    item.get(
                        "rank"
                    )
                )

                if rank is not None:

                    print(
                        f"Rank       : "
                        f"{rank}"
                    )

                print(
                    f"Section    : "
                    f"{item.get('section')}"
                )

                print(
                    f"Heading    : "
                    f"{item.get('heading')}"
                )

                ##################################################
                # RETRIEVAL SCORE
                ##################################################

                score = (
                    item.get(
                        "score"
                    )
                )

                if score is not None:

                    print(
                        f"Similarity : "
                        f"{float(score):.4f}"
                    )

                ##################################################
                # OPTIONAL RERANKER INFORMATION
                #
                # This keeps the display compatible if we later
                # enable cross-encoder reranking.
                ##################################################

                bi_encoder_score = (
                    item.get(
                        "bi_encoder_score"
                    )
                )

                reranker_score = (
                    item.get(
                        "reranker_score"
                    )
                )

                if (
                    bi_encoder_score
                    is not None
                    and
                    score is None
                ):

                    print(
                        f"Bi-encoder : "
                        f"{float(bi_encoder_score):.4f}"
                    )

                if (
                    reranker_score
                    is not None
                ):

                    print(
                        f"Reranker   : "
                        f"{float(reranker_score):.4f}"
                    )

        ######################################################
        # LOCAL LLM ANALYSIS
        ######################################################

        print(
            "\n"
            + "=" * 70
        )

        print(
            "4. COMBINED GROUNDED LLM ANALYSIS"
        )

        print(
            "=" * 70
        )

        assessed_risk = (
            analysis.get(
                "assessed_risk",
                "Unknown",
            )
        )

        agreement = bool(
            analysis.get(
                "agreement_with_model",
                False,
            )
        )

        review = bool(
            analysis.get(
                "human_review_required",
                True,
            )
        )

        evidence = bool(
            analysis.get(
                "evidence_sufficient",
                False,
            )
        )

        print(
            f"\nAssessed risk       : "
            f"{str(assessed_risk).upper()}"
        )

        print(
            f"Agreement with LegalBERT: "
            f"{'YES' if agreement else 'NO'}"
        )

        if "agreement_with_litigation" in analysis:
            print(
                f"Agreement with LE      : "
                f"{'YES' if analysis['agreement_with_litigation'] else 'NO'}"
            )

        print(
            f"Evidence sufficient : "
            f"{'YES' if evidence else 'NO'}"
        )

        print(
            f"Human review        : "
            f"{'REQUIRED' if review else 'NOT REQUIRED'}"
        )

        ######################################################
        # SUMMARY
        ######################################################

        print(
            "\nSummary:"
        )

        print(
            analysis.get(
                "summary",
                "No summary generated.",
            )
        )

        ######################################################
        # RISK REASONING
        ######################################################

        print(
            "\nRisk reasoning:"
        )

        print(
            analysis.get(
                "risk_reasoning",
                "No reasoning generated.",
            )
        )

        ######################################################
        # RELEVANT STATUTORY CONTEXT
        ######################################################

        relevant_sections = (
            analysis.get(
                "relevant_sections",
                [],
            )
        )

        print(
            "\nRelevant statutory context:"
        )

        if relevant_sections:

            for item in relevant_sections:

                section = (
                    item.get(
                        "section",
                        "Unknown",
                    )
                )

                relevance = (
                    item.get(
                        "relevance",
                        "No explanation provided.",
                    )
                )

                print(
                    f"\n- Section "
                    f"{section}: "
                    f"{relevance}"
                )

        else:

            print(
                "\nNo retrieved section was "
                "identified as directly relevant."
            )

        ######################################################
        # WEAK / IRRELEVANT RETRIEVED SECTIONS
        ######################################################

        weak_sections = (
            analysis.get(
                "irrelevant_or_weak_sections",
                [],
            )
        )

        print(
            "\nWeak or irrelevant "
            "retrieved context:"
        )

        if weak_sections:

            for item in weak_sections:

                section = (
                    item.get(
                        "section",
                        "Unknown",
                    )
                )

                reason = (
                    item.get(
                        "reason",
                        "No explanation provided.",
                    )
                )

                print(
                    f"\n- Section "
                    f"{section}: "
                    f"{reason}"
                )

        else:

            print(
                "\nNone explicitly identified."
            )

        ######################################################
        # CONTRACTUAL CONCERN
        ######################################################

        print(
            "\nContractual concern:"
        )

        print(
            analysis.get(
                "contractual_concern",
                "Not identified.",
            )
        )

        ######################################################
        # MITIGATION
        ######################################################

        print(
            "\nSuggested mitigation:"
        )

        print(
            analysis.get(
                "suggested_mitigation",
                (
                    "Manual legal review "
                    "is recommended."
                ),
            )
        )

        ######################################################
        # IMPORTANT INTERPRETATION NOTE
        ######################################################

        print(
            "\n"
            + "=" * 70
        )

        print(
            "INTERPRETATION NOTE"
        )

        print(
            "=" * 70
        )

        print(
            "\nThe LegalBERT result is a learned "
            "contractual-risk signal."
        )

        print(
            "Retrieved statutory provisions are "
            "candidate legal context and do not "
            "automatically imply a statutory violation."
        )

        print(
            "The local LLM evaluates the supplied "
            "evidence and identifies which retrieved "
            "provisions appear relevant."
        )

        ######################################################
        # DISCLAIMER
        ######################################################

        print(
            "\n"
            + "=" * 70
        )

        print(
            "Automated decision-support analysis. "
            "Not a substitute for professional "
            "legal advice."
        )

        print(
            "=" * 70
        )


##############################################################
# COMMAND-LINE APPLICATION
##############################################################

if __name__ == "__main__":

    try:

        system = (
            ContractRiskAnalysisSystem()
        )

    except Exception as error:

        print(
            "\n"
            + "=" * 70
        )

        print(
            "SYSTEM INITIALIZATION FAILED"
        )

        print(
            "=" * 70
        )

        print(
            f"\n{error}"
        )

        raise SystemExit(
            1
        )

    ##########################################################
    # INTERACTIVE LOOP
    ##########################################################

    while True:

        print(
            "\nPaste a legal clause."
        )

        print(
            "Type 'quit' to exit.\n"
        )

        try:

            clause = input(
                "Clause: "
            ).strip()

        except (
            KeyboardInterrupt,
            EOFError,
        ):

            print(
                "\n\nExiting."
            )

            break

        if clause.lower() in {
            "quit",
            "exit",
            "q",
        }:

            print(
                "\nExiting."
            )

            break

        if not clause:

            print(
                "\nPlease enter a legal clause."
            )

            continue

        try:

            result = (
                system.analyze(
                    clause
                )
            )

            system.print_result(
                result
            )

            # ----------------------------
            # GENERATE PDF HERE
            # ----------------------------

            pdf_path = generate_pdf_report(
                result
            )

            print("\n" + "=" * 70)
            print("PDF REPORT GENERATED")
            print("=" * 70)
            print(f"Saved to: {pdf_path}")

        except KeyboardInterrupt:

            print(
                "\n\nAnalysis interrupted."
            )

            continue

        except Exception as error:

            print(
                "\n"
                + "=" * 70
            )

            print(
                "ANALYSIS FAILED"
            )

            print(
                "=" * 70
            )

            print(
                f"\n{type(error).__name__}: "
                f"{error}"
            )
            

            print(
                "\nYou can enter another clause "
                "or type 'quit' to exit."
            )
