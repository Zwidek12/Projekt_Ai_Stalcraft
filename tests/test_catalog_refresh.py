from __future__ import annotations

from pathlib import Path

from stalcraft_market_analyzer.ingestion.catalog import (
    apply_artifact_rarity_overrides,
    build_catalog_refresh_summary,
    load_artifact_rarity_overrides,
    parse_stalcraftdb_catalog_listing,
)


def test_parse_stalcraftdb_catalog_listing_extracts_artifacts() -> None:
    payload = {
        "artifacts": [
            {
                "id": "a1",
                "name": {"lines": {"en": "Gold Spiral"}},
                "rarity": "legendary",
            },
            {
                "id": "a2",
                "name": {"lines": {"en": "Red Shell"}},
                "color": "red",
            },
        ],
        "weapons": [
            {
                "id": "w1",
                "name": {"lines": {"en": "Rifle"}},
                "rarity": "common",
            }
        ],
    }

    items = parse_stalcraftdb_catalog_listing(
        payload=payload,
        base_url="https://stalcraftdb.net/eu",
        region="eu",
    )

    assert len(items) == 3
    gold = next(item for item in items if item["item_id"] == "a1")
    assert gold["item_name"] == "Gold Spiral"
    assert gold["rarity"] == "legendary"
    assert gold["is_artifact"] is True
    assert str(gold["external_url"]).endswith("/eu/items/a1")

    rifle = next(item for item in items if item["item_id"] == "w1")
    assert rifle["is_artifact"] is False

    summary = build_catalog_refresh_summary(items)
    assert summary["items"] == 3
    assert summary["artifacts"] == 2
    assert summary["hot_artifacts"] == 2


def test_parse_stalcraftdb_catalog_listing_handles_nested_items_key() -> None:
    payload = {
        "group": {
            "items": [
                {
                    "itemId": "x1",
                    "name": "Pink Artifact",
                    "grade": "pink",
                    "category": "artifact",
                }
            ]
        }
    }

    items = parse_stalcraftdb_catalog_listing(payload=payload, base_url="https://stalcraftdb.net/eu", region="eu")

    assert items == [
        {
            "item_id": "x1",
            "item_name": "Pink Artifact",
            "rarity": "special",
            "category": "artifact",
            "external_url": "https://stalcraftdb.net/eu/items/x1",
            "is_artifact": True,
        }
    ]


def test_artifact_rarity_overrides(tmp_path: Path) -> None:
    items = [
        {
            "item_id": "x1",
            "item_name": "Artifact",
            "rarity": "unknown",
            "category": "artefact/thermal",
            "external_url": "",
            "is_artifact": True,
        }
    ]
    path = tmp_path / "overrides.json"
    path.write_text('[{"item_id": "x1", "rarity": "legendary"}]', encoding="utf-8")

    overrides = load_artifact_rarity_overrides(path)
    updated = apply_artifact_rarity_overrides(items=items, overrides=overrides)

    assert updated[0]["rarity"] == "legendary"
    assert updated[0]["is_artifact"] is True
    assert build_catalog_refresh_summary(updated)["hot_artifacts"] == 1


def test_artifact_rarity_enrichment_only_fills_unknown() -> None:
    from stalcraft_market_analyzer.ingestion.catalog import apply_artifact_rarity_enrichment

    items = [
        {
            "item_id": "x1",
            "item_name": "Artifact",
            "rarity": "unknown",
            "category": "artefact/thermal",
            "external_url": "",
            "is_artifact": True,
        },
        {
            "item_id": "x2",
            "item_name": "Known Artifact",
            "rarity": "exclusive",
            "category": "artefact/thermal",
            "external_url": "",
            "is_artifact": True,
        },
    ]

    updated = apply_artifact_rarity_enrichment(
        items=items,
        rarity_by_item_id={"x1": "core.quality.common", "x2": "common"},
    )

    assert updated[0]["rarity"] == "common"
    assert updated[1]["rarity"] == "exclusive"
