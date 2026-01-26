"""
Calendar - Календарь экономических событий
==========================================

Отслеживает FOMC, CPI, NFP и другие важные события.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum


class EventImportance(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EconomicEvent:
    """Экономическое событие"""
    name: str
    datetime: datetime
    importance: EventImportance
    description: str = ""
    
    @property
    def hours_until(self) -> float:
        """Часов до события"""
        delta = self.datetime - datetime.utcnow()
        return delta.total_seconds() / 3600


class EventCalendar:
    """Календарь событий"""
    
    # Известные события (можно обновлять)
    # TODO: Загружать из внешнего источника
    KNOWN_EVENTS = [
        # Пример событий (обновить актуальными датами)
        EconomicEvent(
            name="FOMC Meeting",
            datetime=datetime(2026, 1, 29, 19, 0),
            importance=EventImportance.CRITICAL,
            description="Federal Reserve interest rate decision"
        ),
        EconomicEvent(
            name="CPI Report",
            datetime=datetime(2026, 2, 12, 13, 30),
            importance=EventImportance.HIGH,
            description="Consumer Price Index"
        ),
    ]
    
    def __init__(self):
        self._events = self.KNOWN_EVENTS.copy()
    
    def get_upcoming(self, hours: int = 24) -> List[EconomicEvent]:
        """Получить события в ближайшие N часов"""
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours)
        
        return [
            e for e in self._events
            if now <= e.datetime <= cutoff
        ]
    
    def get_critical_events(self, hours: int = 4) -> List[EconomicEvent]:
        """Получить критические события"""
        upcoming = self.get_upcoming(hours)
        return [
            e for e in upcoming
            if e.importance in [EventImportance.HIGH, EventImportance.CRITICAL]
        ]
    
    def should_stop_trading(self) -> tuple[bool, str]:
        """Проверить нужно ли остановить торговлю"""
        critical = self.get_critical_events(hours=2)  # За 2 часа до события
        
        if critical:
            event = critical[0]
            return True, f"{event.name} in {event.hours_until:.1f}h"
        
        return False, ""
    
    def add_event(self, event: EconomicEvent):
        """Добавить событие"""
        self._events.append(event)
        self._events.sort(key=lambda e: e.datetime)
    
    def clear_past_events(self):
        """Удалить прошедшие события"""
        now = datetime.utcnow()
        self._events = [e for e in self._events if e.datetime > now]


# Глобальный экземпляр
event_calendar = EventCalendar()
