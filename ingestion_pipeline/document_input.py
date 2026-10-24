"""Extract review text from one uploaded document in memory."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from pypdf import PdfReader
from pypdf.errors import PdfReadError


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 120_000


def extract_text(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.casefold()
    if extension not in {".txt", ".pdf", ".docx"}:
        raise ValueError("Upload a TXT, PDF, or DOCX file.")
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("File must be nonempty and at most 5 MB.")

    try:
        if extension == ".txt":
            text = content.decode("utf-8-sig")
        elif extension == ".pdf":
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 100:
                raise ValueError("Encrypted PDFs and PDFs over 100 pages are unsupported.")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            document = Document(BytesIO(content))
            blocks = []
            for block in document.iter_inner_content():
                if isinstance(block, Table):
                    blocks.extend("\t".join(cell.text for cell in row.cells) for row in block.rows)
                elif block.text.strip():
                    blocks.append(block.text)
            text = "\n\n".join(blocks)
    except (PdfReadError, BadZipFile, PackageNotFoundError) as exc:
        raise ValueError("The document could not be read.") from exc

    text = text.strip()
    if not text:
        raise ValueError("No text was extracted. Scanned PDFs need OCR before review.")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Extracted text exceeds the 120,000-character review limit.")
    return text
