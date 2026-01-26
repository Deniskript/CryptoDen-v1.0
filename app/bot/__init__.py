"""
Bot Module - Telegram Bot
=========================

Telegram бот для взаимодействия с системой.

Компоненты:
- handlers/: Обработчики команд
- keyboards: Клавиатуры
- middlewares: Middleware
"""

from app.bot.keyboards import get_main_keyboard

__all__ = ["get_main_keyboard"]
