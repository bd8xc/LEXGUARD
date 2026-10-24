"""Local FastAPI application for the LexGuard contract workflow."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agents.contract_coordinator import LE_FEATURES, load_contract_runtime
from backend.jobs import ContractJobManager


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
UPLOAD_DIR = ROOT / "contracts" / "uploads"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
job_manager = ContractJobManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    print("[Startup] Loading reusable CR model and India-law RAG for this server session...", flush=True)
    runtime = await asyncio.to_thread(load_contract_runtime)
    job_manager.set_runtime(runtime)
    print("[Startup] Backend is ready to accept contract uploads.", flush=True)
    yield
    job_manager.shutdown()


app = FastAPI(
    title="LexGuard Contract Review",
    description="Local contract analysis with live clause progress.",
    lifespan=lifespan,
)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "lexguard-local"}


@app.post("/api/contracts", status_code=202)
async def submit_contract(
    file: UploadFile = File(...),
    client_entity: str = Form(""),
    counterparty_entity: str = Form(""),
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
    for name, value in le_values.items():
        if value is not None:
            _, minimum, maximum = LE_FEATURES[name]
            if not minimum <= value <= maximum:
                raise HTTPException(
                    422,
                    f"{name} must be between {minimum:g} and {maximum:g}.",
                )
    if clause_deviation_score is not None and not 0 <= clause_deviation_score <= 1:
        raise HTTPException(422, "clause_deviation_score must be between 0 and 1.")

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
                    raise HTTPException(413, "Contract upload exceeds the 50 MiB limit.")
                destination.write(chunk)
    finally:
        await file.close()

    if size == 0:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(400, "The uploaded contract is empty.")

    operator_input = {
        "client_entity": client_entity.strip(),
        "counterparty_entity": counterparty_entity.strip(),
        "le_features": {name: value for name, value in le_values.items() if value is not None},
        "clause_deviation_score": clause_deviation_score,
    }
    job_id = job_manager.submit(saved_path, operator_input)
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
