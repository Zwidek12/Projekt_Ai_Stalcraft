from __future__ import annotations

from pathlib import Path

from stalcraft_market_analyzer.core.workflow_checkpoint import (
    build_run_key,
    checkpoint_path,
    clear_checkpoint,
    load_checkpoint,
    save_checkpoint,
)


def test_workflow_checkpoint_roundtrip(tmp_path: Path) -> None:
    path = checkpoint_path(tmp_path)
    run_key = build_run_key(region="eu", artifact_only=True, limit=0)
    save_checkpoint(path, run_key=run_key, next_batch_index=2, failed_batches=[1])
    loaded = load_checkpoint(path)
    assert loaded is not None
    assert loaded.run_key == run_key
    assert loaded.next_batch_index == 2
    assert loaded.failed_batches == (1,)
    clear_checkpoint(path)
    assert load_checkpoint(path) is None
