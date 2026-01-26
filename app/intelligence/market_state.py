"""
Market State - Состояние рынка
==============================

Определяет можно ли торговать на основе новостей и событий.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum


class TradingStatus(Enum):
    NORMAL = "normal"           # Торговля разрешена
    CAUTION = "caution"         # Осторожно
    BLOCKED = "blocked"         # Торговля заблокирована
    LONGS_BLOCKED = "longs_blocked"
    SHORTS_BLOCKED = "shorts_blocked"


@dataclass
class MarketState:
    """Состояние рынка"""
    status: TradingStatus = TradingStatus.NORMAL
    reason: str = ""
    
    # Блокировки
    trading_stopped: bool = False
    longs_blocked: bool = False
    shorts_blocked: bool = False
    
    # Буст от позитивных новостей
    longs_boosted: bool = False
    longs_boost_percent: int = 0
    
    # Критические события
    critical_event: Optional[str] = None
    event_time: Optional[datetime] = None
    
    # Последние новости
    recent_news: List[str] = field(default_factory=list)
    
    def can_trade(self, direction: str = None) -> tuple[bool, str]:
        """
        Проверить можно ли торговать
        
        Returns:
            (can_trade, reason)
        """
        if self.trading_stopped:
            return False, f"Trading stopped: {self.reason}"
        
        if direction == "LONG" and self.longs_blocked:
            return False, f"LONGs blocked: {self.reason}"
        
        if direction == "SHORT" and self.shorts_blocked:
            return False, f"SHORTs blocked: {self.reason}"
        
        return True, "OK"
    
    def get_boost(self, direction: str) -> int:
        """Получить буст для направления"""
        if direction == "LONG" and self.longs_boosted:
            return self.longs_boost_percent
        return 0


class MarketStateManager:
    """Менеджер состояния рынка"""
    
    def __init__(self):
        self._state = MarketState()
    
    def get_state(self) -> MarketState:
        """Получить текущее состояние"""
        return self._state
    
    def block_trading(self, reason: str):
        """Заблокировать торговлю"""
        self._state.trading_stopped = True
        self._state.status = TradingStatus.BLOCKED
        self._state.reason = reason
    
    def unblock_trading(self):
        """Разблокировать торговлю"""
        self._state.trading_stopped = False
        self._state.status = TradingStatus.NORMAL
        self._state.reason = ""
    
    def block_longs(self, reason: str):
        """Заблокировать LONGs"""
        self._state.longs_blocked = True
        self._state.status = TradingStatus.LONGS_BLOCKED
        self._state.reason = reason
    
    def block_shorts(self, reason: str):
        """Заблокировать SHORTs"""
        self._state.shorts_blocked = True
        self._state.status = TradingStatus.SHORTS_BLOCKED
        self._state.reason = reason
    
    def boost_longs(self, percent: int, reason: str = ""):
        """Добавить буст для LONGs"""
        self._state.longs_boosted = True
        self._state.longs_boost_percent = percent
        self._state.reason = reason
    
    def set_critical_event(self, event: str, event_time: datetime):
        """Установить критическое событие"""
        self._state.critical_event = event
        self._state.event_time = event_time
        self.block_trading(f"Critical event: {event}")
    
    def add_news(self, headline: str):
        """Добавить новость"""
        self._state.recent_news.insert(0, headline)
        self._state.recent_news = self._state.recent_news[:10]  # Keep last 10
    
    def reset(self):
        """Сбросить состояние"""
        self._state = MarketState()


# Глобальный экземпляр
market_state = MarketStateManager()
