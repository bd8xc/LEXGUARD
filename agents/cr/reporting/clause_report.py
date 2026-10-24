from pathlib import Path
from datetime import datetime

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)

REPORT_FOLDER = (
    Path("outputs")
    / "clause_reports"
)

REPORT_FOLDER.mkdir(
    parents=True,
    exist_ok=True,
)

timestamp = datetime.now().strftime(
    "%Y-%m-%d_%H-%M-%S"
)

OUTPUT = (
    REPORT_FOLDER
    / f"contract_analysis_{timestamp}.pdf"
)


def safe(value):
    """
    ReportLab cannot render None.
    """
    if value is None:
        return "Not provided."

    value = str(value).strip()

    if value == "":
        return "Not provided."

    return value


def generate_pdf_report(result):

    OUTPUT.parent.mkdir(
        exist_ok=True
    )

    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        str(OUTPUT)
    )

    story = []

    model = result.get("model", {})
    analysis = result.get("analysis", {})
    retrieved = result.get("retrieved_law", [])

    ###########################################################
    # TITLE
    ###########################################################

    story.append(
        Paragraph(
            "Contract Risk & Compliance Analysis Report",
            styles["Title"],
        )
    )

    story.append(
        Spacer(1, 20)
    )

    ###########################################################
    # CLAUSE
    ###########################################################

    story.append(
        Paragraph(
            "<b>Contract Clause</b>",
            styles["Heading2"],
        )
    )

    story.append(
        Paragraph(
            safe(result.get("clause")),
            styles["BodyText"],
        )
    )

    story.append(
        Spacer(1, 20)
    )

    ###########################################################
    # LEGALBERT
    ###########################################################

    story.append(
        Paragraph(
            "<b>LegalBERT Risk Signal</b>",
            styles["Heading2"],
        )
    )

    prediction = safe(
        model.get("prediction")
    )

    if prediction.lower() == "seed":
        prediction = "Baseline"

    story.append(
        Paragraph(
            f"Prediction: <b>{prediction}</b>",
            styles["BodyText"],
        )
    )

    score = model.get(
        "model_score"
    )

    if score is not None:

        story.append(
            Paragraph(
                f"Confidence: {score*100:.2f}%",
                styles["BodyText"],
            )
        )

    story.append(
        Spacer(1, 12)
    )

    story.append(
        Paragraph(
            "<b>Class Scores</b>",
            styles["Heading3"],
        )
    )

    for label, score in model.get(
        "class_scores",
        {},
    ).items():

        if label.lower() == "seed":
            label = "Baseline"

        story.append(
            Paragraph(
                f"{label}: {score*100:.2f}%",
                styles["BodyText"],
            )
        )

    story.append(
        Spacer(1, 20)
    )

    ###########################################################
    # RAG
    ###########################################################

    story.append(
        Paragraph(
            "<b>Retrieved Indian Law</b>",
            styles["Heading2"],
        )
    )

    for law in retrieved:

        story.append(
            Paragraph(
                f"<b>Section {safe(law.get('section'))}</b>",
                styles["Heading3"],
            )
        )

        story.append(
            Paragraph(
                safe(law.get("heading")),
                styles["BodyText"],
            )
        )

        score = law.get("score")

        if score is not None:

            story.append(
                Paragraph(
                    f"Similarity Score: {score:.4f}",
                    styles["BodyText"],
                )
            )

        story.append(
            Spacer(1, 8)
        )

    story.append(
        Spacer(1, 12)
    )

    ###########################################################
    # LLM
    ###########################################################

    story.append(
        Paragraph(
            "<b>Grounded Local LLM Analysis</b>",
            styles["Heading2"],
        )
    )

    story.append(
        Paragraph(
            f"Assessed Risk: <b>{safe(analysis.get('assessed_risk'))}</b>",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Agreement with ML: {'YES' if analysis.get('agreement_with_model') else 'NO'}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Evidence Sufficient: {'YES' if analysis.get('evidence_sufficient') else 'NO'}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Human Review Required: {'YES' if analysis.get('human_review_required') else 'NO'}",
            styles["BodyText"],
        )
    )

    story.append(
        Spacer(1, 18)
    )

    sections = [

        (
            "Summary",
            safe(
                analysis.get("summary")
            ),
        ),

        (
            "Risk Reasoning",
            safe(
                analysis.get(
                    "risk_reasoning"
                )
            ),
        ),

        (
            "Contractual Concern",
            safe(
                analysis.get(
                    "contractual_concern"
                )
            ),
        ),

        (
            "Suggested Mitigation",
            safe(
                analysis.get(
                    "suggested_mitigation"
                )
            ),
        ),

    ]

    for heading, body in sections:

        story.append(
            Paragraph(
                f"<b>{heading}</b>",
                styles["Heading3"],
            )
        )

        story.append(
            Paragraph(
                body,
                styles["BodyText"],
            )
        )

        story.append(
            Spacer(1, 10)
        )

    ###########################################################
    # DISCLAIMER
    ###########################################################

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "<b>Disclaimer</b>",
            styles["Heading2"],
        )
    )

    story.append(
        Paragraph(
            "This report is generated automatically using a hybrid AI pipeline combining LegalBERT, Retrieval-Augmented Generation (RAG), and a local Large Language Model. "
            "It is intended for decision support only and does not constitute legal advice.",
            styles["BodyText"],
        )
    )

    doc.build(story)

    return OUTPUT