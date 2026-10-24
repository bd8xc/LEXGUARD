import re
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class RiskFinding:
    """
    Represents one deterministic legal-risk finding.
    """

    rule: str
    risk: str
    reason: str
    matched_text: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class LegalRiskValidator:
    """
    Rule-based legal risk validator.

    This module does NOT replace the LegalBERT model.

    Its purpose is to detect explicit legal-risk patterns that may be
    missed by the ML model, especially when the model predicts Seed
    for clauses containing clearly risky language.
    """

    RISK_ORDER = {
        "Seed": 0,
        "Low": 1,
        "Medium": 2,
        "High": 3,
    }

    def validate(self, text: str) -> List[Dict]:
        """
        Run all legal-risk rules against a clause.

        Parameters
        ----------
        text : str
            Legal clause text.

        Returns
        -------
        List[Dict]
            Structured risk findings.
        """

        if not text or not text.strip():
            return []

        text = self._normalize(text)

        findings: List[RiskFinding] = []

        findings.extend(self._check_termination(text))
        findings.extend(self._check_indemnity(text))
        findings.extend(self._check_liability(text))
        findings.extend(self._check_intellectual_property(text))
        findings.extend(self._check_confidentiality(text))
        findings.extend(self._check_payment_and_remedies(text))

        findings = self._remove_duplicates(findings)

        return [finding.to_dict() for finding in findings]

    # =========================================================
    # TERMINATION
    # =========================================================

    def _check_termination(self, text: str) -> List[RiskFinding]:

        findings = []

        if not self._contains_any(
            text,
            [
                r"\bterminate\b",
                r"\btermination\b",
            ],
        ):
            return findings

        unilateral_party = self._contains_any(
            text,
            [
                r"\bthe supplier may terminate\b",
                r"\bthe customer may terminate\b",
                r"\bthe vendor may terminate\b",
                r"\bthe company may terminate\b",
                r"\bone party may terminate\b",
            ],
        )

        mutual_right = self._contains_any(
            text,
            [
                r"\beither party may terminate\b",
                r"\beach party may terminate\b",
                r"\bthe parties may terminate\b",
            ],
        )

        without_cause = self._contains_any(
            text,
            [
                r"\bwithout cause\b",
                r"\bfor any reason\b",
                r"\bat its sole discretion\b",
                r"\bat any time for convenience\b",
            ],
        )

        without_notice = self._contains_any(
            text,
            [
                r"\bwithout notice\b",
                r"\bwithout prior notice\b",
                r"\bwithout providing prior notice\b",
                r"\bimmediately without notice\b",
            ],
        )

        cure_period = self._contains_any(
            text,
            [
                r"\bcure\b",
                r"\bremedy the breach\b",
                r"\bremedied within\b",
            ],
        )

        material_breach = bool(
            re.search(r"\bmaterial breach\b", text)
        )

        if unilateral_party and without_cause and without_notice:

            findings.append(
                RiskFinding(
                    rule="UNILATERAL_TERMINATION_NO_CAUSE_NO_NOTICE",
                    risk="High",
                    reason=(
                        "One party appears able to terminate the agreement "
                        "without cause and without prior notice."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,60}terminate.{0,120}",
                        ],
                    ),
                )
            )

        elif unilateral_party and without_notice:

            findings.append(
                RiskFinding(
                    rule="UNILATERAL_TERMINATION_NO_NOTICE",
                    risk="High",
                    reason=(
                        "One party appears to have a unilateral termination "
                        "right without adequate prior notice."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,60}terminate.{0,120}",
                        ],
                    ),
                )
            )

        elif unilateral_party and without_cause:

            findings.append(
                RiskFinding(
                    rule="UNILATERAL_TERMINATION_WITHOUT_CAUSE",
                    risk="Medium",
                    reason=(
                        "One party appears able to terminate without cause, "
                        "creating asymmetric termination exposure."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,60}terminate.{0,120}",
                        ],
                    ),
                )
            )

        if material_breach and cure_period:

            findings.append(
                RiskFinding(
                    rule="TERMINATION_WITH_CURE_PERIOD",
                    risk="Low",
                    reason=(
                        "Termination for material breach includes an "
                        "opportunity to cure the breach."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,60}material breach.{0,150}",
                        ],
                    ),
                )
            )

        if mutual_right and not without_notice and not without_cause:

            findings.append(
                RiskFinding(
                    rule="MUTUAL_TERMINATION_RIGHT",
                    risk="Low",
                    reason=(
                        "The termination right appears to apply mutually "
                        "rather than exclusively to one party."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,40}either party may terminate.{0,120}",
                        ],
                    ),
                )
            )

        return findings

    # =========================================================
    # INDEMNIFICATION
    # =========================================================

    def _check_indemnity(self, text: str) -> List[RiskFinding]:

        findings = []

        if not self._contains_any(
            text,
            [
                r"\bindemnify\b",
                r"\bindemnification\b",
                r"\bhold harmless\b",
            ],
        ):
            return findings

        unlimited = self._contains_any(
            text,
            [
                r"\bwithout limitation\b",
                r"\bwithout any limitation\b",
                r"\bwithout monetary cap\b",
                r"\bwithout any monetary cap\b",
                r"\buncapped\b",
                r"\bno cap\b",
                r"\bunlimited liability\b",
            ],
        )

        broad_losses = self._contains_any(
            text,
            [
                r"\ball losses\b",
                r"\ball claims\b",
                r"\ball damages\b",
                r"\ball liabilities\b",
                r"\ball costs\b",
                r"\ball expenses\b",
            ],
        )

        if unlimited:

            findings.append(
                RiskFinding(
                    rule="UNCAPPED_INDEMNITY",
                    risk="High",
                    reason=(
                        "The indemnification obligation appears unlimited "
                        "or not subject to a monetary cap."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,80}(without limitation|uncapped|no cap).{0,80}",
                        ],
                    ),
                )
            )

        elif broad_losses:

            findings.append(
                RiskFinding(
                    rule="BROAD_INDEMNITY",
                    risk="Medium",
                    reason=(
                        "The indemnification obligation uses broad loss or "
                        "claim language that may create significant exposure."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,80}indemnif.{0,180}",
                        ],
                    ),
                )
            )

        return findings

    # =========================================================
    # LIMITATION OF LIABILITY
    # =========================================================

    def _check_liability(self, text: str) -> List[RiskFinding]:

        findings = []

        if not self._contains_any(
            text,
            [
                r"\bliability\b",
                r"\bliable\b",
            ],
        ):
            return findings

        uncapped = self._contains_any(
            text,
            [
                r"\bwithout limitation\b",
                r"\bwithout any limitation\b",
                r"\bwithout monetary cap\b",
                r"\bwithout any monetary cap\b",
                r"\buncapped\b",
                r"\bno cap\b",
                r"\bno limitation of liability\b",
                r"\bunlimited liability\b",
            ],
        )

        has_cap = self._contains_any(
            text,
            [
                r"\bshall not exceed\b",
                r"\baggregate liability.{0,80}fees paid\b",
                r"\bliability cap\b",
                r"\blimited to the fees\b",
            ],
        )

        excludes_consequential = self._contains_any(
            text,
            [
                r"\bnot liable for indirect\b",
                r"\bnot be liable for indirect\b",
                r"\bconsequential damages\b",
            ],
        )

        if uncapped:

            findings.append(
                RiskFinding(
                    rule="UNCAPPED_LIABILITY",
                    risk="High",
                    reason=(
                        "The clause appears to impose liability without "
                        "a monetary or contractual cap."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,100}(without limitation|uncapped|no cap).{0,100}",
                        ],
                    ),
                )
            )

        elif has_cap:

            findings.append(
                RiskFinding(
                    rule="LIABILITY_CAP_PRESENT",
                    risk="Low",
                    reason=(
                        "The clause contains an express limitation or cap "
                        "on aggregate liability."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,100}(shall not exceed|liability cap|limited to).{0,120}",
                        ],
                    ),
                )
            )

        if excludes_consequential:

            findings.append(
                RiskFinding(
                    rule="CONSEQUENTIAL_DAMAGE_EXCLUSION",
                    risk="Low",
                    reason=(
                        "The clause limits exposure to indirect or "
                        "consequential damages."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,100}(indirect|consequential damages).{0,100}",
                        ],
                    ),
                )
            )

        return findings

    # =========================================================
    # INTELLECTUAL PROPERTY
    # =========================================================

    def _check_intellectual_property(
        self,
        text: str,
    ) -> List[RiskFinding]:

        findings = []

        if not self._contains_any(
            text,
            [
                r"\bintellectual property\b",
                r"\bbackground ip\b",
                r"\bpre-existing\b",
                r"\bownership\b",
                r"\bassign\b",
                r"\blicense\b",
            ],
        ):
            return findings

        transfers_preexisting_ip = self._contains_any(
            text,
            [
                r"\bassign.{0,120}pre-existing\b",
                r"\bassign.{0,120}background ip\b",
                r"\btransfer.{0,120}pre-existing\b",
                r"\btransfer.{0,120}background ip\b",
                r"\ball intellectual property.{0,100}customer\b",
                r"\ball intellectual property.{0,100}client\b",
            ],
        )

        retains_preexisting_ip = self._contains_any(
            text,
            [
                r"\bretains ownership\b",
                r"\bretain ownership\b",
                r"\bpre-existing intellectual property.{0,120}remain\b",
                r"\bbackground ip.{0,120}remain\b",
            ],
        )

        if transfers_preexisting_ip:

            findings.append(
                RiskFinding(
                    rule="TRANSFER_OF_PREEXISTING_IP",
                    risk="High",
                    reason=(
                        "The clause may transfer ownership of pre-existing "
                        "or background intellectual property."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,100}(pre-existing|background ip).{0,150}",
                        ],
                    ),
                )
            )

        elif retains_preexisting_ip:

            findings.append(
                RiskFinding(
                    rule="PREEXISTING_IP_RETAINED",
                    risk="Low",
                    reason=(
                        "The clause appears to preserve ownership of "
                        "pre-existing intellectual property."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,100}(retains ownership|retain ownership).{0,150}",
                        ],
                    ),
                )
            )

        return findings

    # =========================================================
    # CONFIDENTIALITY
    # =========================================================

    def _check_confidentiality(self, text: str) -> List[RiskFinding]:

        findings = []

        if not self._contains_any(
            text,
            [
                r"\bconfidential\b",
                r"\bconfidentiality\b",
            ],
        ):
            return findings

        unilateral = self._contains_any(
            text,
            [
                r"\bonly the supplier\b",
                r"\bonly the customer\b",
                r"\bthe supplier shall keep confidential\b",
                r"\bthe customer shall keep confidential\b",
            ],
        )

        mutual = self._contains_any(
            text,
            [
                r"\beach party shall keep confidential\b",
                r"\bboth parties\b",
                r"\beach party agrees\b",
            ],
        )

        if unilateral:

            findings.append(
                RiskFinding(
                    rule="UNILATERAL_CONFIDENTIALITY",
                    risk="Medium",
                    reason=(
                        "The confidentiality obligation appears to apply "
                        "primarily to one party rather than mutually."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,80}confidential.{0,160}",
                        ],
                    ),
                )
            )

        elif mutual:

            findings.append(
                RiskFinding(
                    rule="MUTUAL_CONFIDENTIALITY",
                    risk="Low",
                    reason=(
                        "The confidentiality obligations appear to apply "
                        "mutually to both parties."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,80}confidential.{0,160}",
                        ],
                    ),
                )
            )

        return findings

    # =========================================================
    # PAYMENT / REMEDIES
    # =========================================================

    def _check_payment_and_remedies(
        self,
        text: str,
    ) -> List[RiskFinding]:

        findings = []

        immediate_suspension = self._contains_any(
            text,
            [
                r"\bimmediately suspend\b",
                r"\bsuspend immediately\b",
                r"\bimmediate suspension\b",
            ],
        )

        late_payment = self._contains_any(
            text,
            [
                r"\blate payment\b",
                r"\boverdue\b",
                r"\bfailure to pay\b",
                r"\bnon-payment\b",
                r"\bunpaid invoice\b",
            ],
        )

        acceleration = self._contains_any(
            text,
            [
                r"\ball remaining fees.{0,80}immediately due\b",
                r"\bremaining contract value.{0,80}due\b",
                r"\baccelerated payment\b",
                r"\bacceleration fee\b",
            ],
        )

        if immediate_suspension and late_payment:

            findings.append(
                RiskFinding(
                    rule="IMMEDIATE_SUSPENSION_FOR_NONPAYMENT",
                    risk="Medium",
                    reason=(
                        "The clause permits immediate suspension for "
                        "late or missed payment."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,100}suspend.{0,180}",
                        ],
                    ),
                )
            )

        if acceleration:

            findings.append(
                RiskFinding(
                    rule="ACCELERATED_REMAINING_FEES",
                    risk="High",
                    reason=(
                        "The clause may accelerate substantial remaining "
                        "contract fees following termination or breach."
                    ),
                    matched_text=self._first_match(
                        text,
                        [
                            r".{0,100}(remaining fees|remaining contract value|acceleration).{0,160}",
                        ],
                    ),
                )
            )

        return findings

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _normalize(text: str) -> str:

        text = text.lower()

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    @staticmethod
    def _contains_any(
        text: str,
        patterns: List[str],
    ) -> bool:

        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        )

    @staticmethod
    def _first_match(
        text: str,
        patterns: List[str],
    ) -> str:

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            if match:
                return match.group(0).strip()

        return ""

    @staticmethod
    def _remove_duplicates(
        findings: List[RiskFinding],
    ) -> List[RiskFinding]:

        seen = set()

        unique = []

        for finding in findings:

            key = (
                finding.rule,
                finding.risk,
            )

            if key not in seen:

                seen.add(key)

                unique.append(finding)

        return unique

    def highest_risk(
        self,
        findings: List[Dict],
    ) -> str:
        """
        Return the highest risk level among findings.
        """

        if not findings:
            return "Seed"

        return max(
            (
                finding["risk"]
                for finding in findings
            ),
            key=lambda risk: self.RISK_ORDER[risk],
        )


