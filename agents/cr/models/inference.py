import os

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer

from models.config import Config
from models.sliding_legalbert import SlidingWindowLegalBERT

from processing.risk_validator import LegalRiskValidator
from processing.risk_resolver import RiskResolver


class ContractRiskPredictor:
    """
    Inference wrapper for the trained Sliding-Window LegalBERT model.

    Supports two prediction modes:

    1. predict(text)
       Raw LegalBERT model prediction.

    2. predict_hybrid(text)
       LegalBERT + deterministic legal-risk validator
       + risk resolver.

    IMPORTANT:
    Softmax scores are raw model outputs and are not
    calibrated probabilities.

    IMPORTANT:
    The model class "Seed" represents the dataset's
    baseline/original-pattern class. It must not be
    interpreted as automatically meaning "safe".
    """

    LABEL_NAMES = [
        "Seed",
        "Low",
        "Medium",
        "High",
    ]

    def __init__(
        self,
        checkpoint_path=None,
        device=None,
    ):

        self.cfg = Config()

        ######################################################
        # DEVICE
        ######################################################

        if device is None:
            self.device = self.cfg.device
        else:
            self.device = torch.device(device)

        ######################################################
        # CHECKPOINT
        ######################################################

        if checkpoint_path is None:
            checkpoint_path = self.cfg.checkpoint_path

        self.checkpoint_path = checkpoint_path

        if not os.path.exists(self.checkpoint_path):

            raise FileNotFoundError(
                f"Checkpoint not found: "
                f"{self.checkpoint_path}"
            )

        print(
            f"Using device : {self.device}"
        )

        ######################################################
        # TOKENIZER
        ######################################################

        print(
            "Loading LegalBERT tokenizer..."
        )

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.cfg.model_name
        )

        ######################################################
        # MODEL
        ######################################################

        print(
            "Loading SlidingWindowLegalBERT..."
        )

        self.model = SlidingWindowLegalBERT(
            model_name=self.cfg.model_name,
            num_classes=self.cfg.num_classes,
            dropout=self.cfg.dropout,
        )

        ######################################################
        # LOAD CHECKPOINT
        ######################################################

        checkpoint = torch.load(
            self.checkpoint_path,
            map_location=self.device,
            weights_only=False,
        )

        if (
            isinstance(checkpoint, dict)
            and "model_state_dict" in checkpoint
        ):

            self.model.load_state_dict(
                checkpoint["model_state_dict"]
            )

        else:

            self.model.load_state_dict(
                checkpoint
            )

        self.model.to(
            self.device
        )

        self.model.eval()

        ######################################################
        # HYBRID RISK COMPONENTS
        ######################################################

        self.validator = LegalRiskValidator()

        self.resolver = RiskResolver()

        print(
            "Model loaded successfully."
        )

        print(
            "Hybrid legal-risk validator ready."
        )

    ##########################################################
    # TOKENIZE INTO SLIDING WINDOWS
    ##########################################################

    def _tokenize(self, text):

        if not isinstance(text, str):

            raise TypeError(
                "Input text must be a string."
            )

        text = text.strip()

        if not text:

            raise ValueError(
                "Input text cannot be empty."
            )

        encoding = self.tokenizer(
            text,
            truncation=True,
            max_length=self.cfg.max_length,
            stride=self.cfg.stride,
            return_overflowing_tokens=True,
            padding="max_length",
            return_tensors="pt",
        )

        input_ids = encoding[
            "input_ids"
        ]

        attention_mask = encoding[
            "attention_mask"
        ]

        return (
            input_ids,
            attention_mask,
        )

    ##########################################################
    # RAW LEGALBERT PREDICTION
    ##########################################################

    def predict(self, text):
        """
        Run raw LegalBERT inference.

        This method is intentionally preserved as the
        model-only prediction API.

        Existing evaluation and pipeline code can continue
        using this method without being affected by the
        deterministic rule layer.
        """

        input_ids, attention_mask = (
            self._tokenize(text)
        )

        ######################################################
        # NUMBER OF WINDOWS
        ######################################################

        num_windows = input_ids.shape[0]

        ######################################################
        # MOVE TO DEVICE
        ######################################################

        input_ids = input_ids.to(
            self.device
        )

        attention_mask = attention_mask.to(
            self.device
        )

        ######################################################
        # WINDOW COUNTS
        ######################################################

        window_counts = torch.tensor(
            [num_windows],
            dtype=torch.long,
        )

        ######################################################
        # INFERENCE
        ######################################################

        with torch.no_grad():

            logits = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                window_counts=window_counts,
            )

            probabilities = F.softmax(
                logits,
                dim=1,
            )

        ######################################################
        # EXTRACT SCORES
        ######################################################

        probabilities = (
            probabilities
            .squeeze(0)
            .cpu()
            .numpy()
        )

        predicted_id = int(
            probabilities.argmax()
        )

        predicted_label = (
            self.LABEL_NAMES[
                predicted_id
            ]
        )

        model_score = float(
            probabilities[
                predicted_id
            ]
        )

        class_scores = {

            label:
                float(
                    probabilities[index]
                )

            for index, label
            in enumerate(
                self.LABEL_NAMES
            )
        }

        ######################################################
        # RETURN RAW MODEL RESULT
        ######################################################

        return {

            "prediction":
                predicted_label,

            "prediction_id":
                predicted_id,

            "model_score":
                model_score,

            "class_scores":
                class_scores,

            "num_windows":
                int(
                    num_windows
                ),
        }

    ##########################################################
    # HYBRID PREDICTION
    ##########################################################

    def predict_hybrid(self, text):
        """
        Run the complete hybrid risk pipeline:

            LegalBERT
                +
            LegalRiskValidator
                ↓
            RiskResolver
                ↓
            Final risk result

        Returns both the original ML prediction and the
        final resolved risk classification.
        """

        ######################################################
        # 1. RAW MODEL PREDICTION
        ######################################################

        model_result = self.predict(
            text
        )

        ######################################################
        # 2. DETERMINISTIC LEGAL-RISK VALIDATION
        ######################################################

        findings = self.validator.validate(
            text
        )

        ######################################################
        # 3. RESOLVE MODEL + RULE FINDINGS
        ######################################################

        resolved = self.resolver.resolve(

            model_prediction=(
                model_result[
                    "prediction"
                ]
            ),

            model_score=(
                model_result[
                    "model_score"
                ]
            ),

            findings=findings,
        )

        ######################################################
        # 4. BUILD COMPLETE RESULT
        ######################################################

        return {

            # Final hybrid decision
            "final_risk":
                resolved[
                    "final_risk"
                ],

            "display_risk":
                resolved[
                    "display_risk"
                ],

            "decision_source":
                resolved[
                    "decision_source"
                ],

            "review_recommended":
                resolved[
                    "review_recommended"
                ],

            "rule_override":
                resolved[
                    "rule_override"
                ],

            "agreement":
                resolved[
                    "agreement"
                ],

            "explanation":
                resolved[
                    "explanation"
                ],

            # Original LegalBERT result
            "model_prediction":
                model_result[
                    "prediction"
                ],

            "model_display":
                resolved[
                    "model_display"
                ],

            "model_score":
                model_result[
                    "model_score"
                ],

            "class_scores":
                model_result[
                    "class_scores"
                ],

            "num_windows":
                model_result[
                    "num_windows"
                ],

            # Rule layer
            "rule_risk":
                resolved[
                    "rule_risk"
                ],

            "findings":
                findings,
        }


