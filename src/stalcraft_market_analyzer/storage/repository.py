# Na samej górze dopisz to do istniejących importów:
from src.stalcraft_market_analyzer.storage.models import Alerts
from typing import Optional
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

def log_alert_sent(item_id: str, alert_type: str = "PRICE_DROP") -> bool:
    """Zapisuje w bazie fakt wysłania powiadomienia, aby zapobiec spamowi."""
    with SessionLocal() as session:
        try:
            new_alert = Alerts(
                item_id=item_id,
                alert_type=alert_type,
                sent_at=datetime.now(timezone.utc)
            )
            session.add(new_alert)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Błąd zapisu logu alertu: {e}")
            return False

def can_send_alert(item_id: str, alert_type: str = "PRICE_DROP", cooldown_minutes: int = 60) -> bool:
    """
    Sprawdza, czy możemy wysłać powiadomienie (czy minął cooldown).
    Domyślny cooldown to 60 minut.
    """
    with SessionLocal() as session:
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        
        # Szukamy, czy w ciągu ostatnich 60 minut wysłaliśmy alert dla tego przedmiotu
        recent_alert = session.query(Alerts).filter(
            and_(
                Alerts.item_id == item_id,
                Alerts.alert_type == alert_type,
                Alerts.sent_at >= cutoff_time
            )
        ).first()
        
        # Jeśli recent_alert jest puste (None), to znaczy, że nie było spamu. Zwracamy True.
        return recent_alert is None