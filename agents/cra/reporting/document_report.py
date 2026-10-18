from pathlib import Path

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)


PDF_OUTPUT = Path("outputs") / "contract_analysis.pdf"


def generate_pdf_report(
    document,
    summary,
    results,
):
    """
    Creates a professional PDF version of the
    contract analysis.
    """

    PDF_OUTPUT.parent.mkdir(
        exist_ok=True
    )

    doc = SimpleDocTemplate(
        str(PDF_OUTPUT)
    )

    styles = getSampleStyleSheet()

    story = []

    ####################################################
    # TITLE
    ####################################################

    story.append(
        Paragraph(
            "Contract Risk Analysis Report",
            styles["Title"],
        )
    )

    story.append(
        Spacer(1, 20)
    )

    ####################################################
    # DOCUMENT
    ####################################################

    story.append(
        Paragraph(
            "<b>Document Information</b>",
            styles["Heading2"],
        )
    )

    story.append(
        Paragraph(
            f"File: {document['file_name']}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Pages: {document['page_count']}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Words: {document['word_count']}",
            styles["BodyText"],
        )
    )

    story.append(
        Spacer(1, 20)
    )

    ####################################################
    # SUMMARY
    ####################################################

    story.append(
        Paragraph(
            "<b>Risk Summary</b>",
            styles["Heading2"],
        )
    )

    counts = summary["prediction_counts"]

    story.append(
        Paragraph(
            f"Seed: {counts['Seed']}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Low: {counts['Low']}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Medium: {counts['Medium']}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"High: {counts['High']}",
            styles["BodyText"],
        )
    )

    story.append(
        Spacer(1, 20)
    )

    ####################################################
    # CLAUSES
    ####################################################

    story.append(
        Paragraph(
            "<b>Clause Analysis</b>",
            styles["Heading2"],
        )
    )

    for result in results:

        story.append(
            Paragraph(
                f"<b>{result['clause_number']} - {result['heading']}</b>",
                styles["Heading3"],
            )
        )

        story.append(
            Paragraph(
                f"Prediction: {result['prediction']}",
                styles["BodyText"],
            )
        )

        score = result.get("model_score")

        if score is not None:

            try:
                score = float(score)

                if score <= 1:
                    score *= 100

                story.append(
                    Paragraph(
                        f"Confidence: {score:.2f}%",
                        styles["BodyText"],
                    )
                )
            except:
                pass

        story.append(
            Paragraph(
                result["text"],
                styles["BodyText"],
            )
        )

        story.append(
            Spacer(1, 14)
        )

    doc.build(story)

    return PDF_OUTPUT