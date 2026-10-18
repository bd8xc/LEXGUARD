"""HTTP API for contract analysis. Start with ``uvicorn api:app --reload``."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import lru_cache
import sys
from pathlib import Path
from threading import Lock, Thread
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parent
for import_root in (PROJECT_ROOT / "agents", PROJECT_ROOT / "agents" / "cra"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


class PartyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client: str | None = Field(default=None, min_length=1, description="Client name as stored in Neo4j")
    counterparty: str | None = Field(default=None, min_length=1, description="Counterparty name as stored in Neo4j")
    additional: list[str] = Field(default_factory=list, description="Other named entities to include in COI lookup")

    @field_validator("client", "counterparty")
    @classmethod
    def clean_party_name(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("additional")
    @classmethod
    def clean_additional_names(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Additional party names must not be blank.")
        return cleaned

    @model_validator(mode="after")
    def require_party_pair(self) -> "PartyInput":
        if bool(self.client) != bool(self.counterparty):
            raise ValueError("Provide both client and counterparty names, or neither.")
        if self.client and self.counterparty:
            from agents.coi.domain import entity_match_key

            if entity_match_key(self.client) == entity_match_key(self.counterparty):
                raise ValueError("Client and counterparty must be different entities.")
        if not self.client and not self.additional:
            raise ValueError("Provide primary parties or at least one additional name.")
        return self


class ContractAnalysisRequest(BaseModel):
    """JSON request body shown as an editable form in Swagger UI."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{
                "filename": "sample-contract.txt",
                "contract_text": "The Client will purchase components from the Supplier under accepted purchase orders. The same executive is associated with both parties.",
                "parties": {
                    "client": "Acme Components Pvt. Ltd.",
                    "counterparty": "Alpha Orb Technologies Ltd.",
                    "additional": ["Aarav Mehta"],
                },
                "include_litigation_exposure": False,
                "entities": {},
                "clause_deviation_score": None,
            }]
        },
    )

    filename: str = Field(default="contract.txt", description="Display name; contract_text is treated as UTF-8 plaintext")
    contract_text: str = Field(min_length=1, max_length=120_000)
    parties: PartyInput | None = Field(default=None, description="Party hints for COI, searched alongside NER")
    include_litigation_exposure: bool = False
    entities: dict[str, Any] = Field(
        default_factory=dict,
        description="Manual LE features such as deal_size, liability_cap, auto_renewal, jurisdiction_risk, indemnification_clause, dispute_history, governing_law_clarity",
    )
    clause_deviation_score: float | None = Field(default=None, ge=0, le=1)


class LEIntakeForm(BaseModel):
    """Typed LE values used by the browser to build the model intake JSON."""

    model_config = ConfigDict(extra="forbid")

    deal_size: float | None = Field(default=None, ge=50_000, le=5_000_000)
    liability_cap: bool | None = None
    auto_renewal: bool | None = None
    jurisdiction_risk: int | None = Field(default=None, ge=1, le=10)
    indemnification_clause: bool | None = None
    dispute_history: bool | None = None
    governing_law_clarity: int | None = Field(default=None, ge=1, le=5)
    clause_deviation_score: float | None = Field(default=None, ge=0, le=1)


