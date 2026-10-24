# =============================================================================
# PDF CHUNK QUALITY TESTS
# End-to-end evaluation:
# PDF → ingestion → chunker → semantic scoring
# =============================================================================

import os
import glob
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

# ✅ YOUR project imports
from ingestion_pipeline.ldi.chunking.clause_splitter import split_clauses
from ingestion_pipeline.ldi.ingestion.pdf_table_loader import extract_pdf_text_and_tables


# =============================================================================
# CONFIG
# =============================================================================

TEST_DIR = os.path.join(os.path.dirname(__file__), "sample legal docs")

embedder = SentenceTransformer("all-MiniLM-L6-v2")

MIN_WORDS = 40
MAX_WORDS = 500


# =============================================================================
# HELPERS
# =============================================================================

def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def semantic_score(text: str):
    """Measures if sentences inside a chunk are semantically related."""
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 20]

    if len(sentences) < 2:
        return 1.0

    emb = embedder.encode(sentences)

    sims = []
    for i in range(len(emb) - 1):
        sims.append(cosine(emb[i], emb[i + 1]))

    return float(np.mean(sims))


def header_like(text: str):
    starters = (
        "ARTICLE", "SCHEDULE", "ANNEX",
        "1.", "2.", "3.", "4.",
        "(a)", "(b)", "(i)"
    )
    return text.strip().upper().startswith(starters)


# =============================================================================
# CORE EVALUATION
# =============================================================================

def evaluate_pdf(path):

    # ✅ Use YOUR ingestion

    result = extract_pdf_text_and_tables(path)
    text = result["text"] if isinstance(result, dict) else result
    chunks = split_clauses(text)

    sizes = []
    coherences = []

    for c in chunks:
        t = c["text"]
        sizes.append(len(t.split()))
        coherences.append(semantic_score(t))

    return {
        "file": os.path.basename(path),
        "chunks": len(chunks),
        "avg_words": np.mean(sizes),
        "semantic_score": np.mean(coherences),
        "too_small_ratio": np.mean(np.array(sizes) < MIN_WORDS),
        "too_large_ratio": np.mean(np.array(sizes) > MAX_WORDS),
    }


# =============================================================================
# PYTEST TEST
# =============================================================================

def test_pdf_chunk_quality():

    pdfs = glob.glob(os.path.join(TEST_DIR, "*.pdf"))

    assert pdfs, "No PDFs found in tests/sample_docs"

    reports = []
    passed = 0
    failed = 0
    passed_files = []
    failed_files = []

    for pdf in pdfs:
        r = evaluate_pdf(pdf)
        reports.append(r)

        print(f"\n📄 {r['file']} → {r}")

        # 🔥 QUALITY GATES
        if r["semantic_score"] > 0.6 and r["avg_words"] > 35:
            passed += 1
            passed_files.append(r['file'])
        else:
            failed += 1
            failed_files.append(r['file'])


    print(f"\nSummary: {passed} PDFs passed, {failed} PDFs failed.")
    if passed_files:
        print("Passed files:", ", ".join(passed_files))
    if failed_files:
        print("Failed files:", ", ".join(failed_files))
        # Fail the test if any failed
        assert False, f"{failed} PDFs failed quality gates: {', '.join(failed_files)}"

    # Save metrics in the tests directory
    df = pd.DataFrame(reports)
    out_csv = os.path.join(os.path.dirname(__file__), "chunk_quality_report.csv")
    df.to_csv(out_csv, index=False)
