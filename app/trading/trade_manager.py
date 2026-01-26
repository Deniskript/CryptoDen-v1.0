"""
Trade Manager — Управление сделками
- Открытие/закрытие позиций
- Автоматический SL/TP
- Trailing Stop
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import asyncio

from app.core.logger import logger
from app.strategies import Signal
from app.notifications import telegram_bot


class TradeStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class CloseReason(Enum):
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    MANUAL = "manual"
    EXPIRED = "expired"


@dataclass
class Trade:
    """Активная сделка"""
    id: str
    symbol: str
    direction: str  # LONG, SHORT
    
    # Цены
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    
    # Trailing Stop
    trailing_stop_enabled: bool = True
    trailing_stop_percent: float = 0.3  # Активируется после +0.3%
    trailing_stop_distance: float = 0.2  # Дистанция 0.2%
    highest_price: float = 0.0  # Для LONG
    lowest_price: float = float('inf')  # Для SHORT
    trailing_stop_price: Optional[float] = None
    
    # Размер
    quantity: float = 0.0
    value_usdt: float = 0.0
    
    # P&L
    unrealized_pnl: float = 0.0
    unrealized_pnl_percent: float = 0.0
    
    # Статус
    status: TradeStatus = TradeStatus.PENDING
    close_reason: Optional[CloseReason] = None
    
    # Время
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    
    # Стратегия
    strategy_id: str = ""
    strategy_name: str = ""
    win_rate: float = 0.0
    
    def update_price(self, new_price: float):
        """Обновить текущую цену и пересчитать P&L"""
        self.current_price = new_price
        
        # P&L расчёт
        if self.direction == "LONG":
            self.unrealized_pnl_percent = ((new_price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            self.unrealized_pnl_percent = ((self.entry_price - new_price) / self.entry_price) * 100
        
        self.unrealized_pnl = self.value_usdt * (self.unrealized_pnl_percent / 100)
        
        # Обновление trailing stop
        if self.trailing_stop_enabled:
            self._update_trailing_stop(new_price)
    
    def _update_trailing_stop(self, new_price: float):
        """Обновить trailing stop"""
        
        if self.direction == "LONG":
            # Обновляем максимум
            if new_price > self.highest_price:
                self.highest_price = new_price
            
            # Активируем trailing если прибыль >= trailing_stop_percent
            profit_from_entry = ((new_price - self.entry_price) / self.entry_price) * 100
            
            if profit_from_entry >= self.trailing_stop_percent:
                # Trailing stop = highest - distance%
                new_trailing = self.highest_price * (1 - self.trailing_stop_distance / 100)
                
                # Двигаем только вверх
                if self.trailing_stop_price is None or new_trailing > self.trailing_stop_price:
                    self.trailing_stop_price = new_trailing
                    logger.debug(f"📈 {self.symbol} Trailing SL moved to ${new_trailing:.4f}")
        
        else:  # SHORT
            # Обновляем минимум
            if new_price < self.lowest_price:
                self.lowest_price = new_price
            
            # Активируем trailing если прибыль >= trailing_stop_percent
            profit_from_entry = ((self.entry_price - new_price) / self.entry_price) * 100
            
            if profit_from_entry >= self.trailing_stop_percent:
                # Trailing stop = lowest + distance%
                new_trailing = self.lowest_price * (1 + self.trailing_stop_distance / 100)
                
                # Двигаем только вниз
                if self.trailing_stop_price is None or new_trailing < self.trailing_stop_price:
                    self.trailing_stop_price = new_trailing
                    logger.debug(f"📉 {self.symbol} Trailing SL moved to ${new_trailing:.4f}")
    
    def should_close(self) -> Optional[CloseReason]:
        """Проверить нужно ли закрывать позицию"""
        
        if self.direction == "LONG":
            # Take Profit
            if self.current_price >= self.take_profit:
                return CloseReason.TAKE_PROFIT
            
            # Stop Loss
            if self.current_price <= self.stop_loss:
                return CloseReason.STOP_LOSS
            
            # Trailing Stop
            if self.trailing_stop_price and self.current_price <= self.trailing_stop_price:
                return CloseReason.TRAILING_STOP
        
        else:  # SHORT
            # Take Profit
            if self.current_price <= self.take_profit:
                return CloseReason.TAKE_PROFIT
            
            # Stop Loss
            if self.current_price >= self.stop_loss:
                return CloseReason.STOP_LOSS
            
            # Trailing Stop
            if self.trailing_stop_price and self.current_price >= self.trailing_stop_price:
                return CloseReason.TRAILING_STOP
        
        return None
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'symbol': self.symbol,
            'direction': self.direction,
            'entry': self.entry_price,
            'current': self.current_price,
            'sl': self.stop_loss,
            'tp': self.take_profit,
            'trailing_sl': self.trailing_stop_price,
            'pnl': f"{self.unrealized_pnl_percent:+.2f}%",
            'status': self.status.value,
            'strategy': self.strategy_name,
        }


class TradeManager:
    """
    Менеджер сделок
    
    Функции:
    - Открытие позиций по сигналам
    - Мониторинг и обновление P&L
    - Автоматическое закрытие по SL/TP/Trailing
    """
    
    def __init__(self):
        self.active_trades: Dict[str, Trade] = {}  # trade_id -> Trade
        self.trade_history: List[Trade] = []
        self.trade_counter: int = 0
        
        # Настройки
        self.max_trades_per_symbol: int = 1
        self.max_total_trades: int = 5
        self.default_trade_value: float = 100.0  # USDT
        
        logger.info("TradeManager initialized")
    
    def _generate_trade_id(self, symbol: str) -> str:
        """Генерация ID сделки"""
        self.trade_counter += 1
        return f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.trade_counter}"
    
    def can_open_trade(self, symbol: str) -> tuple[bool, str]:
        """Проверить можно ли открыть сделку"""
        
        # Лимит на символ
        symbol_trades = [t for t in self.active_trades.values() if t.symbol == symbol]
        if len(symbol_trades) >= self.max_trades_per_symbol:
            return False, f"Max trades for {symbol} reached"
        
        # Общий лимит
        if len(self.active_trades) >= self.max_total_trades:
            return False, "Max total trades reached"
        
        return True, "OK"
    
    async def open_trade(self, signal: Signal, value_usdt: float = None) -> Optional[Trade]:
        """Открыть сделку по сигналу"""
        
        can_open, reason = self.can_open_trade(signal.symbol)
        if not can_open:
            logger.warning(f"Cannot open trade: {reason}")
            return None
        
        trade_id = self._generate_trade_id(signal.symbol)
        value = value_usdt or self.default_trade_value
        quantity = value / signal.entry_price
        
        trade = Trade(
            id=trade_id,
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=signal.entry_price,
            current_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            quantity=quantity,
            value_usdt=value,
            status=TradeStatus.OPEN,
            opened_at=datetime.utcnow(),
            strategy_id=signal.strategy_id,
            strategy_name=signal.strategy_name,
            win_rate=signal.win_rate,
            highest_price=signal.entry_price,
            lowest_price=signal.entry_price,
        )
        
        self.active_trades[trade_id] = trade
        
        logger.info(f"✅ Trade opened: {trade_id}")
        logger.info(f"   {signal.symbol} {signal.direction} @ ${signal.entry_price}")
        logger.info(f"   SL: ${signal.stop_loss} | TP: ${signal.take_profit}")
        
        return trade
    
    async def update_prices(self, prices: Dict[str, float]):
        """Обновить цены и проверить SL/TP"""
        
        trades_to_close = []
        
        for trade_id, trade in self.active_trades.items():
            if trade.symbol in prices:
                trade.update_price(prices[trade.symbol])
                
                close_reason = trade.should_close()
                if close_reason:
                    trades_to_close.append((trade_id, close_reason))
        
        # Закрываем сработавшие
        for trade_id, reason in trades_to_close:
            await self.close_trade(trade_id, reason)
    
    async def close_trade(self, trade_id: str, reason: CloseReason) -> Optional[Trade]:
        """Закрыть сделку"""
        
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades.pop(trade_id)
        trade.status = TradeStatus.CLOSED
        trade.close_reason = reason
        trade.closed_at = datetime.utcnow()
        
        self.trade_history.append(trade)
        
        emoji = "✅" if trade.unrealized_pnl >= 0 else "❌"
        logger.info(f"{emoji} Trade closed: {trade_id}")
        logger.info(f"   Reason: {reason.value}")
        logger.info(f"   P&L: {trade.unrealized_pnl_percent:+.2f}% (${trade.unrealized_pnl:+.2f})")
        
        # Отправляем уведомление в Telegram
        await telegram_bot.notify_trade_closed(trade)
        
        return trade
    
    def get_active_trades(self) -> List[Trade]:
        """Получить активные сделки"""
        return list(self.active_trades.values())
    
    def get_statistics(self) -> dict:
        """Статистика торговли"""
        
        if not self.trade_history:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'active_trades': len(self.active_trades),
            }
        
        wins = [t for t in self.trade_history if t.unrealized_pnl > 0]
        total_pnl = sum(t.unrealized_pnl for t in self.trade_history)
        
        return {
            'total_trades': len(self.trade_history),
            'wins': len(wins),
            'losses': len(self.trade_history) - len(wins),
            'win_rate': len(wins) / len(self.trade_history) * 100,
            'total_pnl': round(total_pnl, 2),
            'active_trades': len(self.active_trades),
        }


# Глобальный экземпляр
trade_manager = TradeManager()
