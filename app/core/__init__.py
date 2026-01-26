"""
Core Module - Ядро приложения
=============================

Компоненты:
- config: Настройки приложения (Pydantic Settings)
- constants: Константы (монеты, таймфреймы, лимиты)
- database: Redis и PostgreSQL клиенты
- logger: Настройка логирования (loguru)
"""

from app.core.config import settings
from app.core.constants import COINS, TIMEFRAMES
from app.core.logger import logger

__all__ = ["settings", "logger", "COINS", "TIMEFRAMES"]
