"""
🧠 AI Module — Иерархия AI для торгового бота

Архитектура:
  👑 Master Strategist — главный стратег (управляет модулями)
  🎯 Trading Coordinator — связывает всех
  🎩 Director AI (Директор) — принимает решения (независимый)
  🐋 Whale AI (Друг) — разведка рынка
  👷 Tech AI (Работник) — выполняет стратегии
"""

from app.ai.whale_ai import WhaleAI, whale_ai, WhaleAlert, MarketMetrics, AlertLevel
from app.ai.director_ai import (
    DirectorAI, 
    director_ai, 
    DirectorCommand, 
    DirectorDecision,
    TradingMode,
    MarketSituation,
    get_director_decision,
    DirectorTrader,
    DirectorTrade,
    director_trader,
)
from app.ai.trading_coordinator import (
    TradingCoordinator,
    trading_coordinator,
    TradingAction,
    get_director_guidance,
    filter_signal_through_director,
    process_signal_with_coordinator,
)
from app.ai.master_strategist import (
    MasterStrategist,
    master_strategist,
    MasterStrategy,
    ModuleStrategy,
    MarketCondition,
    GridMode,
)

__all__ = [
    # Master Strategist
    'MasterStrategist',
    'master_strategist',
    'MasterStrategy',
    'ModuleStrategy',
    'MarketCondition',
    'GridMode',
    # Whale AI
    'WhaleAI',
    'whale_ai',
    'WhaleAlert',
    'MarketMetrics',
    'AlertLevel',
    # Director AI
    'DirectorAI',
    'director_ai',
    'DirectorCommand',
    'DirectorDecision',
    'TradingMode',
    'MarketSituation',
    'get_director_decision',
    # Director Trader (TAKE_CONTROL)
    'DirectorTrader',
    'DirectorTrade',
    'director_trader',
    # Trading Coordinator
    'TradingCoordinator',
    'trading_coordinator',
    'TradingAction',
    'get_director_guidance',
    'filter_signal_through_director',
    'process_signal_with_coordinator',
]
