from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

JobStatus = Literal["ok", "error"]


def ops_state_path(project_root: Path) -> Path:
    return project_root / "data" / "dev_ops_state.json"


def load_ops_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "jobs": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Could not read ops state %s: %s", path, error)
        return {"version": 1, "jobs": {}}
    if not isinstance(raw, dict):
        return {"version": 1, "jobs": {}}
    jobs = raw.get("jobs")
    if not isinstance(jobs, dict):
        raw["jobs"] = {}
    return raw


def record_job_run(
    *,
    path: Path,
    job_key: str,
    status: JobStatus,
    message: str,
    duration_ms: float,
    detail: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = load_ops_state(path)
    jobs = state.setdefault("jobs", {})
    if not isinstance(jobs, dict):
        jobs = {}
        state["jobs"] = jobs

    finished_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "status": status,
        "finished_at": finished_at,
        "duration_ms": round(float(duration_ms), 2),
        "message": message[:4000],
        "detail": detail if isinstance(detail, dict) else {},
    }
    jobs[job_key] = payload
    state["updated_at"] = finished_at
    try:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as error:
        logger.warning("Could not write ops state %s: %s", path, error)

    logger.info(
        "DEV_UI job=%s status=%s duration_ms=%.0f msg=%s",
        job_key,
        status,
        float(duration_ms),
        message[:240].replace("\n", " "),
    )


def clear_stuck_jobs(path: Path) -> int:
    """
    Remove job entries stuck in error state (failed runs blocking the ops panel).
    """
    if not path.is_file():
        return 0
    state = load_ops_state(path)
    jobs = state.get("jobs")
    if not isinstance(jobs, dict):
        return 0

    removed = 0
    for key in list(jobs.keys()):
        entry = jobs.get(key)
        if isinstance(entry, dict) and str(entry.get("status", "")).lower() == "error":
            jobs.pop(key, None)
            removed += 1

    if removed:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as error:
            logger.warning("Could not write ops state %s: %s", path, error)
    return removed
