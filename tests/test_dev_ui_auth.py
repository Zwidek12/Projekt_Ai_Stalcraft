from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from api.dev_ui import app


def test_dev_ui_without_token_allows_dashboard(monkeypatch) -> None:
    # Keep this deterministic even when local .env contains DEV_UI_TOKEN.
    monkeypatch.setenv("DEV_UI_TOKEN", "")
    client = TestClient(app)
    response = client.get("/app")
    assert response.status_code == 200


def test_dev_ui_token_requires_basic_auth(monkeypatch) -> None:
    monkeypatch.setenv("DEV_UI_TOKEN", "secret")
    client = TestClient(app)
    response = client.get("/app")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers

    auth = base64.b64encode(b"admin:secret").decode("ascii")
    ok_response = client.get("/app", headers={"Authorization": f"Basic {auth}"})
    assert ok_response.status_code == 200
