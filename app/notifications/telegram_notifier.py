"""
Telegram Notifier - Уведомления в Telegram
==========================================

Отправка уведомлений о сигналах и сделках.
"""

from typing import Optional, List
from aiogram import Bot
from aiogram.enums import ParseMode

from app.core.config import settings
from app.core.logger import logger
from app.strategies.signals import TradeSignal
from app.trading.trade_manager import Trade
from app.notifications.formatters import format_signal, format_trade_opened, format_trade_closed


class TelegramNotifier:
    """Отправщик Telegram уведомлений"""
    
    def __init__(self):
        self._bot: Optional[Bot] = None
        self._subscribers: List[int] = []
    
    def set_bot(self, bot: Bot):
        """Установить бота"""
        self._bot = bot
    
    def add_subscriber(self, chat_id: int):
        """Добавить подписчика"""
        if chat_id not in self._subscribers:
            self._subscribers.append(chat_id)
    
    def remove_subscriber(self, chat_id: int):
        """Удалить подписчика"""
        if chat_id in self._subscribers:
            self._subscribers.remove(chat_id)
    
    async def notify_signal(self, signal: TradeSignal):
        """Уведомить о сигнале"""
        if not self._bot:
            return
        
        message = format_signal(signal)
        await self._broadcast(message)
    
    async def notify_trade_opened(self, trade: Trade):
        """Уведомить об открытии сделки"""
        if not self._bot:
            return
        
        message = format_trade_opened(trade)
        await self._broadcast(message)
    
    async def notify_trade_closed(self, trade: Trade):
        """Уведомить о закрытии сделки"""
        if not self._bot:
            return
        
        message = format_trade_closed(trade)
        await self._broadcast(message)
    
    async def send_message(self, chat_id: int, text: str):
        """Отправить сообщение конкретному пользователю"""
        if not self._bot:
            return
        
        try:
            await self._bot.send_message(
                chat_id,
                text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
    
    async def _broadcast(self, message: str):
        """Разослать сообщение всем подписчикам"""
        if not self._bot:
            return
        
        # Добавляем админа если не в списке
        admin_id = settings.admin_chat_id
        if admin_id and admin_id not in self._subscribers:
            self._subscribers.append(admin_id)
        
        for chat_id in self._subscribers:
            try:
                await self._bot.send_message(
                    chat_id,
                    message,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.warning(f"Failed to send to {chat_id}: {e}")


# Глобальный экземпляр
notifier = TelegramNotifier()
