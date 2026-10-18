import json
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

    Ollama is expected to run locally.
    """

    def __init__(
            self,
            model_name="qwen2.5:1.5b",
            base_url="http://localhost:11434",
        ):
        self.model_name = model_name

        self.base_url = (
            base_url.rstrip("/")
        )

        self.generate_url = (
            f"{self.base_url}/api/generate"
        )

    ##########################################################
    # CHECK CONNECTION
    ##########################################################

    def check_connection(self):

        try:

            response = requests.get(
                f"{self.base_url}/api/tags",
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

    @staticmethod
    def _format_litigation_result(
        litigation_result: Dict | None,
    ) -> str:

        if not litigation_result:
            return "No litigation-exposure result was supplied."

        return json.dumps(
            litigation_result,
            indent=2,
            ensure_ascii=False,
        )

    ##########################################################
    # BUILD PROMPT
    ##########################################################

    def _build_prompt(
        self,
        clause: str,
        model_result: Dict,
        retrieved_law: List[Dict],
        litigation_result: Dict | None = None,
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

        litigation_context = (
            self._format_litigation_result(
                litigation_result
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
4. A contract-level Litigation Exposure model result, when supplied.

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
- Treat both model outputs as fallible signals, not legal conclusions.
- The Litigation Exposure model was trained on synthetic data. Its
  probability is not a calibrated or validated real-world litigation
  probability. SHAP values describe model contributions, not causation.
- The Litigation Exposure model is trained on contract-level records. In this
  clause-first workflow, treat its output as deal-context exposure for the
  selected clause, not as the probability that this clause alone causes suit.
- Weigh the litigation result together with the clause and legal context;
  do not repeat it as a proven fact or let it establish legal liability.

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
LITIGATION EXPOSURE MODEL RESULT
============================================================

{litigation_context}

============================================================
TASK
============================================================

Return ONLY valid JSON using exactly this structure:

{{
    "assessed_risk": "Low | Medium | High",
    "agreement_with_model": true,
    "summary": "Short overall assessment.",
    "risk_reasoning": "Explain the clause risk and how the supplied model signals affect the overall assessment.",
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
        litigation_result: Dict | None = None,
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
                litigation_result=litigation_result,
            )
        )

        payload = {

            "model":
                self.model_name,

            "prompt":
                prompt,

            "stream":
                False,

            "format":
                "json",

            "options": {

                # Low temperature is preferable for
                # grounded legal analysis.
                "temperature":
                    0.1,

            },
        }

        try:

            response = requests.post(
                self.generate_url,
                json=payload,
                timeout=180,
            )

            response.raise_for_status()

        except requests.RequestException as error:

            raise RuntimeError(
                "Could not communicate with "
                "the local Ollama server. "
                "Make sure Ollama is running "
                "and the requested model is installed."
            ) from error

        data = response.json()

        raw_response = data.get(
            "response",
            ""
        ).strip()

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

            return {

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
            }

        return analysis

    def summarize_contract(
        self, cra_values: List[Dict], cl_values: Dict,
        skipped_clauses: List[Dict] | None = None,
    ) -> Dict:
        """Synthesize contract CRA and CL outputs without inventing a score."""
        payload_data = {
            "cra_clause_results": cra_values,
            "skipped_clauses": skipped_clauses or [],
            "confidentiality": cl_values,
        }
        prompt = f"""You are summarizing automated contract-review outputs for a human reviewer.
Use only the supplied CRA and CL values. Do not make a legal conclusion, recalculate any agent score, or infer missing facts.
Treat CRA's ML prediction as a model signal and its clause LLM assessment as an assessment, not a finding of law.
Treat CL's risk_score and risk_level as authoritative agent outputs. A CONTEXT_DEPENDENT NER match alone is not evidence of a leak.
Processing activities describe how data is handled; they are context, not proof of a leak. Distinguish personal data, sensitive personal data, and business-confidential findings.
Return strict JSON with keys: overall_assessment (2-4 sentences), cra_summary, cl_summary, key_risks (array of concise strings), review_priorities (array of concise strings), limitations (one concise string).
Mention clause IDs wherever supplied. If values are unavailable, say so. Do not use markdown or text outside the JSON.

INPUT JSON:
{json.dumps(payload_data, ensure_ascii=False)}"""
        request_payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        try:
            response = requests.post(self.generate_url, json=request_payload, timeout=180)
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(
                "Could not generate the overall CRA/CL summary through local Ollama."
            ) from error

        raw_response = str(response.json().get("response", "")).strip()
        if not raw_response:
            raise RuntimeError("Local LLM returned an empty overall summary.")
        try:
            result = json.loads(raw_response)
        except json.JSONDecodeError as error:
            raise RuntimeError("Local LLM returned invalid JSON for the overall summary.") from error
        for key in ("overall_assessment", "cra_summary", "cl_summary", "limitations"):
            if not isinstance(result.get(key), str):
                result[key] = "Not provided by the LLM."
        for key in ("key_risks", "review_priorities"):
            if not isinstance(result.get(key), list):
                result[key] = []
        return result


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
