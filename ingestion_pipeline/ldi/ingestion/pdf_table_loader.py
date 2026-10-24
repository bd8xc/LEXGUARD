import pdfplumber


def extract_pdf_text_and_tables(pdf_path: str):

    text_blocks = []
    tables_out = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:

            page_text = page.extract_text() or ""
            if page_text.strip():
                text_blocks.append(page_text.strip())

            for table in page.extract_tables():
                clean = []
                for row in table:
                    clean.append([(cell or "").strip() for cell in row])
                tables_out.append(clean)

    return {
        "text": "\n\n".join(text_blocks),
        "tables": tables_out
    }
