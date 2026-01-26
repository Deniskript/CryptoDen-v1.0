"""
Signals - Генерация торговых сигналов
=====================================

Объединяет все компоненты для генерации сигналов.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from app.core.logger import logger
from app.core.constants import COINS
from app.strategies.config import strategy_config
from app.strategies.indicators import calc_all_indicators
from app.strategies.checker import strategy_checker, Direction, CheckResult


@dataclass
class TradeSignal:
    """Торговый сигнал"""
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    strategy_name: str
    confidence: float
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def risk_reward(self) -> float:
        """Risk/Reward ratio"""
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk if risk > 0 else 0
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "strategy": self.strategy_name,
            "confidence": self.confidence,
            "reason": self.reason,
            "risk_reward": self.risk_reward,
            "timestamp": self.timestamp.isoformat()
        }


class SignalGenerator:
    """Генератор торговых сигналов"""
    
    def __init__(self):
        self._last_signals: Dict[str, TradeSignal] = {}
    
    def check_signal(
        self,
        symbol: str,
        candles: List[Dict]
    ) -> Optional[TradeSignal]:
        """
        Проверить сигнал для монеты
        
        Args:
            symbol: Торговая пара (BTC, ETH, etc)
            candles: Список свечей (минимум 50)
        
        Returns:
            TradeSignal если есть сигнал, иначе None
        """
        # Получаем стратегию для монеты
        strategy = strategy_config.get(symbol)
        if not strategy:
            logger.debug(f"No strategy configured for {symbol}")
            return None
        
        # Рассчитываем индикаторы
        indicators = calc_all_indicators(candles)
        if not indicators:
            logger.warning(f"Not enough data for {symbol}")
            return None
        
        # Проверяем условия стратегии
        strategy_name = strategy.get("strategy", "RSI_OVERSOLD")
        params = strategy.get("params", strategy)  # params может быть внутри или на уровне стратегии
        
        result = strategy_checker.check(strategy_name, params, indicators)
        
        if result.triggered:
            signal = TradeSignal(
                symbol=symbol,
                direction=result.direction.value,
                entry_price=result.entry_price,
                stop_loss=result.stop_loss,
                take_profit=result.take_profit,
                strategy_name=strategy_name,
                confidence=result.confidence,
                reason=result.reason
            )
            
            self._last_signals[symbol] = signal
            logger.info(f"🎯 Signal: {symbol} {signal.direction} | {signal.reason}")
            
            return signal
        
        return None
    
    def check_all(self, candles_map: Dict[str, List[Dict]]) -> List[TradeSignal]:
        """
        Проверить сигналы для всех монет
        
        Args:
            candles_map: {symbol: [candles]}
        
        Returns:
            Список сигналов
        """
        signals = []
        
        for symbol in COINS:
            candles = candles_map.get(symbol)
            if candles:
                signal = self.check_signal(symbol, candles)
                if signal:
                    signals.append(signal)
        
        return signals
    
    def get_last_signal(self, symbol: str) -> Optional[TradeSignal]:
        """Получить последний сигнал для монеты"""
        return self._last_signals.get(symbol)
    
    def get_all_last_signals(self) -> Dict[str, TradeSignal]:
        """Получить все последние сигналы"""
        return self._last_signals.copy()


# Глобальный экземпляр
signal_generator = SignalGenerator()
