from datetime import datetime, timezone, timedelta
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from src.stalcraft_market_analyzer.storage.models import PriceHistory
from src.stalcraft_market_analyzer.storage.db import SessionLocal

def save_price_record(item_id: str, item_name: str, price: float, volume: int, source: str = "manual") -> bool:
    with SessionLocal() as session:
        try:
            new_record = PriceHistory(
                item_id=item_id,
                item_name=item_name,
                price=price,
                volume=volume,
                source=source,
                observed_at=datetime.now(timezone.utc)
            )
            session.add(new_record)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Błąd zapisu do bazy: {e}")
            return False

def get_average_price_7d(item_id: str) -> float:
    with SessionLocal() as session:
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        result = session.query(func.avg(PriceHistory.price)).filter(
            and_(
                PriceHistory.item_id == item_id,
                PriceHistory.observed_at >= seven_days_ago
            )
        ).scalar()
        return float(result) if result else 0.0