app = FastAPI(
    title="LEXGUARD Contract Analysis API",
    description=(
        "Submit contract plaintext and optional party names. COI combines those "
        "party hints with NER entities found in the contract and searches Neo4j."
    ),
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    """Serve the browser UI alongside the API and Swagger docs."""
    return FileResponse(PROJECT_ROOT / "static" / "index.html")


_WEB_PAGES = {
    "/review": "review.html",
    "/results": "results.html",
    "/workspaces": "workspaces.html",
    "/tools/conflicts": "conflicts.html",
    "/tools/clauses": "clauses.html",
    "/tools/confidentiality": "confidentiality.html",
    "/tools/litigation": "litigation.html",
    "/advanced": "advanced.html",
}


def _page_handler(page: str):
    def serve_page() -> FileResponse:
        return FileResponse(PROJECT_ROOT / "static" / page)

    return serve_page


for _route, _page in _WEB_PAGES.items():
    app.add_api_route(_route, _page_handler(_page), methods=["GET"], include_in_schema=False)


_pipeline_instance = None
_pipeline_lock = Lock()
_initialization_lock = Lock()
_initialization = {
    "status": "not_started",
    "progress": 0,
    "message": "Waiting to initialize analysis agents.",
    "agents": {name: "pending" for name in ("CRA", "CL", "COI", "LE")},
}
_health_lock = Lock()
_health_check_running = False
_agent_health: dict[str, Any] = {
    "status": "not_checked",
    "checked_at": None,
    "agents": {name: {"status": "pending", "message": "Waiting for initialization."} for name in ("CRA", "CL", "COI", "LE")},
}


def _pipeline():
    """Initialize the heavy analysis stack once per API process and reuse it."""
    global _pipeline_instance
    if _pipeline_instance is None:
        with _pipeline_lock:
            if _pipeline_instance is None:
                from agents.cra.orchestration.contract_pipeline import ContractAnalysisPipeline

                _pipeline_instance = ContractAnalysisPipeline()
    return _pipeline_instance


@app.post("/initialize", tags=["system"])
def initialize() -> dict[str, str]:
    """Start loading all agents in the background; poll GET /initialization-status."""
    with _initialization_lock:
        if _initialization["status"] in {"not_started", "failed"}:
            _initialization.update({
                "status": "initializing",
                "progress": 2,
                "message": "Starting model initialization.",
                "agents": {name: "pending" for name in ("CRA", "CL", "COI", "LE")},
            })
            Thread(target=_initialize_agents, daemon=True, name="lexguard-model-init").start()
    return {"status": _initialization["status"], "message": _initialization["message"]}


@app.get("/initialization-status", tags=["system"])
def initialization_status() -> dict[str, Any]:
    """Report current background initialization progress for each agent."""
    return dict(_initialization)


def _initialize_agents() -> None:
    try:
        _initialization.update({
            "progress": 8,
            "message": "Loading CRA and CL models.",
            "agents": {"CRA": "loading", "CL": "loading", "COI": "pending", "LE": "pending"},
        })
        pipeline = _pipeline()
        _initialization.update({
            "progress": 62,
            "message": "CRA and CL are ready. Preparing COI and LE.",
            "agents": {"CRA": "ready", "CL": "ready", "COI": "loading", "LE": "pending"},
        })

        from agents.coi import ConflictOfInterestAgent

        pipeline.coi_agent = ConflictOfInterestAgent()
        _initialization.update({
            "progress": 78,
            "message": "COI agent is ready. Loading the LE model.",
            "agents": {"CRA": "ready", "CL": "ready", "COI": "ready", "LE": "loading"},
        })

        from litigation_agent.agent.litigation_agent import LitigationExposureAgent

        pipeline.contract_risk.litigation_predictor = LitigationExposureAgent()
        _initialization.update({
            "status": "ready",
            "progress": 100,
            "message": "All agents are initialized. Running asynchronous health checks.",
            "agents": {"CRA": "ready", "CL": "ready", "COI": "ready", "LE": "ready"},
        })
        _start_agent_health_check()
    except Exception as exc:
        failed_agents = dict(_initialization["agents"])
        for name, status in failed_agents.items():
            if status == "loading":
                failed_agents[name] = "error"
        _initialization.update({
            "status": "failed",
            "message": f"Agent initialization failed ({type(exc).__name__}).",
            "agents": failed_agents,
        })


def _agent_health_checks() -> dict[str, tuple[str, str]]:
    """Run shallow liveness checks concurrently; do not execute contract inference."""
    pipeline = _pipeline_instance
    checks = {}

    def cra_check():
        system = pipeline.contract_risk
        ready = all(getattr(system, name, None) is not None for name in ("predictor", "rag", "llm"))
        if ready and not system.llm.check_connection():
            return "unavailable", "Models are loaded, but Ollama did not answer its health check."
        return ("healthy", "LegalBERT, legal retrieval, and Ollama are responding.") if ready else ("unavailable", "CRA models are not fully initialized.")

    def cl_check():
        ready = pipeline is not None and getattr(pipeline, "confidentiality", None) is not None
        return ("healthy", "Confidentiality detectors are initialized.") if ready else ("unavailable", "CL is not initialized.")

    def coi_check():
        from agents.coi.graph_manager import get_graph

        graph = get_graph()
        graph.driver.verify_connectivity()
        return "healthy", "COI agent and Neo4j are reachable."

    def le_check():
        predictor = getattr(pipeline.contract_risk, "litigation_predictor", None) if pipeline else None
        ready = predictor is not None and getattr(predictor, "model", None) is not None
        return ("healthy", "Litigation model is loaded.") if ready else ("unavailable", "LE model is not initialized.")

    checks.update(CRA=cra_check, CL=cl_check, COI=coi_check, LE=le_check)
    results: dict[str, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="lexguard-health") as executor:
        futures = {executor.submit(check): name for name, check in checks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                results[name] = ("unavailable", f"Health check failed ({type(exc).__name__}).")
    return results


def _run_agent_health_check() -> None:
    global _health_check_running
    try:
        results = _agent_health_checks()
        agents = {name: {"status": status, "message": message} for name, (status, message) in results.items()}
        all_healthy = all(item["status"] == "healthy" for item in agents.values())
        _agent_health.update({
            "status": "healthy" if all_healthy else "degraded",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "agents": agents,
        })
    finally:
        with _health_lock:
            _health_check_running = False


def _start_agent_health_check() -> None:
    global _health_check_running
    with _health_lock:
        if _health_check_running:
            return
        _health_check_running = True
        _agent_health.update({
            "status": "checking",
            "agents": {name: {"status": "checking", "message": "Health check running."} for name in ("CRA", "CL", "COI", "LE")},
        })
        Thread(target=_run_agent_health_check, daemon=True, name="lexguard-agent-health").start()


@app.post("/agent-health-check", tags=["system"])
def start_agent_health_check() -> dict[str, str]:
    """Start non-blocking health checks for CRA, CL, COI/Neo4j, and LE."""
    if _initialization["status"] != "ready":
        raise HTTPException(status_code=409, detail="Initialize the agents before checking their health.")
    _start_agent_health_check()
    return {"status": _agent_health["status"], "message": "Agent health checks are running in the background."}


@app.get("/agent-health", tags=["system"])
def agent_health() -> dict[str, Any]:
    """Return the latest asynchronous health checkpoint for each agent."""
    return dict(_agent_health)


@app.post("/build-le-intake", tags=["contract analysis"])
def build_le_intake(form: LEIntakeForm) -> dict[str, Any]:
    """Convert typed UI controls into the JSON shape consumed by LE analysis.

    Conflict of interest is intentionally left unknown here; the COI graph scan
    is the source of that feature during contract analysis.
    """
    values = form.model_dump()
    deviation = values.pop("clause_deviation_score")
    entities = {
        key: (None if value is None else float(value))
        for key, value in values.items()
    }
    return {
        "entities": entities,
        "graph_results": {"conflict_flag": None},
        "clause_deviation_score": deviation,
    }


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze-contract", tags=["contract analysis"])
def analyze_contract(request: ContractAnalysisRequest) -> dict[str, Any]:
    """Run CRA, CL, and COI, plus LE when requested, on supplied contract text."""
    from ingestion_pipeline.contract_ingestion import ingest_contract_bytes

    filename = request.filename.strip() or "contract.txt"
    if "." not in filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]:
        filename += ".txt"
    elif not filename.casefold().endswith(".txt"):
        raise HTTPException(status_code=422, detail="contract_text is plaintext; filename must end in .txt.")
    try:
        document = ingest_contract_bytes(filename, request.contract_text.encode("utf-8"))
        litigation_state = None
        if request.include_litigation_exposure:
            from litigation_agent.intake import parse_litigation_payload

            litigation_state = parse_litigation_payload({
                "entities": request.entities,
                "graph_results": {},
                "clause_deviation_score": request.clause_deviation_score,
            })
            litigation_state.contract_text = document["plaintext"]
        report = _pipeline().analyze(
            document,
            litigation_state=litigation_state,
            coi_parties=request.parties.model_dump(exclude_none=True) if request.parties else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        from agents.coi.graph_manager import GraphQueryError
        from neo4j.exceptions import DriverError, Neo4jError

        if isinstance(exc, (GraphQueryError, DriverError, Neo4jError)):
            raise HTTPException(status_code=503, detail="Contract ingestion failed because Neo4j is unavailable.") from exc
        # Return a useful error class without exposing local paths or tracebacks.
        raise HTTPException(status_code=500, detail=f"Analysis failed ({type(exc).__name__}).") from exc
    return jsonable_encoder(report)


class WebPartyRequest(BaseModel):
    doc_id: str = "browser-scan"
    client_entity: str = Field(min_length=1)
    counterparty_entity: str = Field(min_length=1)
    contract_entities: list[str] = Field(default_factory=list)
    additional_entities: list[str] = Field(default_factory=list)


class WebReviewRequest(WebPartyRequest):
    contract_text: str = Field(min_length=1, max_length=120_000)
    features: dict[str, Any] = Field(default_factory=dict)
    clause_deviation_override: float | None = Field(default=None, ge=0, le=1)


class WebTextRequest(BaseModel):
    contract_text: str = Field(min_length=1, max_length=120_000)
    doc_id: str | None = None


class WebRiskRequest(WebPartyRequest):
    litigation_entities: dict[str, Any]
    clause_deviation_score: float = Field(ge=0, le=1)


class WebLitigationRequest(BaseModel):
    entities: dict[str, Any]
    graph_results: dict[str, Any]
    clause_deviation_score: float = Field(ge=0, le=1)


@app.get("/api/status", tags=["browser"])
def web_status() -> dict[str, str]:
    """Adapt the existing initialization and health checkpoints for the UI."""
    names = {"coi": "COI", "cr": "CRA", "cl": "CL", "le": "LE"}
    statuses = {}
    for code, agent in names.items():
        if code == "cr" and _standalone_cr_predictor.cache_info().currsize:
            statuses[code] = "ready"
            continue
        initialized = _initialization["agents"].get(agent)
        checked = _agent_health.get("agents", {}).get(agent, {}).get("status")
        statuses[code] = (
            "unavailable" if checked == "unavailable" or initialized == "error"
            else "ready" if initialized == "ready"
            else "initializing" if initialized in {"loading", "pending"} and _initialization["status"] == "initializing"
            else "not_started"
        )
    return statuses


@app.post("/api/extract", tags=["browser"])
async def web_extract(file: UploadFile = File(...)) -> dict[str, Any]:
    """Preview uploaded text without adding the document to the KG."""
    from ingestion_pipeline.document_input import MAX_FILE_BYTES, extract_text

    content = await file.read(MAX_FILE_BYTES + 1)
    try:
        extracted = extract_text(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"filename": Path(file.filename or "").name, "text": extracted,
            "characters": len(extracted)}


def _web_ingest(text: str):
    from ingestion_pipeline.contract_ingestion import ingest_contract_bytes
    from agents.coi.graph_manager import GraphQueryError
    from neo4j.exceptions import DriverError, Neo4jError

    try:
        return ingest_contract_bytes("browser-contract.txt", text.encode("utf-8"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (GraphQueryError, DriverError, Neo4jError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Contract ingestion could not update Neo4j.") from exc


@lru_cache(maxsize=1)
def _standalone_cr_predictor():
    from models.inference import ContractRiskPredictor

    return ContractRiskPredictor()


def _web_coi(request: WebPartyRequest) -> dict[str, Any]:
    from agents.coi.conflict_agent import ConflictOfInterestAgent

    try:
        return ConflictOfInterestAgent().run(
            client_entity=request.client_entity,
            counterparty_entity=request.counterparty_entity,
            contract_entities=request.contract_entities,
            additional_entities=request.additional_entities,
            doc_id=request.doc_id,
        ).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _web_le(entities: dict[str, Any], graph_results: dict[str, Any], deviation: float) -> dict[str, Any]:
    from litigation_agent.agent.litigation_agent import LitigationExposureAgent
    from litigation_agent.intake import parse_litigation_payload

    try:
        state = parse_litigation_payload({"entities": entities, "graph_results": graph_results,
                                          "clause_deviation_score": deviation})
        return LitigationExposureAgent().predict_with_explanation(state)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _redact_confidentiality(report: dict[str, Any]) -> dict[str, Any]:
    from agents.cl.confidentiality_leakage.masker import mask_value

    return {**report, "findings": [
        {**finding, "value": mask_value(finding.get("type", ""), finding.get("value", ""))}
        for finding in report.get("findings", [])
    ]}


@app.post("/api/coi/check", tags=["browser"])
def web_coi_check(request: WebPartyRequest) -> dict[str, Any]:
    return _web_coi(request)


@app.post("/api/le/predict", tags=["browser"])
def web_le_predict(request: WebLitigationRequest) -> dict[str, Any]:
    return _web_le(request.entities, request.graph_results, request.clause_deviation_score)


@app.post("/api/risk/assess", tags=["browser"])
def web_risk_assess(request: WebRiskRequest) -> dict[str, Any]:
    coi = _web_coi(request)
    if coi["status"] != "complete" or coi["conflict_flag"] is None:
        return {"status": "partial", "coi": coi, "litigation": None,
                "reason": "Litigation scoring requires a completed COI graph check."}
    litigation = _web_le(request.litigation_entities, {"conflict_flag": coi["conflict_flag"]},
                         request.clause_deviation_score)
    return {"status": "complete", "coi": coi, "litigation": litigation}


@app.post("/api/cl/analyze", tags=["browser"])
def web_cl_analyze(request: WebTextRequest) -> dict[str, Any]:
    from agents.cl.confidentiality_leakage import ConfidentialityLeakageAgent

    document = _web_ingest(request.contract_text)
    result = ConfidentialityLeakageAgent().analyze(
        doc_id=document["contract_id"], clauses=document["clauses"]
    ).model_dump()
    return jsonable_encoder({"status": "complete", **_redact_confidentiality(result)})


@app.post("/api/cr/analyze", tags=["browser"])
def web_cr_analyze(request: WebTextRequest) -> dict[str, Any]:
    document = _web_ingest(request.contract_text)
    eligible = [clause for clause in document["clauses"] if len(clause["text"].split()) >= 5]
    try:
        predictor = (_pipeline_instance.contract_risk.predictor if _pipeline_instance
                     else _standalone_cr_predictor())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Clause model unavailable ({type(exc).__name__}).") from exc
    clauses = []
    for clause in eligible[:12]:
        try:
            model = predictor.predict(clause["text"])
            prediction = str(model.get("prediction", ""))
            if prediction.casefold() == "baseline":
                model = {**model, "prediction": "Seed"}
            clauses.append({"clause_id": clause["clause_id"], "model": model})
        except Exception as exc:
            clauses.append({"clause_id": clause["clause_id"], "reason": type(exc).__name__})
    return jsonable_encoder({
        "status": "complete" if all("model" in clause for clause in clauses) else "partial",
        "clauses": clauses, "omitted_clause_count": len(eligible[12:]),
        "model_note": "LegalBERT labels are risk signals, not calibrated probabilities.",
    })


@app.post("/api/analyze", tags=["browser"])
def web_analyze(request: WebReviewRequest) -> dict[str, Any]:
    try:
        party_hints = PartyInput(client=request.client_entity,
                                 counterparty=request.counterparty_entity,
                                 additional=request.contract_entities + request.additional_entities)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    report = analyze_contract(ContractAnalysisRequest(
        filename="browser-contract.txt", contract_text=request.contract_text,
        parties=party_hints,
        include_litigation_exposure=request.clause_deviation_override is not None,
        entities=request.features,
        clause_deviation_score=request.clause_deviation_override,
    ))
    graph = report["coi"].get("graph_result") or {
        "status": "unknown", "conflict_detected": False,
        "severity": "UNKNOWN", "reason": "COI graph check did not run.",
    }
    graph = {**graph, "clause_findings": report["coi"].get("clause_findings", []),
             "entities": report["coi"].get("entities", []),
             "party_roles": report["coi"].get("party_roles", {})}
    clauses = []
    for clause in report["clauses"]:
        model = (clause.get("cra") or {}).get("model")
        if model and str(model.get("prediction", "")).casefold() == "baseline":
            model = {**model, "prediction": "Seed"}
        clauses.append({"clause_id": clause["clause_id"], "model": model,
                        **({"reason": clause["cra_error"]} if clause.get("cra_error") else {})})
    cr = {"status": "partial" if report["summary"]["clauses_failed"] else "complete",
          "clauses": clauses, "omitted_clause_count": report["summary"]["clauses_skipped"]}
    cl = {"status": "complete", **_redact_confidentiality(report["confidentiality"])}
    le_report = report["litigation_exposure"]
    le = le_report if le_report.get("status") == "complete" and graph.get("status") == "complete" else None
    reasons = []
    if graph.get("status") != "complete":
        reasons.append("COI graph evidence is incomplete or unverified.")
    if graph.get("conflict_detected"):
        reasons.append("A potential conflict path needs human review.")
    if graph["clause_findings"]:
        reasons.append("A clause contains a potential conflict pattern that needs verification.")
    if cr["status"] != "complete":
        reasons.append("Some clauses could not be classified.")
    if report["confidentiality"].get("risk_level") == "HIGH":
        reasons.append("High confidentiality risk was reported.")
    if le is None:
        reasons.append("Litigation exposure was not scored.")
    if not reasons:
        reasons.append("Automated findings require human assessment.")
    return jsonable_encoder({
        "doc_id": report["contract_id"],
        "status": "complete" if graph.get("status") == "complete" and cr["status"] == "complete" and le else "partial",
        "coi": graph, "cr": cr, "cl": cl, "le": le,
        "le_status": ("skipped: COI incomplete" if le_report.get("status") == "complete" and le is None
                      else le_report.get("status", "not_requested")),
        "decision": {"human_review_required": report["summary"]["human_review_required"],
                     "reasons": reasons, "limitations": []},
        "graph_update": report.get("metadata", {}).get("graph_update"),
    })
