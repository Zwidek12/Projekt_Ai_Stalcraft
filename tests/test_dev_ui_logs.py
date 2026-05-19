from __future__ import annotations

from fastapi.testclient import TestClient

from api.dev_ui import app
from api.system_log import clear_system_logs, tail_system_logs
import logging


def test_dev_logs_api_returns_tail(monkeypatch) -> None:
    monkeypatch.setenv("DEV_UI_TOKEN", "")
    clear_system_logs()
    logging.getLogger("test.dev_ui_logs").warning("hello-from-test")
    client = TestClient(app)
    response = client.get("/dev/api/logs?limit=50")
    assert response.status_code == 200
    payload = response.json()
    assert any("hello-from-test" in line for line in payload["lines"])
    assert tail_system_logs(limit=5)
