from __future__ import annotations

from pathlib import Path

from api import ops_state


def test_ops_state_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    ops_state.record_job_run(
        path=path,
        job_key="ingestion",
        status="ok",
        message="done",
        duration_ms=12.5,
        detail={"x": 1},
    )
    loaded = ops_state.load_ops_state(path)
    jobs = loaded.get("jobs", {})
    assert isinstance(jobs, dict)
    assert jobs["ingestion"]["status"] == "ok"
    assert jobs["ingestion"]["message"] == "done"
    assert jobs["ingestion"]["detail"] == {"x": 1}


def test_clear_stuck_jobs_removes_only_errors(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    ops_state.record_job_run(
        path=path,
        job_key="ingestion",
        status="error",
        message="failed",
        duration_ms=1.0,
        detail={},
    )
    ops_state.record_job_run(
        path=path,
        job_key="pipeline",
        status="ok",
        message="ok",
        duration_ms=1.0,
        detail={},
    )
    removed = ops_state.clear_stuck_jobs(path)
    assert removed == 1
    jobs = ops_state.load_ops_state(path).get("jobs", {})
    assert "ingestion" not in jobs
    assert jobs["pipeline"]["status"] == "ok"
