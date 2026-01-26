"""
Handlers - Обработчики команд
=============================

Все handlers для Telegram бота.
"""

from app.bot.handlers.start import router as start_router
from app.bot.handlers.status import router as status_router
from app.bot.handlers.signals import router as signals_router
from app.bot.handlers.trades import router as trades_router
from app.bot.handlers.news import router as news_router
from app.bot.handlers.settings import router as settings_router

all_routers = [
    start_router,
    status_router,
    signals_router,
    trades_router,
    news_router,
    settings_router,
]

__all__ = ["all_routers"]
