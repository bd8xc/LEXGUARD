# LDI tests

CL analysis and document resolution tests run without the root web app. `test_chunk_quality.py` evaluates sample PDFs and may download the sentence-transformer model; run it only when its optional dependencies are installed. The `delete_chroma_collection.py` utility can alter a local index and is not part of routine tests.
