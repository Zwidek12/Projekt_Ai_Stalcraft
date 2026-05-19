from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint:
    run_key: str
    next_batch_index: int
    failed_batches: tuple[int, ...]


def checkpoint_path(project_root: Path) -> Path:
    return project_root / "data" / "daily_workflow_checkpoint.json"


def build_run_key(*, region: str, artifact_only: bool, limit: int) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{day}|{region.strip().lower() or 'eu'}|artifact_only={int(bool(artifact_only))}|limit={int(limit)}"


def load_checkpoint(path: Path) -> WorkflowCheckpoint | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Ignoring corrupt workflow checkpoint %s: %s", path, error)
        return None
    if not isinstance(raw, dict):
        return None
    run_key = str(raw.get("run_key", "")).strip()
    if not run_key:
        return None
    failed_raw = raw.get("failed_batches", [])
    failed_batches: tuple[int, ...] = ()
    if isinstance(failed_raw, list):
        failed_batches = tuple(sorted({int(value) for value in failed_raw}))
    return WorkflowCheckpoint(
        run_key=run_key,
        next_batch_index=max(0, int(raw.get("next_batch_index", 0) or 0)),
        failed_batches=failed_batches,
    )


def save_checkpoint(path: Path, *, run_key: str, next_batch_index: int, failed_batches: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "run_key": run_key,
        "next_batch_index": max(0, int(next_batch_index)),
        "failed_batches": sorted({int(value) for value in failed_batches}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_checkpoint(path: Path) -> None:
    if path.is_file():
        try:
            path.unlink()
        except OSError as error:
            logger.warning("Could not remove workflow checkpoint %s: %s", path, error)
