"""
🧠 AI Module — Иерархия AI для торгового бота

Архитектура:
- 👷 Tech AI (Работник) — выполняет стратегии
- 🎩 Director AI (Директор) — принимает решения
- 🐋 Whale AI (Друг) — разведка рынка, метрики китов
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
]
