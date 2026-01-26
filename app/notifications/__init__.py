"""
Notifications Module — Telegram уведомления
"""

from app.notifications.telegram_bot import TelegramBot, telegram_bot

# Alias for backwards compatibility
TelegramNotifier = TelegramBot

__all__ = ['TelegramBot', 'TelegramNotifier', 'telegram_bot']
