"""
Brain Module - Принятие решений
===============================

Центральный модуль принятия торговых решений.

Компоненты:
- decision_engine: Главный движок решений
- signal_processor: Обработка сигналов
- ai_confirmation: AI подтверждение (опционально)
"""

from app.brain.decision_engine import decision_engine, Decision

__all__ = ["decision_engine", "Decision"]
