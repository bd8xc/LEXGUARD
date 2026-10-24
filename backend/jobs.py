"""Single-worker contract jobs with replayable progress history."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from agents.contract_coordinator import ContractAnalysisRuntime, OUTPUT_DIR, analyze_contract


TERMINAL_STATES = {"complete", "failed"}


class ContractJobManager:
    """Keep local job state in memory and serialize model-heavy analyses."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lexguard-analysis")
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._runtime: ContractAnalysisRuntime | None = None

    def set_runtime(self, runtime: ContractAnalysisRuntime) -> None:
        """Install the once-loaded model/RAG objects used by every web job."""
        with self._lock:
            self._runtime = runtime

    def submit(self, file_path: Path, operator_input: dict[str, Any]) -> str:
        job_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._condition:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "latest_progress": {
                    "stage": "queued",
                    "message": "Contract queued for analysis.",
                    "percent": 0,
                },
                "result": None,
                "error": None,
                "events": [],
            }
            self._append_event_locked(job_id, "progress", self._jobs[job_id]["latest_progress"])
        self._executor.submit(self._run, job_id, file_path, operator_input)
        return job_id

    def _append_event_locked(self, job_id: str, event_type: str, data: dict[str, Any]) -> None:
        job = self._jobs[job_id]
        event_id = len(job["events"]) + 1
        data = {**data, "job_id": job_id}
        event = {"id": event_id, "type": event_type, "data": data}
        job["events"].append(event)
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        if event_type == "progress":
            job["latest_progress"] = data
        self._condition.notify_all()

    def _publish_progress(self, job_id: str, event: dict[str, Any]) -> None:
        with self._condition:
            if job_id not in self._jobs:
                return
            self._append_event_locked(job_id, "progress", dict(event))

    def _run(self, job_id: str, file_path: Path, operator_input: dict[str, Any]) -> None:
        with self._condition:
            job = self._jobs[job_id]
            runtime = self._runtime
            job["status"] = "running"
            self._append_event_locked(job_id, "progress", {
                "stage": "running",
                "message": "Analysis started.",
                "percent": 0,
            })
        try:
            result = analyze_contract(
                file_path,
                operator_input,
                progress_callback=lambda event: self._publish_progress(job_id, event),
                runtime=runtime,
            )
            with self._condition:
                job = self._jobs[job_id]
                job["status"] = "complete"
                job["result"] = result
                self._append_event_locked(job_id, "complete", {
                    "stage": "complete",
                    "message": "Contract analysis finished.",
                    "percent": 100,
                })
        except Exception as exc:
            # The exception detail is local diagnostic information; contract text is never logged here.
            message = f"Analysis failed ({type(exc).__name__}): {exc}"
            with self._condition:
                job = self._jobs[job_id]
                job["status"] = "failed"
                job["error"] = message
                self._append_event_locked(job_id, "failed", {
                    "stage": "failed",
                    "message": message,
                    "percent": job["latest_progress"].get("percent", 0),
                })

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {
                key: value
                for key, value in job.items()
                if key != "events"
            }

    def wait_for_events(self, job_id: str, after_id: int, timeout: float = 15.0):
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                return [], "missing"
            if len(job["events"]) <= after_id and job["status"] not in TERMINAL_STATES:
                self._condition.wait(timeout=timeout)
                job = self._jobs.get(job_id)
                if job is None:
                    return [], "missing"
            events = [event for event in job["events"] if event["id"] > after_id]
            return events, job["status"]

    def report_path(self, job_id: str, kind: str) -> Path | None:
        if kind not in {"json", "pdf"}:
            return None
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] != "complete" or not job.get("result"):
                return None
            raw_path = (job["result"].get("outputs") or {}).get(kind)

        if not raw_path:
            return None
        candidate = Path(raw_path).resolve()
        output_root = OUTPUT_DIR.resolve()
        if not candidate.is_relative_to(output_root) or not candidate.is_file():
            return None
        return candidate

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
