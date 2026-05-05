from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import Database
from .models import Alerts, PatchAnalysis, PriceHistory
from .repository_contract import IngestionBatch, PriceHistoryRepository, RepositoryPriceRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SqlAlchemyRepository(PriceHistoryRepository):
    db: Database

    def save_ingestion_batch(self, batch: IngestionBatch) -> int:
        inserted = 0
        with self.db.session_factory() as session:
            try:
                for record in batch.records:
                    inserted += _insert_price_record(session, batch=batch, record=record)
                session.commit()
                return inserted
            except Exception as error:
                session.rollback()
                logger.error("Failed to save ingestion batch %s: %s", batch.snapshot_id, error)
                raise

    def get_price_history_since(self, *, item_id: str, since: datetime) -> list[PriceHistory]:
        with self.db.session_factory() as session:
            stmt = (
                select(PriceHistory)
                .where(PriceHistory.item_id == item_id)
                .where(PriceHistory.observed_at >= since)
                .order_by(PriceHistory.observed_at.asc())
            )
            return list(session.execute(stmt).scalars().all())

    def get_average_price_7d(self, *, item_id: str, now: datetime | None = None) -> float | None:
        now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        since = now_utc - timedelta(days=7)
        rows = self.get_price_history_since(item_id=item_id, since=since)
        if not rows:
            return None
        return sum(row.price for row in rows) / len(rows)

    def save_alert(self, *, alert_type: str, fingerprint: str, payload: dict[str, object], item_id: str | None = None) -> bool:
        created_at = datetime.now(timezone.utc)
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self.db.session_factory() as session:
            try:
                session.add(
                    Alerts(
                        created_at=created_at,
                        alert_type=alert_type,
                        item_id=item_id,
                        fingerprint=fingerprint,
                        payload_json=payload_json,
                    )
                )
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False

    def save_patch_analysis(self, *, patch_version: str, analyzed_at: datetime, result: dict[str, object]) -> bool:
        result_json = json.dumps(result, ensure_ascii=False)
        with self.db.session_factory() as session:
            try:
                session.add(PatchAnalysis(patch_version=patch_version, analyzed_at=analyzed_at, result_json=result_json))
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False


def _insert_price_record(session: Session, *, batch: IngestionBatch, record: RepositoryPriceRecord) -> int:
    row = PriceHistory(
        snapshot_id=batch.snapshot_id,
        collected_at=batch.collected_at,
        item_id=record["item_id"],
        item_name=record["item_name"],
        price=record["price"],
        volume=record["volume"],
        observed_at=record["observed_at"],
        source=record["source"],
    )

    session.add(row)
    try:
        session.flush()
        return 1
    except IntegrityError:
        session.rollback()
        return 0

