"""
Telegram Bot — Уведомления и управление
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode

from app.core.config import settings
from app.core.logger import logger
from app.trading import trade_manager
from app.strategies import strategy_checker, get_enabled_strategies


class TelegramNotifier:
    """
    Telegram бот для:
    - Уведомлений о сигналах
    - Уведомлений об открытии/закрытии сделок
    - Команд управления
    """
    
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.chat_id: Optional[int] = None
        self.enabled: bool = False
        
        self._setup()
    
    def _setup(self):
        """Инициализация бота"""
        
        token = settings.telegram_bot_token
        self.chat_id = settings.admin_chat_id
        
        if not token or not self.chat_id:
            logger.warning("Telegram not configured (missing token or chat_id)")
            return
        
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.enabled = True
        
        # Регистрация команд
        self._register_handlers()
        
        logger.info("✅ Telegram bot initialized")
    
    def _register_handlers(self):
        """Регистрация обработчиков команд"""
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            await message.answer(
                "🤖 *CryptoDen Trading Bot*\n\n"
                "Команды:\n"
                "/status — Статус бота\n"
                "/trades — Активные сделки\n"
                "/stats — Статистика\n"
                "/strategies — Стратегии\n"
                "/prices — Текущие цены",
                parse_mode=ParseMode.MARKDOWN
            )
        
        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message):
            active = len(trade_manager.get_active_trades())
            strategies = len(get_enabled_strategies())
            checker_status = strategy_checker.get_status()
            
            text = (
                "📊 *Статус бота*\n\n"
                f"🟢 Работает\n"
                f"📈 Активных сделок: {active}\n"
                f"🎯 Стратегий: {strategies}\n"
                f"📅 Сигналов сегодня: {checker_status.get('total_today', 0)}\n"
                f"⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
            )
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("trades"))
        async def cmd_trades(message: types.Message):
            trades = trade_manager.get_active_trades()
            
            if not trades:
                await message.answer("📭 Нет активных сделок")
                return
            
            text = "📊 *Активные сделки:*\n\n"
            
            for t in trades:
                emoji = "🟢" if t.unrealized_pnl >= 0 else "🔴"
                text += (
                    f"{emoji} *{t.symbol}* {t.direction}\n"
                    f"   Entry: ${t.entry_price:.4f}\n"
                    f"   Current: ${t.current_price:.4f}\n"
                    f"   P&L: {t.unrealized_pnl_percent:+.2f}%\n"
                    f"   SL: ${t.stop_loss:.4f} | TP: ${t.take_profit:.4f}\n\n"
                )
            
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("stats"))
        async def cmd_stats(message: types.Message):
            stats = trade_manager.get_statistics()
            
            text = (
                "📈 *Статистика торговли*\n\n"
                f"Всего сделок: {stats.get('total_trades', 0)}\n"
                f"✅ Wins: {stats.get('wins', 0)}\n"
                f"❌ Losses: {stats.get('losses', 0)}\n"
                f"📊 Win Rate: {stats.get('win_rate', 0):.1f}%\n"
                f"💰 Total P&L: ${stats.get('total_pnl', 0):.2f}"
            )
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("strategies"))
        async def cmd_strategies(message: types.Message):
            strategies = get_enabled_strategies()
            
            text = "🎯 *Активные стратегии:*\n\n"
            
            for symbol, s in strategies.items():
                text += f"• *{symbol}*: {s.name}\n  WR: {s.avg_win_rate:.1f}%\n\n"
            
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("prices"))
        async def cmd_prices(message: types.Message):
            from app.trading.bybit.client import BybitClient
            
            client = BybitClient(testnet=False)
            symbols = list(get_enabled_strategies().keys())
            
            async with client:
                prices = await client.get_prices(symbols)
            
            if not prices:
                await message.answer("❌ Не удалось получить цены")
                return
            
            text = "💹 *Текущие цены:*\n\n"
            for sym, price in sorted(prices.items(), key=lambda x: -x[1]):
                text += f"• *{sym}*: ${price:,.4f}\n"
            
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
    
    async def send_message(self, text: str, parse_mode: str = ParseMode.MARKDOWN):
        """Отправить сообщение"""
        
        if not self.enabled or not self.bot:
            logger.debug(f"Telegram disabled, skipping: {text[:50]}...")
            return
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
    
    async def notify_signal(self, signal):
        """Уведомление о сигнале"""
        
        emoji = "🟢" if signal.direction == "LONG" else "🔴"
        
        text = (
            f"{emoji} *СИГНАЛ: {signal.symbol}*\n\n"
            f"📍 Направление: {signal.direction}\n"
            f"💰 Entry: ${signal.entry_price:.4f}\n"
            f"🛑 Stop Loss: ${signal.stop_loss:.4f}\n"
            f"🎯 Take Profit: ${signal.take_profit:.4f}\n\n"
            f"📊 Стратегия: {signal.strategy_name}\n"
            f"📈 Win Rate: {signal.win_rate:.1f}%\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
        
        await self.send_message(text)
    
    async def notify_trade_opened(self, trade):
        """Уведомление об открытии сделки"""
        
        emoji = "🟢" if trade.direction == "LONG" else "🔴"
        
        text = (
            f"✅ *СДЕЛКА ОТКРЫТА*\n\n"
            f"{emoji} {trade.symbol} {trade.direction}\n"
            f"💰 Entry: ${trade.entry_price:.4f}\n"
            f"📦 Size: ${trade.value_usdt:.2f}\n"
            f"🛑 SL: ${trade.stop_loss:.4f}\n"
            f"🎯 TP: ${trade.take_profit:.4f}"
        )
        
        await self.send_message(text)
    
    async def notify_trade_closed(self, trade):
        """Уведомление о закрытии сделки"""
        
        emoji = "✅" if trade.unrealized_pnl >= 0 else "❌"
        reason_emoji = {
            "take_profit": "🎯",
            "stop_loss": "🛑", 
            "trailing_stop": "📈",
            "manual": "👤",
        }.get(trade.close_reason.value if trade.close_reason else "unknown", "❓")
        
        reason_text = trade.close_reason.value if trade.close_reason else "unknown"
        
        text = (
            f"{emoji} *СДЕЛКА ЗАКРЫТА*\n\n"
            f"📍 {trade.symbol} {trade.direction}\n"
            f"💰 Entry: ${trade.entry_price:.4f}\n"
            f"💰 Exit: ${trade.current_price:.4f}\n"
            f"📊 P&L: {trade.unrealized_pnl_percent:+.2f}% (${trade.unrealized_pnl:+.2f})\n"
            f"{reason_emoji} Причина: {reason_text}"
        )
        
        await self.send_message(text)
    
    async def notify_error(self, error: str):
        """Уведомление об ошибке"""
        
        text = f"⚠️ *ОШИБКА*\n\n{error}"
        await self.send_message(text)
    
    async def notify_startup(self):
        """Уведомление о запуске"""
        
        strategies = len(get_enabled_strategies())
        
        text = (
            "🚀 *CryptoDen Bot запущен!*\n\n"
            f"📊 Стратегий: {strategies}\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        
        await self.send_message(text)
    
    async def start_polling(self):
        """Запустить прослушивание команд"""
        
        if not self.enabled:
            logger.warning("Telegram polling skipped (not configured)")
            return
        
        logger.info("📱 Telegram bot polling started")
        await self.dp.start_polling(self.bot)
    
    async def stop(self):
        """Остановить бота"""
        
        if self.bot:
            await self.bot.session.close()
            logger.info("📱 Telegram bot stopped")


# Глобальный экземпляр
telegram_bot = TelegramNotifier()