# =============================================================
# STANDALONE TEST
# =============================================================

if __name__ == "__main__":

    validator = LegalRiskValidator()

    test_clauses = [

        # Should detect HIGH termination risk
        """
        The Supplier may terminate this Agreement at any time
        without cause and without providing prior notice
        to the Customer.
        """,

        # Should detect LOW / protected termination
        """
        Either party may terminate this Agreement for material
        breach if the breaching party fails to cure such breach
        within thirty days after receiving written notice.
        """,

        # Should detect HIGH uncapped indemnity
        """
        The Supplier shall indemnify and hold harmless the Customer
        against all claims, damages, losses, liabilities and expenses
        arising under this Agreement without limitation or monetary cap.
        """,

        # Should detect LOW liability protection
        """
        Neither party shall be liable for indirect or consequential
        damages, and each party's aggregate liability shall not exceed
        the fees paid under this Agreement during the preceding
        twelve months.
        """,

    ]

    for index, clause in enumerate(
        test_clauses,
        start=1,
    ):

        print("\n" + "=" * 80)

        print(
            f"TEST CLAUSE {index}"
        )

        print("=" * 80)

        clean_clause = " ".join(
            clause.split()
        )

        print("\nCLAUSE:")
        print(clean_clause)

        findings = validator.validate(
            clean_clause
        )

        print("\nFINDINGS:")

        if not findings:

            print(
                "No deterministic risk rules triggered."
            )

        else:

            for finding in findings:

                print(
                    f"\nRule   : {finding['rule']}"
                )

                print(
                    f"Risk   : {finding['risk']}"
                )

                print(
                    f"Reason : {finding['reason']}"
                )

                if finding["matched_text"]:

                    print(
                        f"Match  : {finding['matched_text']}"
                    )

        print(
            "\nHighest rule risk:",
            validator.highest_risk(findings),
        )