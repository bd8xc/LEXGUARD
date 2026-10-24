# Ingestion pipeline

`document_input.py` extracts editable text from TXT, PDF, and DOCX uploads for the root web app. It works in memory and rejects unreadable, encrypted, oversized, or empty documents. The optional `ldi/` package provides table-aware extraction, clause chunking, embeddings, persistent indexing, and search.

The root coordinator passes extracted text to the four agents; uploading alone does not write to the COI graph or the optional Chroma index. See the [LDI README](ldi/README.md) for standalone indexing.
