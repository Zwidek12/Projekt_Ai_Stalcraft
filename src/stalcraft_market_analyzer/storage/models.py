from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String(50), index=True)
    item_name: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(30))
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class PatchAnalysis(Base):
    __tablename__ = "patch_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    patch_version: Mapped[str] = mapped_column(String(50), unique=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    raw_summary: Mapped[str] = mapped_column(Text)
    buffed_items: Mapped[str] = mapped_column(Text) 
    nerfed_items: Mapped[str] = mapped_column(Text)
    neutral_items: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)

class Alerts(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(String(50))
    alert_type: Mapped[str] = mapped_column(String(50))
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))