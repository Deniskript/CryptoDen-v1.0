"""
🔌 Базовый класс для всех торговых модулей
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ModuleSignal:
    """Сигнал от модуля"""
    module_name: str
    symbol: str
    direction: str  # "LONG" | "SHORT" | "BUY" | "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str
    confidence: float = 0.7
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class BaseModule(ABC):
    """Базовый класс для всех торговых модулей"""
    
    name: str = "base"
    enabled: bool = True
    
    @abstractmethod
    async def get_signals(self, market_data: Dict) -> List[ModuleSignal]:
        """Получить сигналы от модуля"""
        pass
    
    @abstractmethod
    async def get_status(self) -> Dict:
        """Статус модуля"""
        pass
    
    def enable(self):
        self.enabled = True
    
    def disable(self):
        self.enabled = False
