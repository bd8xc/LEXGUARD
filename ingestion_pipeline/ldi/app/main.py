from fastapi import APIRouter, FastAPI, UploadFile, File, Body
from typing import List
import shutil
import os
from pathlib import Path
from tempfile import mkstemp
from ingestion_pipeline.ldi.search.pipeline import search_clauses
from pydantic import BaseModel
from agents.cl.confidentiality_leakage.router import router as confidentiality_router

# PDF loader: extracts both text and tables from PDF
from ingestion_pipeline.ldi.ingestion.pdf_table_loader import extract_pdf_text_and_tables
# DOCX loader: extracts both text and tables from DOCX
from ingestion_pipeline.ldi.ingestion.docx_loader import load_docx
# Clause chunker: splits text into legal clause objects
from ingestion_pipeline.ldi.chunking.clause_splitter import split_clauses

# Embedding pipeline
from ingestion_pipeline.ldi.embeddings.pipeline import embed_and_store
# Search pipeline

class SearchRequest(BaseModel):
    query: str
    k: int = 5

# Initialize FastAPI app

app = FastAPI()
app.include_router(confidentiality_router)
router = APIRouter(tags=["Ingestion"])


def _save_upload(file: UploadFile) -> str:
    """Store an upload under a unique, server-chosen temporary name."""
    suffix = Path(file.filename or "").suffix.lower()
    descriptor, path = mkstemp(suffix=suffix if suffix in {".pdf", ".docx"} else "")
    try:
        with os.fdopen(descriptor, "wb") as output:
            shutil.copyfileobj(file.file, output)
    except Exception:
        os.remove(path)
        raise
    return path


# ==============================
# INGEST ENDPOINT: Extracts text and tables from uploaded PDF or DOCX (single file)
# ==============================
@router.post("/ingest/")
async def ingest_document(file: UploadFile = File(...)):
    temp_path = _save_upload(file)
    try:
        if file.filename.lower().endswith(".pdf"):
            result = extract_pdf_text_and_tables(temp_path)
        elif file.filename.lower().endswith(".docx"):
            result = load_docx(temp_path)
        else:
            return {"error": "Unsupported file type"}
    finally:
        os.remove(temp_path)
    return result


# ==============================
# CHUNK ENDPOINT: Splits text into legal clauses and returns tables (single file)
# ==============================
@router.post("/chunk/")
async def chunk_document(file: UploadFile = File(...)):
    temp_path = _save_upload(file)
    try:
        if file.filename.lower().endswith(".pdf"):
            result = extract_pdf_text_and_tables(temp_path)
        elif file.filename.lower().endswith(".docx"):
            result = load_docx(temp_path)
        else:
            return {"error": "Unsupported file type"}
        text = result["text"]
        tables = result["tables"]
        clauses = split_clauses(text)
    finally:
        os.remove(temp_path)
    return {
        "clauses": clauses,
        "tables": tables,
        "clause_count": len(clauses),
        "table_count": len(tables)
    }


# ==============================
# INGEST MULTI ENDPOINT: Extracts text and tables from multiple uploaded PDFs or DOCXs
# ==============================
@router.post("/ingest-multi/")
async def ingest_documents(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        temp_path = _save_upload(file)
        try:
            if file.filename.lower().endswith(".pdf"):
                result = extract_pdf_text_and_tables(temp_path)
            elif file.filename.lower().endswith(".docx"):
                result = load_docx(temp_path)
            else:
                result = {"error": f"Unsupported file type: {file.filename}"}
        finally:
            os.remove(temp_path)
        results.append({"filename": file.filename, **result})
    return results



# ==============================
# CHUNK MULTI ENDPOINT: Splits text into legal clauses and returns tables (multiple files)
# ==============================
@router.post("/chunk-multi/")
async def chunk_documents(files: List[UploadFile] = File(...)):
    results = []
    for file in files:
        temp_path = _save_upload(file)
        try:
            if file.filename.lower().endswith(".pdf"):
                result = extract_pdf_text_and_tables(temp_path)
            elif file.filename.lower().endswith(".docx"):
                result = load_docx(temp_path)
            else:
                results.append({"filename": file.filename, "error": "Unsupported file type"})
                continue
            text = result["text"]
            tables = result["tables"]
            clauses = split_clauses(text)
            results.append({
                "filename": file.filename,
                "clauses": clauses,
                "tables": tables,
                "clause_count": len(clauses),
                "table_count": len(tables)
            })
        finally:
            os.remove(temp_path)
    return results


@router.post("/embed-multi/")
async def embed_documents(files: List[UploadFile] = File(...)):
    """
    Embeds and stores legal clauses from multiple uploaded PDF or DOCX files.
    Returns a list of results per file.
    """
    results = []
    for file in files:
        temp_path = _save_upload(file)
        try:
            if file.filename.lower().endswith(".pdf"):
                result = extract_pdf_text_and_tables(temp_path)
            elif file.filename.lower().endswith(".docx"):
                result = load_docx(temp_path)
            else:
                results.append({"filename": file.filename, "error": "Unsupported file type"})
                continue
            text = result["text"]
            clauses = split_clauses(text)

            for table_index, table in enumerate(result.get("tables", []) or [], start=1):
                table_text = "\n".join(["\t".join(row) for row in table])
                clauses.append(
                    {
                        "clause_id": f"TABLE_{table_index}",
                        "section": f"Table {table_index}",
                        "level": "table",
                        "text": table_text,
                    }
                )
            stats = embed_and_store(clauses, file.filename)
            results.append({
                "filename": file.filename,
                "clauses_indexed": stats["clauses"],
                "status": "cached" if stats.get("cached") else "success"
            })
        finally:
            os.remove(temp_path)
    return results



    # ==============================
    # SEARCH ENDPOINT: Semantic search for legal clauses
    # ==============================


@router.post("/search/")
async def search_endpoint(body: SearchRequest = Body(...)):
    """
    Semantic search for legal clauses.
    Body: {"query": str, "k": int}
    Returns: {"results": [...]} 
    """
    results = search_clauses(body.query, body.k)
    return {"results": results}


app.include_router(router)

