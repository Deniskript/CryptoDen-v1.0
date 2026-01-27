"""
🧠 AI Module — Иерархия AI для торгового бота

Архитектура:
  🎯 Trading Coordinator — связывает всех
  🎩 Director AI (Директор) — принимает решения
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
)
from app.ai.trading_coordinator import (
    TradingCoordinator,
    trading_coordinator,
    TradingAction,
    get_director_guidance,
    filter_signal_through_director,
    process_signal_with_coordinator,
)

__all__ = [
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
    # Trading Coordinator
    'TradingCoordinator',
    'trading_coordinator',
    'TradingAction',
    'get_director_guidance',
    'filter_signal_through_director',
    'process_signal_with_coordinator',
]
