"""
Decision Engine - Движок принятия решений
=========================================

Объединяет стратегии, новости и AI для финального решения.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from app.core.logger import logger
from app.core.constants import COINS
from app.strategies.signals import TradeSignal, signal_generator
from app.intelligence.market_state import market_state
from app.trading.bybit.client import bybit_client


class DecisionAction(Enum):
    TRADE = "trade"
    SKIP = "skip"
    WAIT = "wait"


@dataclass
class Decision:
    """Решение системы"""
    symbol: str
    action: DecisionAction
    signal: Optional[TradeSignal] = None
    reason: str = ""
    confidence: float = 0.0
    news_impact: str = "neutral"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "signal": self.signal.to_dict() if self.signal else None,
            "reason": self.reason,
            "confidence": self.confidence,
            "news_impact": self.news_impact,
            "timestamp": self.timestamp.isoformat()
        }


class DecisionEngine:
    """Движок принятия решений"""
    
    def __init__(self):
        self._last_decisions: Dict[str, Decision] = {}
    
    async def analyze(self, symbol: str) -> Decision:
        """
        Анализировать монету и принять решение
        
        Args:
            symbol: Торговая пара
        
        Returns:
            Decision
        """
        logger.info(f"🧠 Analyzing {symbol}...")
        
        # 1. Проверяем состояние рынка (новости)
        state = market_state.get_state()
        can_trade, block_reason = state.can_trade()
        
        if not can_trade:
            return Decision(
                symbol=symbol,
                action=DecisionAction.SKIP,
                reason=f"Market blocked: {block_reason}",
                news_impact="negative"
            )
        
        # 2. Получаем данные
        candles = await bybit_client.get_klines(symbol, "5", 100)
        if not candles or len(candles) < 50:
            return Decision(
                symbol=symbol,
                action=DecisionAction.WAIT,
                reason="Insufficient data"
            )
        
        # 3. Проверяем сигнал стратегии
        signal = signal_generator.check_signal(symbol, candles)
        
        if not signal:
            return Decision(
                symbol=symbol,
                action=DecisionAction.SKIP,
                reason="No signal from strategy"
            )
        
        # 4. Проверяем направление с новостями
        can_direction, dir_reason = state.can_trade(signal.direction)
        if not can_direction:
            return Decision(
                symbol=symbol,
                action=DecisionAction.SKIP,
                signal=signal,
                reason=f"Direction blocked: {dir_reason}",
                news_impact="negative"
            )
        
        # 5. Применяем буст если есть
        boost = state.get_boost(signal.direction)
        final_confidence = signal.confidence
        
        if boost > 0:
            final_confidence = min(1.0, signal.confidence * (1 + boost / 100))
            logger.info(f"📈 Confidence boosted +{boost}%: {signal.confidence:.2f} → {final_confidence:.2f}")
        
        # 6. Финальное решение
        decision = Decision(
            symbol=symbol,
            action=DecisionAction.TRADE,
            signal=signal,
            reason=signal.reason,
            confidence=final_confidence,
            news_impact="positive" if boost > 0 else "neutral"
        )
        
        self._last_decisions[symbol] = decision
        
        logger.info(f"✅ Decision: {symbol} {signal.direction} | Confidence: {final_confidence:.2f}")
        
        return decision
    
    async def analyze_all(self) -> List[Decision]:
        """Анализировать все монеты"""
        decisions = []
        
        for symbol in COINS:
            decision = await self.analyze(symbol)
            decisions.append(decision)
        
        return decisions
    
    def get_last_decision(self, symbol: str) -> Optional[Decision]:
        """Получить последнее решение"""
        return self._last_decisions.get(symbol)
    
    def get_tradeable_decisions(self) -> List[Decision]:
        """Получить решения для торговли"""
        return [
            d for d in self._last_decisions.values()
            if d.action == DecisionAction.TRADE
        ]


# Глобальный экземпляр
decision_engine = DecisionEngine()
