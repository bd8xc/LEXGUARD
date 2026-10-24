"""Local FastAPI application for the LexGuard contract workflow."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from agents.contract_coordinator import (
    LE_FEATURES, _mask_tree, _run_cl, _run_coi, _run_cr, _run_le,
    load_contract_runtime,
)
from backend.jobs import ContractJobManager
from ingestion_pipeline.document_input import extract_text
from ingestion_pipeline.ldi.chunking.clause_splitter import split_clauses


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
UPLOAD_DIR = ROOT / "contracts" / "uploads"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # The ingestion pipeline enforces this limit.
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
job_manager = ContractJobManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    print("[Startup] Loading reusable CR model and India-law RAG for this server session...", flush=True)
    runtime = await asyncio.to_thread(load_contract_runtime)
    job_manager.set_runtime(runtime)
    app.state.runtime = runtime
    print("[Startup] Backend is ready to accept contract uploads.", flush=True)
    yield
    job_manager.shutdown()


app = FastAPI(
    title="LexGuard Contract Review",
    description="Local contract analysis with live clause progress.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

PAGES = {
    "/": "index.html", "/review": "review.html", "/results": "results.html",
    "/workspaces": "workspaces.html", "/tools/conflicts": "conflicts.html",
    "/tools/clauses": "clauses.html", "/tools/confidentiality": "confidentiality.html",
    "/tools/litigation": "litigation.html", "/advanced": "advanced.html",
}


class TextContract(BaseModel):
    contract_text: str = Field(min_length=40, max_length=120_000)
    client_entity: str = ""
    counterparty_entity: str = ""
    additional_entities: str = ""
    le_features: dict[str, float] = Field(default_factory=dict)
    clause_deviation_score: float | None = None


class Parties(BaseModel):
    client_entity: str = Field(min_length=1)
    counterparty_entity: str = Field(min_length=1)
    additional_entities: str = ""


class LitigationParties(Parties):
    le_features: dict[str, float] = Field(default_factory=dict)
    clause_deviation_score: float | None = None


class ContractText(BaseModel):
    contract_text: str = Field(min_length=40, max_length=120_000)


def operator_input(client: str, counterparty: str, additional: str,
                   features: dict[str, float], deviation: float | None) -> dict:
    for name, value in features.items():
        if name not in LE_FEATURES:
            raise HTTPException(422, f"Unknown LE input: {name}.")
        _, minimum, maximum = LE_FEATURES[name]
        if not minimum <= value <= maximum:
            raise HTTPException(422, f"{name} must be between {minimum:g} and {maximum:g}.")
    if deviation is not None and not 0 <= deviation <= 1:
        raise HTTPException(422, "clause_deviation_score must be between 0 and 1.")
    extra = [name.strip() for name in re.split(r"[,;\n]+", additional) if name.strip()]
    if len(extra) > 13:
        raise HTTPException(422, "Enter no more than 13 additional entities.")
    return {
        "client_entity": client.strip(), "counterparty_entity": counterparty.strip(),
        "additional_entities": extra, "le_features": features,
        "clause_deviation_score": deviation,
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(WEB_DIR / PAGES["/"])


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "lexguard-local"}


@app.get("/api/status")
def agent_status() -> dict[str, str]:
    import importlib.util

    runtime = getattr(app.state, "runtime", None)
    if not runtime or not runtime.predictor:
        cr_status = "missing_model"
    elif not runtime.rag or not runtime.llm_client or not runtime.llm_client.check_connection():
        cr_status = "degraded"
    else:
        cr_status = "ready"
    load_dotenv(ROOT / ".env")
    coi_ready = False
    if (ROOT / "agents/coi/graph_manager.py").is_file() and os.getenv("NEO4J_PASSWORD") not in (None, "", "replace_me"):
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                auth=(os.getenv("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
                connection_timeout=2,
            )
            try:
                driver.verify_connectivity()
                coi_ready = True
            finally:
                driver.close()
        except Exception:
            pass
    return {
        "cr": cr_status,
        "cl": "ready" if importlib.util.find_spec("spacy") else "unavailable",
        "coi": "ready" if coi_ready else "unavailable",
        "le": "ready" if importlib.util.find_spec("joblib") and (ROOT / "agents/le/litigation_model.joblib").is_file() else "unavailable",
    }


@app.post("/api/contracts", status_code=202)
async def submit_contract(
    file: UploadFile = File(...),
    client_entity: str = Form(""),
    counterparty_entity: str = Form(""),
    additional_entities: str = Form(""),
    deal_size: float | None = Form(None),
    liability_cap: float | None = Form(None),
    auto_renewal: float | None = Form(None),
    jurisdiction_risk: float | None = Form(None),
    indemnification_clause: float | None = Form(None),
    dispute_history: float | None = Form(None),
    governing_law_clarity: float | None = Form(None),
    clause_deviation_score: float | None = Form(None),
) -> dict[str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Upload a PDF, DOCX, or TXT contract.")

    le_values = {
        "deal_size": deal_size,
        "liability_cap": liability_cap,
        "auto_renewal": auto_renewal,
        "jurisdiction_risk": jurisdiction_risk,
        "indemnification_clause": indemnification_clause,
        "dispute_history": dispute_history,
        "governing_law_clarity": governing_law_clarity,
    }
    inputs = operator_input(client_entity, counterparty_entity, additional_entities,
                            {name: value for name, value in le_values.items() if value is not None},
                            clause_deviation_score)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"{uuid4().hex}{suffix}"
    size = 0
    try:
        with saved_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    destination.close()
                    saved_path.unlink(missing_ok=True)
                    raise HTTPException(413, "Contract upload exceeds the 5 MiB limit.")
                destination.write(chunk)
    finally:
        await file.close()

    if size == 0:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded contract is empty.")

    job_id = job_manager.submit(saved_path, inputs)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Analysis job not found.")
    return job


@app.get("/api/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    if job_manager.get(job_id) is None:
        raise HTTPException(404, "Analysis job not found.")
    try:
        cursor = max(0, int(last_event_id or 0))
    except ValueError:
        cursor = 0

    async def event_stream():
        nonlocal cursor
        while True:
            events, status = await asyncio.to_thread(
                job_manager.wait_for_events,
                job_id,
                cursor,
                15.0,
            )
            for event in events:
                cursor = event["id"]
                payload = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
                yield f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n"
            if status in {"complete", "failed", "missing"}:
                break
            if not events:
                yield ": keep-alive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}/reports/{kind}")
def download_report(job_id: str, kind: str) -> FileResponse:
    if kind not in {"json", "pdf"}:
        raise HTTPException(404, "Report type must be json or pdf.")
    path = job_manager.report_path(job_id, kind)
    if path is None:
        job = job_manager.get(job_id)
        if job is None:
            raise HTTPException(404, "Analysis job not found.")
        if job["status"] not in {"complete", "failed"}:
            raise HTTPException(409, "The analysis has not finished yet.")
        raise HTTPException(404, f"The {kind.upper()} report is not available.")
    media_type = "application/pdf" if kind == "pdf" else "application/json"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.post("/api/extract")
async def preview_extract(file: UploadFile = File(...)) -> dict[str, str]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Upload a PDF, DOCX, or TXT contract.")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Contract upload exceeds the 5 MiB limit.")
    try:
        return {"text": await asyncio.to_thread(extract_text, file.filename or "contract.txt", raw)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/contracts/text", status_code=202)
def submit_text_contract(request: TextContract) -> dict[str, str]:
    inputs = operator_input(request.client_entity, request.counterparty_entity,
                            request.additional_entities, request.le_features,
                            request.clause_deviation_score)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = UPLOAD_DIR / f"pasted-{uuid4().hex}.txt"
    saved_path.write_text(request.contract_text, encoding="utf-8")
    return {"job_id": job_manager.submit(saved_path, inputs), "status": "queued"}


@app.post("/api/tools/conflicts")
def check_conflicts(request: Parties) -> dict:
    inputs = operator_input(request.client_entity, request.counterparty_entity,
                            request.additional_entities, {}, None)
    return _run_coi(f"specialist-{uuid4().hex}", inputs)


@app.post("/api/tools/litigation")
def check_litigation(request: LitigationParties) -> dict:
    inputs = operator_input(request.client_entity, request.counterparty_entity,
                            request.additional_entities, request.le_features,
                            request.clause_deviation_score)
    coi = _run_coi(f"specialist-{uuid4().hex}", inputs)
    le = _run_le(inputs, coi)
    return {"coi": coi, "le": le}


def clauses_from_text(text: str) -> list[dict]:
    clauses = split_clauses(text)
    if not clauses:
        raise HTTPException(422, "The ingestion pipeline did not identify any clauses.")
    return clauses


@app.post("/api/tools/clauses")
def check_clauses(request: ContractText) -> dict:
    clauses = clauses_from_text(request.contract_text)
    result = _run_cr(clauses, runtime=getattr(app.state, "runtime", None))
    return {**result, "clauses": [{k: v for k, v in row.items() if k not in {"text", "excerpt"}}
                                    for row in result.get("clauses", [])]}


@app.post("/api/tools/confidentiality")
def check_confidentiality(request: ContractText) -> dict:
    clauses = clauses_from_text(request.contract_text)
    result, replacements = _run_cl(f"specialist-{uuid4().hex}", clauses)
    return _mask_tree(result, replacements)


@app.get("/{page_path:path}", include_in_schema=False)
def frontend_page(page_path: str) -> FileResponse:
    page = PAGES.get("/" + page_path.rstrip("/"))
    if page is None:
        raise HTTPException(404, "Page not found.")
    return FileResponse(WEB_DIR / page)
