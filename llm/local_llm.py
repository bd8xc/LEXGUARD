import json
import os
from typing import Dict, List

import requests


class LocalLegalLLM:
    """
    Local LLM reasoning layer for contract-risk analysis.

    The LLM does NOT replace LegalBERT and does NOT independently
    retrieve law.

    It receives:

        1. Original contract clause
        2. LegalBERT risk prediction
        3. Retrieved Indian statutory provisions

    It then produces a grounded explanation.

    Supports local Ollama and OpenAI-compatible chat-completions servers.
    """

    def __init__(
            self,
            model_name=None,
            base_url=None,
            api_style=None,
        ):
        self.model_name = (
            model_name
            or os.getenv("LEXGUARD_LLM_MODEL", "qwen2.5:1.5b")
        )

        self.base_url = (
            (base_url or os.getenv("LEXGUARD_LLM_BASE_URL", "http://localhost:11434"))
            .rstrip("/")
        )

        self.api_style = (
            api_style
            or os.getenv("LEXGUARD_LLM_API_STYLE", "ollama").strip().lower()
        )

        self.api_root = (
            self.base_url
            if self.base_url.endswith("/v1")
            else f"{self.base_url}/v1"
        )

        self.generate_url = (
            f"{self.base_url}/api/generate"
            if self.api_style == "ollama"
            else f"{self.api_root}/chat/completions"
            if self.api_style == "openai_compatible"
            else None
        )

        if self.generate_url is None:
            raise ValueError(
                "LEXGUARD_LLM_API_STYLE must be 'ollama' or 'openai_compatible'."
            )

    ##########################################################
    # CHECK CONNECTION
    ##########################################################

    def check_connection(self):

        try:

            health_url = (
                f"{self.base_url}/api/tags"
                if self.api_style == "ollama"
                else f"{self.api_root}/models"
            )
            api_key = os.getenv("LEXGUARD_LLM_API_KEY")
            headers = (
                {"Authorization": f"Bearer {api_key}"}
                if api_key and self.api_style == "openai_compatible"
                else None
            )
            response = requests.get(
                health_url,
                headers=headers,
                timeout=10,
            )

            response.raise_for_status()

            return True

        except requests.RequestException:

            return False

    ##########################################################
    # FORMAT LEGALBERT RESULT
    ##########################################################

    @staticmethod
    def _format_model_result(
        model_result: Dict,
    ) -> str:

        prediction = (
            model_result.get(
                "prediction",
                "Unknown",
            )
        )

        model_score = float(
            model_result.get(
                "model_score",
                0.0,
            )
        )

        class_scores = (
            model_result.get(
                "class_scores",
                {}
            )
        )

        lines = [

            f"Predicted class: "
            f"{prediction}",

            f"Model score: "
            f"{model_score * 100:.2f}%",

            "Class scores:",
        ]

        for label, score in (
            class_scores.items()
        ):

            display_label = (
                "Baseline"
                if label == "Seed"
                else label
            )

            lines.append(
                f"- {display_label}: "
                f"{float(score) * 100:.2f}%"
            )

        return "\n".join(
            lines
        )

    ##########################################################
    # FORMAT RETRIEVED LAW
    ##########################################################

    @staticmethod
    def _format_legal_context(
        retrieved_law: List[Dict],
    ) -> str:

        if not retrieved_law:

            return (
                "No statutory provisions "
                "were retrieved."
            )

        blocks = []

        for item in retrieved_law:

            section = item.get(
                "section",
                "Unknown",
            )

            heading = item.get(
                "heading",
                "",
            )

            text = item.get(
                "text",
                "",
            )

            score = item.get(
                "score"
            )

            block = [

                (
                    f"SECTION {section}: "
                    f"{heading}"
                ),

            ]

            if score is not None:

                block.append(
                    "Retrieval similarity: "
                    f"{float(score):.4f}"
                )

            block.extend(
                [
                    "Provision:",
                    text,
                ]
            )

            blocks.append(
                "\n".join(
                    block
                )
            )

        return (
            "\n\n"
            "------------------------------"
            "\n\n"
        ).join(
            blocks
        )

    ##########################################################
    # BUILD PROMPT
    ##########################################################

    def _build_prompt(
        self,
        clause: str,
        model_result: Dict,
        retrieved_law: List[Dict],
    ) -> str:

        model_context = (
            self._format_model_result(
                model_result
            )
        )

        legal_context = (
            self._format_legal_context(
                retrieved_law
            )
        )

        prompt = f"""
You are the reasoning component of an automated Indian commercial
contract risk analysis system.

You must analyze the supplied contract clause using ONLY the evidence
provided below.

You are given:

1. The original contract clause.
2. A risk signal produced by a fine-tuned LegalBERT classifier.
3. Candidate statutory provisions retrieved from the Indian Contract
   Act, 1872.

The classifier scores are raw model outputs, not calibrated probabilities
or legal conclusions. "Baseline" describes the training label and must
not be treated as automatically safe.

IMPORTANT RELEVANCE RULES:

- Retrieved statutory provisions are candidate evidence only.
- Do not select a provision merely because it contains words similar
  to the contract clause.
- Compare the actual legal relationship and factual context described
  by each provision with the supplied clause.
- Prefer a general provision that directly defines or governs the
  contractual concept over a specialized provision that applies only
  to a different legal relationship.
- If a provision concerns principal-agent relationships, agency,
  criminal conduct, guarantee, bailment, pledge, or another specialized
  relationship, do not treat it as directly relevant unless that same
  relationship exists in the supplied clause.
- Explicitly place retrieved but inapplicable provisions under
  irrelevant_or_weak_sections.
- Do not claim that a clause violates a statutory provision unless the
  supplied statutory text itself supports that conclusion.
- Distinguish contractual risk from statutory illegality.

============================================================
CONTRACT CLAUSE
============================================================

{clause}

============================================================
LEGALBERT RISK SIGNAL
============================================================

{model_context}

============================================================
RETRIEVED STATUTORY CONTEXT
============================================================

{legal_context}

============================================================
TASK
============================================================

Return ONLY valid JSON using exactly this structure:

{{
    "assessed_risk": "Low | Medium | High",
    "agreement_with_model": true,
    "summary": "Short overall assessment.",
    "risk_reasoning": "Explain the contractual risk based on the clause.",
    "relevant_sections": [
        {{
            "section": "section number",
            "relevance": "Why this retrieved section is relevant."
        }}
    ],
    "irrelevant_or_weak_sections": [
        {{
            "section": "section number",
            "reason": "Why this retrieved section should not be relied upon."
        }}
    ],
    "contractual_concern": "Main contractual concern.",
    "suggested_mitigation": "Possible drafting or review mitigation.",
    "human_review_required": true,
    "evidence_sufficient": true
}}

Do not include markdown.

Do not include text before or after the JSON.
"""

        return prompt.strip()

    ##########################################################
    # ANALYZE
    ##########################################################

    def analyze(
        self,
        clause: str,
        model_result: Dict,
        retrieved_law: List[Dict],
    ) -> Dict:

        clause = clause.strip()

        if not clause:

            raise ValueError(
                "Clause cannot be empty."
            )

        prompt = (
            self._build_prompt(
                clause=clause,
                model_result=model_result,
                retrieved_law=retrieved_law,
            )
        )

        if self.api_style == "ollama":
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
            }
            headers = None
        else:
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            }
            api_key = os.getenv("LEXGUARD_LLM_API_KEY")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

        try:

            response = requests.post(
                self.generate_url,
                json=payload,
                headers=headers,
                timeout=180,
            )

            response.raise_for_status()

        except requests.RequestException as error:

            raise RuntimeError(
                "Could not communicate with the configured LLM server. "
                "Check LEXGUARD_LLM_BASE_URL, API style, and model availability."
            ) from error

        data = response.json()

        if self.api_style == "ollama":
            raw_response = data.get("response", "").strip()
        else:
            choices = data.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            raw_response = str(message.get("content") or "").strip()

        if not raw_response:

            raise RuntimeError(
                "Local LLM returned an "
                "empty response."
            )

        ######################################################
        # PARSE JSON
        ######################################################

        try:

            analysis = json.loads(
                raw_response
            )

        except json.JSONDecodeError:

            # Preserve raw output if model ever fails
            # strict JSON generation.

            return self._normalize_analysis({

                "assessed_risk":
                    "Unknown",

                "agreement_with_model":
                    False,

                "summary":
                    (
                        "The local LLM response "
                        "could not be parsed."
                    ),

                "risk_reasoning":
                    raw_response,

                "relevant_sections":
                    [],

                "irrelevant_or_weak_sections":
                    [],

                "contractual_concern":
                    "Unable to parse analysis.",

                "suggested_mitigation":
                    (
                        "Manual review recommended."
                    ),

                "human_review_required":
                    True,

                "evidence_sufficient":
                    False,
            }, retrieved_law, response_valid=False)

        return self._normalize_analysis(analysis, retrieved_law)

    @staticmethod
    def _normalize_analysis(analysis, retrieved_law, response_valid=True):
        """Validate the remembered clause-analysis fields and cited sections."""
        if not isinstance(analysis, dict):
            analysis = {}
            response_valid = False

        required = {
            "assessed_risk", "agreement_with_model", "summary", "risk_reasoning",
            "relevant_sections", "irrelevant_or_weak_sections", "contractual_concern",
            "suggested_mitigation", "human_review_required", "evidence_sufficient",
        }
        if not required.issubset(analysis):
            response_valid = False
        if not isinstance(analysis.get("assessed_risk"), str):
            response_valid = False
        for key in ("summary", "risk_reasoning", "contractual_concern", "suggested_mitigation"):
            if not isinstance(analysis.get(key), str):
                response_valid = False
        for key in ("relevant_sections", "irrelevant_or_weak_sections"):
            if not isinstance(analysis.get(key), list):
                response_valid = False
        for key in ("agreement_with_model", "human_review_required", "evidence_sufficient"):
            if not isinstance(analysis.get(key), bool):
                response_valid = False

        valid_sections = {
            str(item.get("section"))
            for item in retrieved_law
            if isinstance(item, dict) and item.get("section") is not None
        }

        def section_items(name, explanation_key):
            values = analysis.get(name)
            if not isinstance(values, list):
                return []
            normalized = []
            for item in values:
                if not isinstance(item, dict) or item.get("section") is None:
                    continue
                section = str(item["section"])
                if section not in valid_sections:
                    continue
                explanation = item.get(explanation_key)
                if isinstance(explanation, str) and explanation.strip():
                    normalized.append({"section": section, explanation_key: explanation.strip()})
            return normalized

        assessed = str(analysis.get("assessed_risk", "Unknown")).strip().title()
        if assessed not in {"Low", "Medium", "High"}:
            assessed = "Unknown"

        return {
            "assessed_risk": assessed,
            "agreement_with_model": analysis.get("agreement_with_model") is True,
            "summary": str(analysis.get("summary") or "Analysis unavailable; manual review required."),
            "risk_reasoning": str(analysis.get("risk_reasoning") or "No grounded reasoning was returned."),
            "relevant_sections": section_items("relevant_sections", "relevance"),
            "irrelevant_or_weak_sections": section_items("irrelevant_or_weak_sections", "reason"),
            "contractual_concern": str(analysis.get("contractual_concern") or "Not identified."),
            "suggested_mitigation": str(analysis.get("suggested_mitigation") or "Manual review recommended."),
            "human_review_required": True,
            "evidence_sufficient": analysis.get("evidence_sufficient") is True,
            "response_valid": response_valid,
        }


##############################################################
# BASIC CONNECTION TEST
##############################################################

if __name__ == "__main__":

    llm = LocalLegalLLM()

    print(
        "=" * 70
    )

    print(
        "LOCAL LEGAL LLM TEST"
    )

    print(
        "=" * 70
    )

    if llm.check_connection():

        print(
            "\nOllama connection: OK"
        )

        print(
            f"Configured model  : "
            f"{llm.model_name}"
        )

    else:

        print(
            "\nOllama connection: FAILED"
        )

        print(
            "Make sure Ollama is running."
        )
