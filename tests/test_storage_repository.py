from __future__ import annotations

from datetime import datetime, timezone

from stalcraft_market_analyzer.storage.db import create_database, init_schema
from stalcraft_market_analyzer.storage.repository import SqlAlchemyRepository
from stalcraft_market_analyzer.storage.repository_contract import IngestionBatch, RepositoryPriceRecord


def _batch(*, snapshot_id: str) -> IngestionBatch:
    now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
    record: RepositoryPriceRecord = {
        "item_id": "7lrz3",
        "item_name": "AK-103",
        "price": 123.0,
        "volume": 1,
        "observed_at": datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        "source": "stalcraftdb_auction",
        "rarity": "exclusive",
    }
    return IngestionBatch(snapshot_id=snapshot_id, collected_at=now, records=[record])


def test_save_ingestion_batch_dedupes_by_unique_key() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    batch = _batch(snapshot_id="snap1")
    inserted_1 = repo.save_ingestion_batch(batch)
    inserted_2 = repo.save_ingestion_batch(batch)

    assert inserted_1 == 1
    assert inserted_2 == 0


def test_get_average_price_7d_returns_value() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    batch = _batch(snapshot_id="snap2")
    repo.save_ingestion_batch(batch)

    avg = repo.get_average_price_7d(item_id="7lrz3", now=datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc))
    assert avg == 123.0

    observations = repo.get_price_observations_since(
        item_id="7lrz3",
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    assert observations[0]["rarity"] == "exclusive"


def test_count_alerts_since_and_recent() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    assert repo.save_alert(
        alert_type="price_anomaly",
        fingerprint="fp1",
        payload={"k": "v"},
        item_id="7lrz3",
    )
    assert repo.save_alert(
        alert_type="price_anomaly",
        fingerprint="fp2",
        payload={"k": "v2"},
        item_id="7lrz3",
    )

    since_past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert repo.count_alerts_since(since=since_past, alert_type="price_anomaly") == 2

    since_future = datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert repo.count_alerts_since(since=since_future, alert_type=None) == 0

    recent = repo.fetch_recent_alerts(limit=5)
    assert len(recent) == 2
    assert {str(r["fingerprint"]) for r in recent} == {"fp1", "fp2"}


def test_catalog_and_hot_deals_roundtrip() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
    changed = repo.upsert_item_catalog(
        items=[
            {
                "item_id": "art1",
                "item_name": "Red Artifact",
                "rarity": "red",
                "category": "artifact",
                "external_url": "https://example.test/items/art1",
                "is_artifact": True,
            }
        ],
        updated_at=now,
    )
    assert changed == 1

    search = repo.search_artifacts(query="red", rarity="red")
    assert len(search) == 1
    assert search[0]["item_id"] == "art1"

    saved = repo.save_market_deals(
        review_id="daily-test",
        created_at=now,
        deals=[
            {
                "item_id": "art1",
                "item_name": "Red Artifact",
                "rarity": "red",
                "category": "artifact",
                "external_url": "https://example.test/items/art1",
                "is_artifact": True,
                "current_price": 50.0,
                "avg_price_1d": 80.0,
                "avg_price_7d": 100.0,
                "deviation_pct": -50.0,
                "deal_score": 100.0,
                "observed_at": now,
                "source": "test",
            }
        ],
    )
    assert saved == 1

    hot = repo.get_hot_deals(rarities={"red"}, artifact_only=True)
    assert len(hot) == 1
    assert hot[0]["item_id"] == "art1"


def test_catalog_upsert_does_not_downgrade_high_rarity_to_unknown() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    repo.upsert_item_catalog(
        items=[
            {
                "item_id": "art1",
                "item_name": "Artifact",
                "rarity": "exclusive",
                "category": "artefact/thermal",
                "external_url": "https://example.test/items/art1",
                "is_artifact": True,
            }
        ]
    )
    repo.upsert_item_catalog(
        items=[
            {
                "item_id": "art1",
                "item_name": "Artifact",
                "rarity": "unknown",
                "category": "artefact/thermal",
                "external_url": "https://example.test/items/art1",
                "is_artifact": True,
            }
        ]
    )

    item = repo.get_catalog_item(item_id="art1")
    assert item is not None
    assert item["rarity"] == "exclusive"


def test_catalog_upsert_can_clear_misleading_common_rarity() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    repo.upsert_item_catalog(
        items=[
            {
                "item_id": "art1",
                "item_name": "Artifact",
                "rarity": "common",
                "category": "artefact/thermal",
                "external_url": "https://example.test/items/art1",
                "is_artifact": True,
            }
        ]
    )
    repo.upsert_item_catalog(
        items=[
            {
                "item_id": "art1",
                "item_name": "Artifact",
                "rarity": "unknown",
                "category": "artefact/thermal",
                "external_url": "https://example.test/items/art1",
                "is_artifact": True,
            }
        ]
    )

    item = repo.get_catalog_item(item_id="art1")
    assert item is not None
    assert item["rarity"] == "unknown"


def test_game_updates_roundtrip() -> None:
    db = create_database("sqlite+pysqlite:///:memory:")
    init_schema(db)
    repo = SqlAlchemyRepository(db=db)

    now = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
    update_id = repo.save_game_update(
        update={
            "update_type": "balance",
            "title": "Balance Patch",
            "summary": "Artifacts adjusted.",
            "link_url": "https://example.test/patch",
            "new_items": [{"item_id": "a1", "name": "New Artifact", "url": "https://example.test/a1"}],
            "published_at": now,
        },
        created_at=now,
    )

    assert update_id == 1
    latest = repo.get_latest_game_update()
    assert latest is not None
    assert latest["title"] == "Balance Patch"
    assert latest["update_type"] == "balance"
    assert latest["new_items"] == [{"item_id": "a1", "name": "New Artifact", "url": "https://example.test/a1"}]

    rows = repo.list_game_updates(update_type="balance")
    assert len(rows) == 1

