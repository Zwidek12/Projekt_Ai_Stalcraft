from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    item_id: Mapped[str] = mapped_column(String(32), nullable=False)
    item_name: Mapped[str] = mapped_column(String(256), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    rarity: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "item_id",
            "observed_at",
            "price",
            "volume",
            name="uq_price_snapshot_item_time_price_volume",
        ),
        Index("ix_price_item_time", "item_id", "observed_at"),
    )


class Alerts(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)  # price_alert / patch_alert
    item_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)

    payload_json: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (UniqueConstraint("alert_type", "fingerprint", name="uq_alert_type_fingerprint"),)


class PatchAnalysis(Base):
    __tablename__ = "patch_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patch_version: Mapped[str] = mapped_column(String(64), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_json: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (UniqueConstraint("patch_version", name="uq_patch_version"),)


class ItemCatalog(Base):
    __tablename__ = "item_catalog"

    item_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    item_name: Mapped[str] = mapped_column(String(256), nullable=False)
    rarity: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    external_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    is_artifact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_item_catalog_name", "item_name"),
        Index("ix_item_catalog_rarity", "rarity"),
        Index("ix_item_catalog_artifact", "is_artifact"),
    )


class MarketDeal(Base):
    __tablename__ = "market_deals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    item_id: Mapped[str] = mapped_column(String(32), nullable=False)
    item_name: Mapped[str] = mapped_column(String(256), nullable=False)
    rarity: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    external_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    is_artifact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    avg_price_1d: Mapped[float] = mapped_column(Float, nullable=False)
    avg_price_7d: Mapped[float] = mapped_column(Float, nullable=False)
    deviation_pct: Mapped[float] = mapped_column(Float, nullable=False)
    deal_score: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("review_id", "item_id", name="uq_market_deal_review_item"),
        Index("ix_market_deal_active_score", "is_active", "deal_score"),
        Index("ix_market_deal_item_time", "item_id", "observed_at"),
        Index("ix_market_deal_rarity", "rarity"),
    )


class GameUpdate(Base):
    __tablename__ = "game_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    update_type: Mapped[str] = mapped_column(String(32), nullable=False, default="update")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False, default="")
    link_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    new_items_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_game_updates_published", "published_at"),
        Index("ix_game_updates_type", "update_type"),
    )

