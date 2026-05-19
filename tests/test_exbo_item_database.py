from __future__ import annotations

from pathlib import Path

from stalcraft_market_analyzer.ingestion.exbo_item_database import (
    _load_cached_rarity_index,
    _rarity_from_item_payload,
)


def test_exbo_item_payload_ignores_common_tooltip_quality() -> None:
    payload = {
        "id": "wg3p",
        "color": "DEFAULT",
        "infoBlocks": [
            {
                "type": "list",
                "elements": [
                    {
                        "type": "key-value",
                        "key": {"type": "translation", "key": "core.quality.common"},
                        "value": {"type": "translation", "key": "stalker.tooltip.artefact.not_probed"},
                    }
                ],
            }
        ],
    }

    assert _rarity_from_item_payload(payload) == "unknown"


def test_exbo_item_payload_falls_back_to_color() -> None:
    assert _rarity_from_item_payload({"id": "x1", "color": "legendary"}) == "legendary"


def test_load_cached_rarity_index_normalizes_values(tmp_path: Path) -> None:
    cache = tmp_path / "rarities.json"
    cache.write_text('{"a1": "core.quality.common", "a2": "unknown", "a3": "gold"}', encoding="utf-8")

    assert _load_cached_rarity_index(cache) == {"a1": "common", "a3": "legendary"}
