"""
🧠 AI Module — Иерархия AI для торгового бота

Архитектура:
- 👷 Tech AI (Работник) — выполняет стратегии
- 🎩 News AI (Директор) — принимает решения на основе новостей
- 🐋 Whale AI (Друг) — разведка рынка, метрики китов
"""

from app.ai.whale_ai import WhaleAI, whale_ai, WhaleAlert, MarketMetrics, AlertLevel

__all__ = [
    'WhaleAI',
    'whale_ai',
    'WhaleAlert',
    'MarketMetrics',
    'AlertLevel',
]
