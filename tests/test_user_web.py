from __future__ import annotations

from fastapi.testclient import TestClient

from api.user_web import _decorate_market_row, app


def test_user_web_home_smoke() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Stalcraft Market" in response.text


def test_user_web_deals_smoke() -> None:
    client = TestClient(app)
    response = client.get("/deals")
    assert response.status_code == 200
    assert "Hot Deals" in response.text


def test_user_web_artifacts_smoke() -> None:
    client = TestClient(app)
    response = client.get("/artifacts")
    assert response.status_code == 200
    assert "Artifacts" in response.text


def test_user_web_updates_smoke() -> None:
    client = TestClient(app)
    response = client.get("/updates")
    assert response.status_code == 200
    assert "Updates" in response.text


def test_user_web_displays_unknown_artifact_as_artifact() -> None:
    row = _decorate_market_row(
        {
            "item_id": "a1",
            "item_name": "Artifact",
            "rarity": "unknown",
            "category": "artefact/thermal",
            "is_artifact": True,
        }
    )
    assert row["rarity_display"] == "artifact"
    assert row["rarity_class"] == "artifact"


def test_sort_artifact_rows_by_rarity() -> None:
    from api.user_web import _sort_artifact_rows

    rows = [
        {"item_name": "B", "rarity": "common"},
        {"item_name": "A", "rarity": "legendary"},
    ]
    sorted_rows = _sort_artifact_rows(rows, sort="rarity")
    assert sorted_rows[0]["rarity"] == "legendary"
    assert sorted_rows[1]["rarity"] == "common"
