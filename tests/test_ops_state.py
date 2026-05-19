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
