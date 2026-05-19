from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import Database
from .models import Alerts, GameUpdate, ItemCatalog, MarketDeal, PatchAnalysis, PriceHistory
from .repository_contract import (
    CatalogItemInput,
    GameUpdateInput,
    IngestionBatch,
    MarketDealInput,
    PriceHistoryRepository,
    PriceObservation,
    RepositoryPriceRecord,
)

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

    def get_distinct_item_ids(self, *, since: datetime) -> list[str]:
        with self.db.session_factory() as session:
            stmt = (
                select(distinct(PriceHistory.item_id))
                .where(PriceHistory.observed_at >= since)
                .order_by(PriceHistory.item_id.asc())
            )
            return [str(value) for value in session.execute(stmt).scalars().all() if value]

    def get_observed_prices_since(self, *, item_id: str, since: datetime) -> list[float]:
        observations = self.get_price_observations_since(item_id=item_id, since=since)
        return [float(obs["price"]) for obs in observations]

    def get_price_observations_since(self, *, item_id: str, since: datetime) -> list[PriceObservation]:
        with self.db.session_factory() as session:
            stmt = (
                select(PriceHistory.price, PriceHistory.observed_at, PriceHistory.source, PriceHistory.rarity)
                .where(PriceHistory.item_id == item_id)
                .where(PriceHistory.observed_at >= since)
                .order_by(PriceHistory.observed_at.asc())
            )
            rows = session.execute(stmt).all()
            observations: list[PriceObservation] = []
            for price, observed_at, source, rarity in rows:
                observations.append(
                    PriceObservation(
                        price=float(price),
                        observed_at=observed_at,
                        source=str(source),
                        rarity=str(rarity or "unknown"),
                    )
                )
            return observations

    def save_alert(self, *, alert_type: str, fingerprint: str, payload: dict[str, object], item_id: str | None = None) -> bool:
        created_at = datetime.now(timezone.utc)
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)
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

    def has_recent_price_anomaly(self, *, item_id: str, since: datetime) -> bool:
        with self.db.session_factory() as session:
            stmt = select(
                exists().where(
                    Alerts.alert_type == "price_anomaly",
                    Alerts.item_id == item_id,
                    Alerts.created_at >= since,
                )
            )
            return bool(session.scalar(stmt))

    def count_alerts_since(self, *, since: datetime, alert_type: str | None = None) -> int:
        with self.db.session_factory() as session:
            stmt = select(func.count()).select_from(Alerts).where(Alerts.created_at >= since)
            if alert_type is not None:
                stmt = stmt.where(Alerts.alert_type == alert_type)
            value = session.scalar(stmt)
            return int(value or 0)

    def fetch_recent_alerts(self, *, limit: int = 12) -> list[dict[str, object]]:
        lim = max(1, min(int(limit), 200))
        with self.db.session_factory() as session:
            stmt = select(Alerts).order_by(Alerts.created_at.desc()).limit(lim)
            rows = session.scalars(stmt).all()
            out: list[dict[str, object]] = []
            for row in rows:
                out.append(
                    {
                        "created_at": row.created_at,
                        "alert_type": row.alert_type,
                        "fingerprint": row.fingerprint,
                        "item_id": row.item_id,
                    }
                )
            return out

    def upsert_item_catalog(self, *, items: list[CatalogItemInput], updated_at: datetime | None = None) -> int:
        now = updated_at or datetime.now(timezone.utc)
        changed = 0
        with self.db.session_factory() as session:
            for item in items:
                item_id = str(item.get("item_id", "")).strip()
                if not item_id:
                    continue
                item_name = str(item.get("item_name") or f"item_{item_id}").strip()
                incoming_rarity = str(item.get("rarity") or "unknown").strip().lower()
                category = str(item.get("category") or "unknown").strip().lower()
                external_url = str(item.get("external_url") or "").strip()
                is_artifact = bool(item.get("is_artifact", False))

                existing = session.get(ItemCatalog, item_id)
                if existing is None:
                    session.add(
                        ItemCatalog(
                            item_id=item_id,
                            item_name=item_name,
                            rarity=incoming_rarity,
                            category=category,
                            external_url=external_url,
                            is_artifact=is_artifact,
                            updated_at=now,
                        )
                    )
                    changed += 1
                    continue

                existing.item_name = item_name
                existing.rarity = _merged_catalog_rarity(
                    current=str(existing.rarity or "unknown"),
                    incoming=incoming_rarity,
                )
                existing.category = category
                existing.external_url = external_url
                existing.is_artifact = is_artifact
                existing.updated_at = now
                changed += 1
            session.commit()
        return changed

    def get_catalog_items(self, *, artifact_only: bool = False, limit: int = 10_000) -> list[dict[str, object]]:
        lim = max(1, min(int(limit), 50_000))
        with self.db.session_factory() as session:
            stmt = select(ItemCatalog).order_by(ItemCatalog.item_name.asc()).limit(lim)
            if artifact_only:
                stmt = stmt.where(ItemCatalog.is_artifact.is_(True))
            return [_catalog_row_to_dict(row) for row in session.scalars(stmt).all()]

    def search_artifacts(
        self,
        *,
        query: str = "",
        rarity: str = "",
        artifact_only: bool = True,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        lim = max(1, min(int(limit), 500))
        q = query.strip().lower()
        rarity_filter = rarity.strip().lower()
        with self.db.session_factory() as session:
            stmt = select(ItemCatalog).order_by(ItemCatalog.item_name.asc()).limit(lim)
            if artifact_only:
                stmt = stmt.where(ItemCatalog.is_artifact.is_(True))
            if rarity_filter:
                stmt = stmt.where(ItemCatalog.rarity == rarity_filter)
            if q:
                stmt = stmt.where(func.lower(ItemCatalog.item_name).like(f"%{q}%"))
            return [_catalog_row_to_dict(row) for row in session.scalars(stmt).all()]

    def get_catalog_item(self, *, item_id: str) -> dict[str, object] | None:
        with self.db.session_factory() as session:
            row = session.get(ItemCatalog, item_id)
            return _catalog_row_to_dict(row) if row is not None else None

    def save_market_deals(
        self,
        *,
        review_id: str,
        deals: list[MarketDealInput],
        created_at: datetime | None = None,
        replace_active: bool = True,
    ) -> int:
        now = created_at or datetime.now(timezone.utc)
        inserted = 0
        with self.db.session_factory() as session:
            if replace_active:
                session.execute(update(MarketDeal).values(is_active=False).where(MarketDeal.is_active.is_(True)))

            for deal in deals:
                duplicate = session.scalar(
                    select(
                        exists().where(
                            MarketDeal.review_id == review_id,
                            MarketDeal.item_id == deal["item_id"],
                        )
                    )
                )
                if duplicate:
                    continue
                row = MarketDeal(
                    review_id=review_id,
                    created_at=now,
                    item_id=deal["item_id"],
                    item_name=deal["item_name"],
                    rarity=deal["rarity"],
                    category=deal["category"],
                    external_url=deal["external_url"],
                    is_artifact=deal["is_artifact"],
                    current_price=deal["current_price"],
                    avg_price_1d=deal["avg_price_1d"],
                    avg_price_7d=deal["avg_price_7d"],
                    deviation_pct=deal["deviation_pct"],
                    deal_score=deal["deal_score"],
                    observed_at=deal["observed_at"],
                    source=deal["source"],
                    is_active=True,
                )
                session.add(row)
                inserted += 1
            session.commit()
        return inserted

    def get_hot_deals(
        self,
        *,
        rarities: set[str] | None = None,
        artifact_only: bool = True,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        lim = max(1, min(int(limit), 500))
        normalized_rarities = {value.strip().lower() for value in (rarities or set()) if value.strip()}
        with self.db.session_factory() as session:
            stmt = (
                select(MarketDeal)
                .where(MarketDeal.is_active.is_(True))
                .order_by(MarketDeal.deal_score.desc(), MarketDeal.deviation_pct.asc())
                .limit(lim)
            )
            if artifact_only:
                stmt = stmt.where(MarketDeal.is_artifact.is_(True))
            if normalized_rarities:
                stmt = stmt.where(MarketDeal.rarity.in_(normalized_rarities))
            return [_deal_row_to_dict(row) for row in session.scalars(stmt).all()]

    def get_latest_deal_for_item(self, *, item_id: str) -> dict[str, object] | None:
        with self.db.session_factory() as session:
            stmt = (
                select(MarketDeal)
                .where(MarketDeal.item_id == item_id)
                .where(MarketDeal.is_active.is_(True))
                .order_by(MarketDeal.created_at.desc())
                .limit(1)
            )
            row = session.scalars(stmt).first()
            return _deal_row_to_dict(row) if row is not None else None

    def get_item_price_history_1d(self, *, item_id: str, now: datetime | None = None) -> list[PriceObservation]:
        now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return self.get_price_observations_since(item_id=item_id, since=now_utc - timedelta(days=1))

    def save_game_update(self, *, update: GameUpdateInput, created_at: datetime | None = None) -> int:
        now = created_at or datetime.now(timezone.utc)
        published = update.get("published_at") or now
        with self.db.session_factory() as session:
            row = GameUpdate(
                update_type=str(update.get("update_type") or "update").strip().lower(),
                title=str(update.get("title") or "").strip(),
                summary=str(update.get("summary") or "").strip(),
                link_url=str(update.get("link_url") or "").strip(),
                new_items_json=json.dumps(update.get("new_items") or [], ensure_ascii=False, default=str),
                published_at=published,
                created_at=now,
            )
            session.add(row)
            session.commit()
            return int(row.id)

    def list_game_updates(self, *, update_type: str = "", limit: int = 20) -> list[dict[str, object]]:
        lim = max(1, min(int(limit), 200))
        with self.db.session_factory() as session:
            stmt = select(GameUpdate).order_by(GameUpdate.published_at.desc(), GameUpdate.id.desc()).limit(lim)
            normalized_type = update_type.strip().lower()
            if normalized_type:
                stmt = stmt.where(GameUpdate.update_type == normalized_type)
            return [_game_update_row_to_dict(row) for row in session.scalars(stmt).all()]

    def get_latest_game_update(self) -> dict[str, object] | None:
        rows = self.list_game_updates(limit=1)
        return rows[0] if rows else None


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
        rarity=record["rarity"],
    )

    session.add(row)
    try:
        session.flush()
        return 1
    except IntegrityError:
        session.rollback()
        return 0


def _merged_catalog_rarity(*, current: str, incoming: str) -> str:
    normalized_current = current.strip().lower() or "unknown"
    normalized_incoming = incoming.strip().lower() or "unknown"
    if normalized_current == "common" and normalized_incoming == "unknown":
        return "unknown"
    if normalized_incoming == "unknown" and normalized_current != "unknown":
        return normalized_current
    return normalized_incoming


def _catalog_row_to_dict(row: ItemCatalog) -> dict[str, object]:
    return {
        "item_id": row.item_id,
        "item_name": row.item_name,
        "rarity": row.rarity,
        "category": row.category,
        "external_url": row.external_url,
        "is_artifact": bool(row.is_artifact),
        "updated_at": row.updated_at,
    }


def _deal_row_to_dict(row: MarketDeal) -> dict[str, object]:
    return {
        "id": row.id,
        "review_id": row.review_id,
        "created_at": row.created_at,
        "item_id": row.item_id,
        "item_name": row.item_name,
        "rarity": row.rarity,
        "category": row.category,
        "external_url": row.external_url,
        "is_artifact": bool(row.is_artifact),
        "current_price": row.current_price,
        "avg_price_1d": row.avg_price_1d,
        "avg_price_7d": row.avg_price_7d,
        "deviation_pct": row.deviation_pct,
        "deal_score": row.deal_score,
        "observed_at": row.observed_at,
        "source": row.source,
        "is_active": bool(row.is_active),
    }


def _game_update_row_to_dict(row: GameUpdate) -> dict[str, object]:
    try:
        new_items = json.loads(row.new_items_json)
    except json.JSONDecodeError:
        new_items = []
    return {
        "id": row.id,
        "update_type": row.update_type,
        "title": row.title,
        "summary": row.summary,
        "link_url": row.link_url,
        "new_items": new_items if isinstance(new_items, list) else [],
        "published_at": row.published_at,
        "created_at": row.created_at,
    }

