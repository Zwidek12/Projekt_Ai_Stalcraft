from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
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

