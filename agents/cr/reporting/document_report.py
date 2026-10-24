from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)


PDF_OUTPUT = Path(__file__).resolve().parents[1] / "outputs" / "contract_analysis.pdf"


def generate_pdf_report(
    document,
    summary,
    results,
    agent_results=None,
    output_path=None,
):
    """
    Creates a professional PDF version of the
    contract analysis.
    """

    pdf_output = Path(output_path) if output_path else PDF_OUTPUT
    pdf_output.parent.mkdir(
        exist_ok=True
    )

    doc = SimpleDocTemplate(
        str(pdf_output)
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
            f"File: {escape(str(document.get('file_name', 'Unknown')))}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Pages: {escape(str(document.get('page_count') or 'Unknown'))}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Words: {escape(str(document.get('word_count', 0)))}",
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

    counts = summary.get("prediction_counts", {})

    story.append(
        Paragraph(
            f"Seed: {counts.get('Seed', 0)}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Low: {counts.get('Low', 0)}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"Medium: {counts.get('Medium', 0)}",
            styles["BodyText"],
        )
    )

    story.append(
        Paragraph(
            f"High: {counts.get('High', 0)}",
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
                f"<b>{escape(str(result.get('clause_number', result.get('clause_id', 'N/A'))))} - "
                f"{escape(str(result.get('heading', result.get('section', 'UNSPECIFIED'))))}</b>",
                styles["Heading3"],
            )
        )

        story.append(
            Paragraph(
                f"Prediction: {escape(str(result.get('prediction', 'Unknown')))}",
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
                        f"Model score: {score:.2f}%",
                        styles["BodyText"],
                    )
                )
            except:
                pass

        class_scores = result.get("class_scores") or {}
        if class_scores:
            rendered_scores = ", ".join(
                f"{label}: {float(value) * 100:.2f}%"
                for label, value in class_scores.items()
            )
            story.append(Paragraph(f"Class scores: {escape(rendered_scores)}", styles["BodyText"]))
        if result.get("num_windows") is not None:
            story.append(Paragraph(f"Windows: {escape(str(result['num_windows']))}", styles["BodyText"]))

        story.append(
            Paragraph(
                escape(str(result.get("excerpt", result.get("text", "")))[:1600]),
                styles["BodyText"],
            )
        )

        analysis = result.get("analysis") or {}
        if analysis:
            story.append(Paragraph("Grounded clause analysis", styles["Heading4"]))
            story.append(Paragraph(
                f"Assessed risk: {escape(str(analysis.get('assessed_risk', 'Unknown')))}; "
                f"agreement with LegalBERT: {escape(str(analysis.get('agreement_with_model', False)))}; "
                f"evidence sufficient: {escape(str(analysis.get('evidence_sufficient', False)))}; "
                f"human review required: {escape(str(analysis.get('human_review_required', True)))}",
                styles["BodyText"],
            ))
            for label, key in (
                ("Summary", "summary"),
                ("Risk reasoning", "risk_reasoning"),
                ("Contractual concern", "contractual_concern"),
                ("Suggested mitigation", "suggested_mitigation"),
            ):
                value = analysis.get(key)
                if value:
                    story.append(Paragraph(f"<b>{label}:</b> {escape(str(value))}", styles["BodyText"]))

            for title, key, detail_key in (
                ("Relevant statutory context", "relevant_sections", "relevance"),
                ("Weak or irrelevant retrieved context", "irrelevant_or_weak_sections", "reason"),
            ):
                story.append(Paragraph(title, styles["Heading4"]))
                items = analysis.get(key) or []
                if not items:
                    story.append(Paragraph("None identified.", styles["BodyText"]))
                for item in items:
                    story.append(Paragraph(
                        f"Section {escape(str(item.get('section', 'Unknown')))}: "
                        f"{escape(str(item.get(detail_key, '')))}",
                        styles["BodyText"],
                    ))

            retrieved_law = result.get("retrieved_law") or []
            story.append(Paragraph("Retrieved Indian law", styles["Heading4"]))
            if not retrieved_law:
                story.append(Paragraph("No statutory provisions were retrieved.", styles["BodyText"]))
            for item in retrieved_law:
                story.append(Paragraph(
                    f"Rank {escape(str(item.get('rank', 'N/A')))}; "
                    f"Section {escape(str(item.get('section', 'Unknown')))}; "
                    f"{escape(str(item.get('heading', '')))}; "
                    f"similarity {escape(str(item.get('score', 'N/A')))}; "
                    f"source {escape(str(item.get('source', '')))}",
                    styles["BodyText"],
                ))
                if item.get("text"):
                    story.append(Paragraph(
                        f"Provision: {escape(str(item['text']))}",
                        styles["BodyText"],
                    ))

            if result.get("llm_error"):
                story.append(Paragraph(
                    f"LLM status: {escape(str(result.get('llm_status', 'unavailable')))}. "
                    f"{escape(str(result['llm_error']))}",
                    styles["BodyText"],
                ))

            if result.get("interpretation_note"):
                story.append(Paragraph(escape(str(result["interpretation_note"])), styles["BodyText"]))

        story.append(
            Spacer(1, 14)
        )

    if agent_results:
        story.extend([Spacer(1, 12), Paragraph("Agent Findings", styles["Heading1"])])

        cr = agent_results.get("cr", {})
        story.append(Paragraph("Contract Risk (CR)", styles["Heading2"]))
        story.append(Paragraph(f"Status: {escape(str(cr.get('status', 'not_run')))}", styles["BodyText"]))
        if cr.get("reason"):
            story.append(Paragraph(escape(str(cr["reason"])), styles["BodyText"]))

        cl = agent_results.get("cl", {})
        cl_report = cl.get("report", {})
        story.append(Paragraph("Confidentiality Leakage (CL)", styles["Heading2"]))
        story.append(Paragraph(f"Status: {escape(str(cl.get('status', 'not_run')))}", styles["BodyText"]))
        if cl.get("reason"):
            story.append(Paragraph(escape(str(cl["reason"])), styles["BodyText"]))
        if cl_report:
            story.append(Paragraph(
                f"Risk: {escape(str(cl_report.get('risk_level', 'Unknown')))} "
                f"({escape(str(cl_report.get('risk_score', 'n/a')))} / 100); "
                f"findings: {escape(str(cl_report.get('total_findings', 0)))}",
                styles["BodyText"],
            ))
            for finding in cl_report.get("findings", [])[:30]:
                story.append(Paragraph(
                    f"{escape(str(finding.get('clause_id', '')))} "
                    f"{escape(str(finding.get('type', 'finding')))} / "
                    f"{escape(str(finding.get('sensitivity', '')))}: "
                    f"{escape(str(finding.get('value', '[redacted]')))}",
                    styles["BodyText"],
                ))

        coi = agent_results.get("coi", {})
        coi_report = coi.get("report", {})
        story.append(Spacer(1, 10))
        story.append(Paragraph("Conflict of Interest (COI)", styles["Heading2"]))
        story.append(Paragraph(f"Status: {escape(str(coi.get('status', 'not_run')))}", styles["BodyText"]))
        if coi.get("reason"):
            story.append(Paragraph(escape(str(coi["reason"])), styles["BodyText"]))
        if coi_report:
            story.append(Paragraph(
                f"Conflict flag: {escape(str(coi_report.get('conflict_flag', 'unknown')))}; "
                f"severity: {escape(str(coi_report.get('severity', 'unknown')))}; "
                f"review required: {escape(str(coi_report.get('review_required', True)))}",
                styles["BodyText"],
            ))
            for finding in coi_report.get("findings", [])[:20]:
                story.append(Paragraph(
                    f"Path: {escape(str(' → '.join(finding.get('path', []))))}; "
                    f"verified: {escape(str(finding.get('verified', False)))}",
                    styles["BodyText"],
                ))

        le = agent_results.get("le", {})
        le_result = le.get("result", {})
        story.append(Spacer(1, 10))
        story.append(Paragraph("Litigation Exposure (LE)", styles["Heading2"]))
        story.append(Paragraph(f"Status: {escape(str(le.get('status', 'not_run')))}", styles["BodyText"]))
        if le.get("reason"):
            story.append(Paragraph(escape(str(le["reason"])), styles["BodyText"]))
        if le_result:
            story.append(Paragraph(
                f"Model score: {escape(str(le_result.get('litigation_probability', 'n/a')))}; "
                f"risk level: {escape(str(le_result.get('risk_level', 'Unknown')))}",
                styles["BodyText"],
            ))
            story.append(Paragraph(
                escape(str(le.get("interpretation", "Synthetic-data model score; not a calibrated real-world probability."))),
                styles["BodyText"],
            ))
            for feature, contribution in le_result.get("shap_explanation", {}).items():
                story.append(Paragraph(
                    f"{escape(str(feature))}: {escape(str(contribution))}",
                    styles["BodyText"],
                ))
        elif le.get("reason"):
            story.append(Paragraph(escape(str(le["reason"])), styles["BodyText"]))

        for warning in agent_results.get("warnings", []):
            story.append(Paragraph(f"Warning: {escape(str(warning))}", styles["BodyText"]))

    doc.build(story)

    return pdf_output
