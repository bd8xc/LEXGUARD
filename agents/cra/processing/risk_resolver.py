from typing import Dict, List, Optional


class RiskResolver:
    """
    Combines the LegalBERT prediction with deterministic
    legal-risk validator findings.

    IMPORTANT:
    'Seed' is treated as a model baseline/original-pattern class,
    NOT as a guarantee that the clause is legally safe.
    """

    RISK_ORDER = {
        "Seed": 0,
        "Low": 1,
        "Medium": 2,
        "High": 3,
    }

    DISPLAY_NAMES = {
        "Seed": "Baseline",
        "Low": "Low",
        "Medium": "Medium",
        "High": "High",
    }

    def resolve(
        self,
        model_prediction: str,
        model_score: float,
        findings: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Resolve ML output and deterministic rule findings.

        Parameters
        ----------
        model_prediction:
            Seed / Low / Medium / High

        model_score:
            Model softmax score.
            Can be either:
                0.9963
            or:
                99.63

        findings:
            Output from LegalRiskValidator.validate()

        Returns
        -------
        Dict containing the final hybrid decision.
        """

        findings = findings or []

        model_prediction = self._normalize_risk(
            model_prediction
        )

        model_score = self._normalize_score(
            model_score
        )

        highest_rule_risk = self._highest_rule_risk(
            findings
        )

        # -----------------------------------------------------
        # CASE 1
        # No deterministic rule triggered
        # -----------------------------------------------------

        if highest_rule_risk is None:

            return {
                "final_risk": model_prediction,
                "display_risk": self.DISPLAY_NAMES[
                    model_prediction
                ],
                "decision_source": "Model",
                "model_prediction": model_prediction,
                "model_display": self.DISPLAY_NAMES[
                    model_prediction
                ],
                "model_score": model_score,
                "rule_risk": None,
                "rule_override": False,
                "agreement": None,
                "review_recommended": (
                    model_prediction == "Seed"
                ),
                "findings": findings,
                "explanation": self._no_rule_explanation(
                    model_prediction
                ),
            }

        # -----------------------------------------------------
        # CASE 2
        # Model predicts Seed but explicit rule finds risk
        # -----------------------------------------------------

        if (
            model_prediction == "Seed"
            and highest_rule_risk != "Seed"
        ):

            return {
                "final_risk": highest_rule_risk,
                "display_risk": self.DISPLAY_NAMES[
                    highest_rule_risk
                ],
                "decision_source": "Rule Override",
                "model_prediction": model_prediction,
                "model_display": "Baseline",
                "model_score": model_score,
                "rule_risk": highest_rule_risk,
                "rule_override": True,
                "agreement": False,
                "review_recommended": (
                    highest_rule_risk in {
                        "Medium",
                        "High",
                    }
                ),
                "findings": findings,
                "explanation": (
                    "The model classified the clause as "
                    "Baseline/Seed, but an explicit legal-risk "
                    f"rule detected {highest_rule_risk.lower()} "
                    "risk. The deterministic finding takes "
                    "precedence for the final risk result."
                ),
            }

        # -----------------------------------------------------
        # CASE 3
        # Model and rules agree
        # -----------------------------------------------------

        if model_prediction == highest_rule_risk:

            return {
                "final_risk": model_prediction,
                "display_risk": self.DISPLAY_NAMES[
                    model_prediction
                ],
                "decision_source": "Model + Rule Agreement",
                "model_prediction": model_prediction,
                "model_display": self.DISPLAY_NAMES[
                    model_prediction
                ],
                "model_score": model_score,
                "rule_risk": highest_rule_risk,
                "rule_override": False,
                "agreement": True,
                "review_recommended": (
                    model_prediction in {
                        "Medium",
                        "High",
                    }
                ),
                "findings": findings,
                "explanation": (
                    "The LegalBERT prediction and deterministic "
                    "legal-risk rules agree on the risk level."
                ),
            }

        # -----------------------------------------------------
        # CASE 4
        # Rule detects more severe risk than model
        # -----------------------------------------------------

        if (
            self.RISK_ORDER[highest_rule_risk]
            > self.RISK_ORDER[model_prediction]
        ):

            return {
                "final_risk": highest_rule_risk,
                "display_risk": self.DISPLAY_NAMES[
                    highest_rule_risk
                ],
                "decision_source": "Rule Escalation",
                "model_prediction": model_prediction,
                "model_display": self.DISPLAY_NAMES[
                    model_prediction
                ],
                "model_score": model_score,
                "rule_risk": highest_rule_risk,
                "rule_override": True,
                "agreement": False,
                "review_recommended": (
                    highest_rule_risk in {
                        "Medium",
                        "High",
                    }
                ),
                "findings": findings,
                "explanation": (
                    f"The model predicted {model_prediction}, "
                    "but deterministic legal-risk analysis "
                    f"identified a more severe "
                    f"{highest_rule_risk} risk pattern."
                ),
            }

        # -----------------------------------------------------
        # CASE 5
        # Model predicts more severe risk than rules
        #
        # IMPORTANT:
        # Do NOT downgrade automatically.
        # The rules are incomplete and only cover selected
        # explicit patterns.
        # -----------------------------------------------------

        return {
            "final_risk": model_prediction,
            "display_risk": self.DISPLAY_NAMES[
                model_prediction
            ],
            "decision_source": "Model Retained",
            "model_prediction": model_prediction,
            "model_display": self.DISPLAY_NAMES[
                model_prediction
            ],
            "model_score": model_score,
            "rule_risk": highest_rule_risk,
            "rule_override": False,
            "agreement": False,
            "review_recommended": True,
            "findings": findings,
            "explanation": (
                f"The model predicted {model_prediction}, while "
                f"the strongest deterministic rule indicated "
                f"{highest_rule_risk}. The model result was "
                "retained because the rule layer is not designed "
                "to automatically downgrade ML predictions."
            ),
        }

    # =========================================================
    # HELPERS
    # =========================================================

    def _highest_rule_risk(
        self,
        findings: List[Dict],
    ) -> Optional[str]:

        valid_risks = []

        for finding in findings:

            risk = finding.get("risk")

            if risk in self.RISK_ORDER:
                valid_risks.append(risk)

        if not valid_risks:
            return None

        return max(
            valid_risks,
            key=lambda risk: self.RISK_ORDER[risk],
        )

    def _normalize_risk(
        self,
        risk: str,
    ) -> str:

        if not isinstance(risk, str):
            raise ValueError(
                "model_prediction must be a string."
            )

        lookup = {
            "seed": "Seed",
            "baseline": "Seed",
            "low": "Low",
            "medium": "Medium",
            "high": "High",
        }

        normalized = lookup.get(
            risk.strip().lower()
        )

        if normalized is None:

            raise ValueError(
                f"Unknown risk label: {risk}"
            )

        return normalized

    @staticmethod
    def _normalize_score(
        score: float,
    ) -> float:

        score = float(score)

        # If supplied as percentage, convert to probability.
        if score > 1.0:
            score = score / 100.0

        return max(
            0.0,
            min(score, 1.0),
        )

    @staticmethod
    def _no_rule_explanation(
        model_prediction: str,
    ) -> str:

        if model_prediction == "Seed":

            return (
                "The model classified the clause as "
                "Baseline/Seed and no deterministic rule "
                "triggered. Baseline does not necessarily mean "
                "risk-free; it indicates that no currently "
                "implemented explicit rule detected a known "
                "risk pattern."
            )

        return (
            f"The model classified the clause as "
            f"{model_prediction}. No currently implemented "
            "deterministic legal-risk rule was triggered."
        )


# =============================================================
# STANDALONE TEST
# =============================================================

if __name__ == "__main__":

    from processing.risk_validator import (
        LegalRiskValidator,
    )

    validator = LegalRiskValidator()

    resolver = RiskResolver()

    tests = [

        {
            "name": (
                "Seed model prediction but dangerous "
                "termination rule"
            ),
            "clause": (
                "The Supplier may terminate this Agreement "
                "at any time without cause and without "
                "providing prior notice to the Customer."
            ),
            "model_prediction": "Seed",
            "model_score": 0.9963,
        },

        {
            "name": (
                "High model prediction and uncapped indemnity"
            ),
            "clause": (
                "The Supplier shall indemnify and hold harmless "
                "the Customer against all claims, damages, "
                "losses, liabilities and expenses arising "
                "under this Agreement without limitation "
                "or monetary cap."
            ),
            "model_prediction": "High",
            "model_score": 0.9962,
        },

        {
            "name": (
                "Seed model prediction with protected "
                "liability clause"
            ),
            "clause": (
                "Neither party shall be liable for indirect "
                "or consequential damages, and each party's "
                "aggregate liability shall not exceed the "
                "fees paid under this Agreement during the "
                "preceding twelve months."
            ),
            "model_prediction": "Seed",
            "model_score": 0.9986,
        },

        {
            "name": (
                "Model High but only Low deterministic rule"
            ),
            "clause": (
                "Either party may terminate this Agreement "
                "for material breach if the breaching party "
                "fails to cure such breach within thirty days "
                "after receiving written notice."
            ),
            "model_prediction": "High",
            "model_score": 0.85,
        },

    ]

    for index, test in enumerate(
        tests,
        start=1,
    ):

        print(
            "\n"
            + "=" * 80
        )

        print(
            f"RESOLVER TEST {index}"
        )

        print(
            "=" * 80
        )

        print(
            f"\nScenario : {test['name']}"
        )

        findings = validator.validate(
            test["clause"]
        )

        result = resolver.resolve(
            model_prediction=(
                test["model_prediction"]
            ),
            model_score=(
                test["model_score"]
            ),
            findings=findings,
        )

        print(
            f"\nModel prediction : "
            f"{result['model_display']}"
        )

        print(
            f"Model score      : "
            f"{result['model_score'] * 100:.2f}%"
        )

        print(
            f"Rule risk        : "
            f"{result['rule_risk']}"
        )

        print(
            f"Final risk       : "
            f"{result['display_risk']}"
        )

        print(
            f"Decision source  : "
            f"{result['decision_source']}"
        )

        print(
            f"Rule override    : "
            f"{result['rule_override']}"
        )

        print(
            f"Review required  : "
            f"{result['review_recommended']}"
        )

        print(
            "\nExplanation:"
        )

        print(
            result["explanation"]
        )

        if result["findings"]:

            print(
                "\nRule findings:"
            )

            for finding in result["findings"]:

                print(
                    f"  - [{finding['risk']}] "
                    f"{finding['rule']}"
                )

                print(
                    f"    {finding['reason']}"
                )