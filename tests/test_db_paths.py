from __future__ import annotations

from pathlib import Path

from stalcraft_market_analyzer.core.config import load_config
from stalcraft_market_analyzer.storage.db import create_database, db_ping, init_schema, prepare_sqlite_database_url


def test_prepare_sqlite_database_url_creates_parent_dir(tmp_path: Path) -> None:
    db_file = tmp_path / "nested" / "market.db"
    url = prepare_sqlite_database_url(f"sqlite:///{db_file.as_posix()}", project_root=tmp_path)
    assert db_file.parent.is_dir()
    db = create_database(url)
    init_schema(db)
    db_ping(db)


def test_load_config_creates_data_dir_for_default_sqlite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = load_config(project_root=tmp_path)
    assert Path(cfg.database_url.split("///", 1)[-1]).parent.exists()
    assert cfg.raw_output_dir.is_dir()
