"""
🎯 Trading Coordinator — Координатор торговли
Связывает всех AI агентов в единую систему

Иерархия:
  🎩 Director AI — принимает решения
  🐋 Whale AI — разведка рынка
  👷 Tech AI — выполняет стратегии
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from app.core.logger import logger
from app.core.config import settings


@dataclass
class TradingAction:
    """Действие для выполнения"""
    action_type: str  # "open", "close", "modify", "none"
    symbol: str = ""
    direction: str = ""  # "LONG", "SHORT"
    reason: str = ""
    source: str = ""  # "tech_ai", "director_ai"
    size_multiplier: float = 1.0
    stop_loss: float = 0
    take_profit: float = 0
    entry_price: float = 0
    confidence: int = 50
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "action": self.action_type,
            "symbol": self.symbol,
            "direction": self.direction,
            "source": self.source,
            "reason": self.reason[:100],
            "confidence": self.confidence,
        }


class TradingCoordinator:
    """
    🎯 Главный координатор
    
    Управляет взаимодействием между:
    - Director AI (решения)
    - Whale AI (разведка)
    - Tech AI (стратегии через StrategyChecker)
    """
    
    def __init__(self):
        self.is_running = False
        self.last_check = None
        self.actions_executed = 0
        self.director_interventions = 0
        self.signals_generated = 0
        
        # Cooldown между проверками Director
        self.director_check_interval = timedelta(minutes=5)
        self.last_director_check = None
        
        # История действий
        self.action_history: List[TradingAction] = []
        
        logger.info("🎯 Trading Coordinator инициализирован")
    
    async def should_check_director(self) -> bool:
        """Нужно ли проверять Директора?"""
        if self.last_director_check is None:
            return True
        
        return datetime.now() - self.last_director_check >= self.director_check_interval
    
    async def get_director_guidance(self) -> dict:
        """
        Получить руководство от Директора
        Возвращает dict с разрешениями и модификаторами
        """
        
        try:
            from app.ai.director_ai import director_ai, DirectorDecision, TradingMode
            
            # Проверяем нужно ли обновлять
            if not await self.should_check_director():
                # Возвращаем последнее решение
                if director_ai.last_command:
                    return {
                        "decision": director_ai.last_command.decision.value,
                        "mode": director_ai.last_command.mode.value,
                        "allow_longs": director_ai.allow_new_longs,
                        "allow_shorts": director_ai.allow_new_shorts,
                        "size_multiplier": director_ai.size_multiplier,
                        "risk_level": director_ai.situation.risk_level if director_ai.situation else "normal",
                        "cached": True,
                    }
            
            # Получаем новое решение
            command = await director_ai.make_decision()
            self.last_director_check = datetime.now()
            
            return {
                "decision": command.decision.value,
                "mode": command.mode.value,
                "reason": command.reason,
                "allow_longs": director_ai.allow_new_longs,
                "allow_shorts": director_ai.allow_new_shorts,
                "size_multiplier": director_ai.size_multiplier,
                "risk_level": director_ai.situation.risk_level if director_ai.situation else "normal",
                "details": command.details,
                "cached": False,
            }
            
        except Exception as e:
            logger.error(f"Director guidance error: {e}")
            return {
                "decision": "continue",
                "mode": "auto",
                "allow_longs": True,
                "allow_shorts": True,
                "size_multiplier": 1.0,
                "risk_level": "unknown",
                "error": str(e),
            }
    
    async def filter_signal(self, signal, guidance: dict) -> Tuple[bool, str]:
        """
        Фильтрация сигнала через Директора
        
        Returns:
            (allowed, reason)
        """
        
        decision = guidance.get("decision", "continue")
        
        # КРИТИЧЕСКОЕ — всё запрещено
        if decision in ["close_all", "take_control"]:
            return False, "🎩 Директор запретил новые сделки"
        
        # Пауза новых сделок
        if decision == "pause_new":
            return False, "⏸️ Пауза новых сделок"
        
        # Проверка по направлению
        if signal.direction == "LONG" and not guidance.get("allow_longs", True):
            return False, "🚫 LONG заблокирован Директором"
        
        if signal.direction == "SHORT" and not guidance.get("allow_shorts", True):
            return False, "🚫 SHORT заблокирован Директором"
        
        # Проверка риска
        risk = guidance.get("risk_level", "normal")
        if risk == "extreme":
            return False, "🔴 Экстремальный риск — торговля запрещена"
        
        return True, "OK"
    
    async def process_signal(self, signal, guidance: dict) -> Optional[TradingAction]:
        """
        Обработать сигнал с учётом Директора
        """
        
        # Фильтруем через Директора
        allowed, reason = await self.filter_signal(signal, guidance)
        
        if not allowed:
            logger.info(f"⛔ Signal {signal.symbol} {signal.direction} blocked: {reason}")
            return None
        
        # Применяем модификатор размера
        size_mult = guidance.get("size_multiplier", 1.0)
        
        # Создаём действие
        action = TradingAction(
            action_type="open",
            symbol=signal.symbol,
            direction=signal.direction,
            reason=f"{signal.strategy_name} | {reason}",
            source="tech_ai",
            size_multiplier=size_mult,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_price=signal.entry_price,
            confidence=int(signal.confidence * 100) if signal.confidence <= 1 else int(signal.confidence),
        )
        
        self.signals_generated += 1
        self._save_action(action)
        
        return action
    
    async def check_for_close_orders(self, guidance: dict) -> List[TradingAction]:
        """
        Проверить нужно ли закрыть позиции по команде Директора
        """
        
        actions = []
        decision = guidance.get("decision", "continue")
        
        try:
            from app.trading import trade_manager
            
            trades = trade_manager.get_active_trades()
            
            if decision == "close_all":
                # Закрыть всё
                for trade in trades:
                    action = TradingAction(
                        action_type="close",
                        symbol=trade.symbol,
                        direction=trade.direction,
                        reason=f"🎩 Director: {guidance.get('reason', 'Close all')[:50]}",
                        source="director_ai",
                    )
                    actions.append(action)
                    self.director_interventions += 1
            
            elif decision == "close_longs":
                # Закрыть только лонги
                for trade in trades:
                    if trade.direction == "LONG":
                        action = TradingAction(
                            action_type="close",
                            symbol=trade.symbol,
                            direction=trade.direction,
                            reason="🎩 Director: Close longs",
                            source="director_ai",
                        )
                        actions.append(action)
                        self.director_interventions += 1
            
            elif decision == "close_shorts":
                # Закрыть только шорты
                for trade in trades:
                    if trade.direction == "SHORT":
                        action = TradingAction(
                            action_type="close",
                            symbol=trade.symbol,
                            direction=trade.direction,
                            reason="🎩 Director: Close shorts",
                            source="director_ai",
                        )
                        actions.append(action)
                        self.director_interventions += 1
        
        except Exception as e:
            logger.error(f"Check close orders error: {e}")
        
        return actions
    
    async def execute_close_action(self, action: TradingAction) -> bool:
        """Выполнить закрытие позиции"""
        
        try:
            from app.trading import trade_manager, CloseReason
            
            # Ищем trade_id по символу
            for trade_id, trade in trade_manager.active_trades.items():
                if trade.symbol == action.symbol and trade.direction == action.direction:
                    await trade_manager.close_trade(trade_id, CloseReason.MANUAL)
                    
                    logger.warning(f"🎩 Closed {action.symbol} {action.direction}: {action.reason}")
                    self.actions_executed += 1
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Execute close error: {e}")
            return False
    
    def _save_action(self, action: TradingAction):
        """Сохранить действие в историю"""
        self.action_history.append(action)
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]
    
    def get_status(self) -> Dict:
        """Получить статус координатора"""
        
        return {
            "is_running": self.is_running,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "last_director_check": self.last_director_check.isoformat() if self.last_director_check else None,
            "actions_executed": self.actions_executed,
            "signals_generated": self.signals_generated,
            "director_interventions": self.director_interventions,
        }
    
    def get_status_text(self) -> str:
        """Статус для Telegram"""
        
        text = f"""🎯 *Trading Coordinator*

*Сигналов:* {self.signals_generated}
*Выполнено:* {self.actions_executed}
*Вмешательств Директора:* {self.director_interventions}
"""
        
        if self.last_director_check:
            time_ago = (datetime.now() - self.last_director_check).seconds // 60
            text += f"\n_Director проверен {time_ago} мин назад_"
        
        return text


# Singleton
trading_coordinator = TradingCoordinator()


async def get_director_guidance() -> dict:
    """Публичная функция для получения руководства"""
    return await trading_coordinator.get_director_guidance()


async def filter_signal_through_director(signal, guidance: dict) -> Tuple[bool, str]:
    """Фильтрация сигнала"""
    return await trading_coordinator.filter_signal(signal, guidance)


async def process_signal_with_coordinator(signal, guidance: dict) -> Optional[TradingAction]:
    """Обработать сигнал через координатор"""
    return await trading_coordinator.process_signal(signal, guidance)