##############################################################
# COMMAND-LINE HYBRID TEST
##############################################################

if __name__ == "__main__":

    predictor = ContractRiskPredictor()

    print(
        "\n"
        + "=" * 70
    )

    print(
        "HYBRID CONTRACT RISK PREDICTION"
    )

    print(
        "=" * 70
    )

    print(
        "\nLegalBERT + Legal Risk Validator + Risk Resolver"
    )

    while True:

        print(
            "\nPaste a legal clause."
        )

        print(
            "Type 'quit' to exit.\n"
        )

        text = input(
            "Clause: "
        ).strip()

        if text.lower() in {
            "quit",
            "exit",
            "q",
        }:

            print(
                "\nExiting."
            )

            break

        if not text:

            print(
                "Please enter some text."
            )

            continue

        try:

            result = predictor.predict_hybrid(
                text
            )

            ##################################################
            # MODEL ANALYSIS
            ##################################################

            print(
                "\n"
                + "=" * 70
            )

            print(
                "MODEL ANALYSIS"
            )

            print(
                "=" * 70
            )

            print(
                f"Prediction      : "
                f"{result['model_display']}"
            )

            if (
                result["model_prediction"]
                == "Seed"
            ):

                print(
                    "Internal class  : Seed"
                )

            print(
                f"Model score     : "
                f"{result['model_score'] * 100:.2f}%"
            )

            print(
                f"Windows         : "
                f"{result['num_windows']}"
            )

            print(
                "\nClass scores:"
            )

            for (
                label,
                score,
            ) in result[
                "class_scores"
            ].items():

                display_label = (
                    "Baseline"
                    if label == "Seed"
                    else label
                )

                print(
                    f"{display_label:<10}: "
                    f"{score * 100:.2f}%"
                )

            ##################################################
            # RULE ANALYSIS
            ##################################################

            print(
                "\n"
                + "=" * 70
            )

            print(
                "RULE ANALYSIS"
            )

            print(
                "=" * 70
            )

            if not result["findings"]:

                print(
                    "\nNo deterministic legal-risk "
                    "rules triggered."
                )

            else:

                print(
                    f"\nHighest rule risk : "
                    f"{result['rule_risk']}"
                )

                for index, finding in enumerate(
                    result["findings"],
                    start=1,
                ):

                    print(
                        "\n"
                        + "-" * 70
                    )

                    print(
                        f"Finding {index}"
                    )

                    print(
                        f"Rule   : "
                        f"{finding['rule']}"
                    )

                    print(
                        f"Risk   : "
                        f"{finding['risk']}"
                    )

                    print(
                        f"Reason : "
                        f"{finding['reason']}"
                    )

                    if finding[
                        "matched_text"
                    ]:

                        print(
                            f"Match  : "
                            f"{finding['matched_text']}"
                        )

            ##################################################
            # FINAL HYBRID DECISION
            ##################################################

            print(
                "\n"
                + "=" * 70
            )

            print(
                "FINAL HYBRID DECISION"
            )

            print(
                "=" * 70
            )

            print(
                f"\nFinal risk      : "
                f"{result['display_risk'].upper()}"
            )

            print(
                f"Decision source : "
                f"{result['decision_source']}"
            )

            print(
                f"Rule override   : "
                f"{'Yes' if result['rule_override'] else 'No'}"
            )

            print(
                f"Review required : "
                f"{'Yes' if result['review_recommended'] else 'No'}"
            )

            print(
                "\nExplanation:"
            )

            print(
                result[
                    "explanation"
                ]
            )

            ##################################################
            # WARNING
            ##################################################

            print(
                "\n"
                + "-" * 70
            )

            print(
                "Note: Model scores are raw softmax outputs "
                "and are not calibrated probabilities."
            )

            print(
                "Baseline/Seed does not automatically mean "
                "that a clause is risk-free."
            )

            print(
                "-" * 70
            )

        except Exception as error:

            print(
                f"\nPrediction failed: "
                f"{error}"
            )