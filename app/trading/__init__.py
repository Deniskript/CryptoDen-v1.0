"""
Trading Module — Модуль торговли

Включает:
- TradeManager — управление сделками
- Trade — модель сделки
- Trailing Stop — автоматический трейлинг
"""

from app.trading.trade_manager import (
    Trade,
    TradeStatus,
    CloseReason,
    TradeManager,
    trade_manager,
)

__all__ = [
    'Trade',
    'TradeStatus',
    'CloseReason',
    'TradeManager',
    'trade_manager',
]
