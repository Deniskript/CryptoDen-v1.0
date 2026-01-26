"""
Telegram Bot — Уведомления и управление

Команды управления:
- /run — запустить бота
- /stop — остановить бота  
- /pause — вкл/выкл AI
- /live — переключить Paper/Live режим
- /status — статус
- /trades — активные сделки
- /stats — статистика
- /set_size — размер сделки
- /set_confidence — мин. confidence AI
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
    - Управления ботом через команды
    - Уведомлений о сигналах
    - Уведомлений об открытии/закрытии сделок
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
    
    def _is_admin(self, user_id: int) -> bool:
        """Проверка что это админ"""
        return user_id == self.chat_id
    
    def _register_handlers(self):
        """Регистрация обработчиков команд"""
        
        # ============ КОМАНДЫ УПРАВЛЕНИЯ ============
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            """Главное меню"""
            await message.answer(
                "🤖 *CryptoDen Trading Bot*\n\n"
                "📍 *Управление:*\n"
                "/run — 🚀 Запустить бота\n"
                "/stop — 🛑 Остановить бота\n"
                "/pause — ⏸️ Вкл/выкл AI\n"
                "/live — 💰 Paper/Live режим\n\n"
                "📊 *Информация:*\n"
                "/status — Статус бота\n"
                "/trades — Активные сделки\n"
                "/stats — Статистика\n"
                "/prices — Текущие цены\n"
                "/strategies — Стратегии\n\n"
                "⚙️ *Настройки:*\n"
                "/set\\_size 100 — Размер сделки\n"
                "/set\\_confidence 70 — Мин. confidence AI\n\n"
                "📱 Отправь /run чтобы начать!",
                parse_mode=ParseMode.MARKDOWN
            )
        
        @self.dp.message(Command("run"))
        async def cmd_run(message: types.Message):
            """🚀 Запустить бота"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            # Импортируем здесь чтобы избежать circular import
            from app.core.monitor import market_monitor
            
            if market_monitor.running:
                await message.answer("⚠️ Бот уже запущен!\n\nИспользуй /stop для остановки")
                return
            
            await message.answer(
                "🚀 *Запускаю бота...*\n\n"
                f"• 🧠 AI: {'Включён' if market_monitor.ai_enabled else 'Выключен'}\n"
                f"• 📝 Режим: {'Paper' if market_monitor.paper_trading else 'LIVE!'}\n"
                f"• 💰 Размер: ${market_monitor.trade_value_usdt}\n"
                f"• ⏱️ Интервал: {market_monitor.check_interval} сек\n\n"
                "📊 Мониторинг начат!",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Запускаем в фоне
            asyncio.create_task(market_monitor.start())
        
        @self.dp.message(Command("stop"))
        async def cmd_stop(message: types.Message):
            """🛑 Остановить бота"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            from app.core.monitor import market_monitor
            
            if not market_monitor.running:
                await message.answer("⚠️ Бот не запущен!\n\nИспользуй /run для запуска")
                return
            
            await market_monitor.stop()
            
            stats = trade_manager.get_statistics()
            
            await message.answer(
                "🛑 *Бот остановлен*\n\n"
                f"📊 Циклов выполнено: {market_monitor.check_count}\n"
                f"💰 P&L за сессию: ${stats.get('total_pnl', 0):.2f}\n\n"
                "Отправь /run чтобы запустить снова",
                parse_mode=ParseMode.MARKDOWN
            )
        
        @self.dp.message(Command("pause"))
        async def cmd_pause(message: types.Message):
            """⏸️ Пауза AI (стратегии работают, AI нет)"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            from app.core.monitor import market_monitor
            
            market_monitor.ai_enabled = not market_monitor.ai_enabled
            
            if market_monitor.ai_enabled:
                await message.answer(
                    "🧠 *AI ВКЛЮЧЁН*\n\n"
                    "• AI анализирует каждый сигнал\n"
                    "• AI управляет SL/TP\n"
                    "• Расходуются токены OpenRouter",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message.answer(
                    "❌ *AI ВЫКЛЮЧЕН*\n\n"
                    "• Торговля только по стратегиям\n"
                    "• Фиксированные SL/TP\n"
                    "• Токены НЕ расходуются",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        @self.dp.message(Command("live"))
        async def cmd_live(message: types.Message):
            """💰 Переключить Paper/Live режим"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            from app.core.monitor import market_monitor
            
            if market_monitor.paper_trading:
                # Требуем подтверждение для Live
                await message.answer(
                    "⚠️ *ВНИМАНИЕ!*\n\n"
                    "Переключение на *LIVE торговлю*!\n"
                    "Будут использоваться *РЕАЛЬНЫЕ деньги*!\n\n"
                    "🔴 Убедись что:\n"
                    "• API ключи настроены правильно\n"
                    "• На балансе есть USDT\n"
                    "• Ты понимаешь риски\n\n"
                    "Отправь /live\\_confirm для подтверждения",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                market_monitor.paper_trading = True
                await message.answer(
                    "📝 *Режим: Paper Trading*\n\n"
                    "Торговля без реальных денег.\n"
                    "Сделки симулируются.",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        @self.dp.message(Command("live_confirm"))
        async def cmd_live_confirm(message: types.Message):
            """Подтверждение Live режима"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            from app.core.monitor import market_monitor
            
            market_monitor.paper_trading = False
            await message.answer(
                "🔴 *LIVE TRADING ВКЛЮЧЁН!*\n\n"
                "⚠️ Бот торгует *РЕАЛЬНЫМИ* деньгами!\n\n"
                f"💰 Размер сделки: ${market_monitor.trade_value_usdt}\n"
                f"🎯 Min confidence: {market_monitor.min_confidence}%\n\n"
                "Отправь /live чтобы вернуться в Paper режим",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # ============ КОМАНДЫ ИНФОРМАЦИИ ============
        
        @self.dp.message(Command("status"))
        async def cmd_status(message: types.Message):
            """Статус бота"""
            from app.core.monitor import market_monitor
            
            stats = trade_manager.get_statistics()
            checker_status = strategy_checker.get_status()
            
            running_emoji = "🟢" if market_monitor.running else "🔴"
            ai_emoji = "🧠" if market_monitor.ai_enabled else "❌"
            mode_emoji = "📝" if market_monitor.paper_trading else "🔴"
            mode_text = "Paper" if market_monitor.paper_trading else "LIVE!"
            
            text = (
                f"📊 *Статус CryptoDen*\n\n"
                f"{running_emoji} Бот: {'Работает' if market_monitor.running else 'Остановлен'}\n"
                f"{ai_emoji} AI: {'Включён' if market_monitor.ai_enabled else 'Выключен'}\n"
                f"{mode_emoji} Режим: {mode_text}\n\n"
                f"📈 Активных сделок: {len(trade_manager.get_active_trades())}\n"
                f"💰 Размер сделки: ${market_monitor.trade_value_usdt}\n"
                f"🎯 Min confidence: {market_monitor.min_confidence}%\n"
                f"📅 Сигналов сегодня: {checker_status.get('total_today', 0)}\n\n"
                f"📊 *Статистика:*\n"
                f"Всего сделок: {stats.get('total_trades', 0)}\n"
                f"✅ Wins: {stats.get('wins', 0)} | ❌ Losses: {stats.get('losses', 0)}\n"
                f"Win Rate: {stats.get('win_rate', 0):.1f}%\n"
                f"💰 P&L: ${stats.get('total_pnl', 0):.2f}\n\n"
                f"⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
            )
            
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("trades"))
        async def cmd_trades(message: types.Message):
            """Активные сделки"""
            trades = trade_manager.get_active_trades()
            
            if not trades:
                await message.answer("📭 Нет активных сделок")
                return
            
            text = "📊 *Активные сделки:*\n\n"
            
            total_pnl = 0
            for t in trades:
                emoji = "🟢" if t.unrealized_pnl >= 0 else "🔴"
                total_pnl += t.unrealized_pnl
                text += (
                    f"{emoji} *{t.symbol}* {t.direction}\n"
                    f"   💰 Entry: ${t.entry_price:,.4f}\n"
                    f"   📍 Current: ${t.current_price:,.4f}\n"
                    f"   📊 P&L: {t.unrealized_pnl_percent:+.2f}% (${t.unrealized_pnl:+.2f})\n"
                    f"   🛑 SL: ${t.stop_loss:,.4f} | 🎯 TP: ${t.take_profit:,.4f}\n\n"
                )
            
            text += f"📊 *Общий P&L: ${total_pnl:+.2f}*"
            
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("stats"))
        async def cmd_stats(message: types.Message):
            """Статистика"""
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
            """Стратегии"""
            strategies = get_enabled_strategies()
            
            text = "🎯 *Активные стратегии:*\n\n"
            
            for symbol, s in strategies.items():
                text += f"• *{symbol}*: {s.name}\n  WR: {s.avg_win_rate:.1f}%\n\n"
            
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("prices"))
        async def cmd_prices(message: types.Message):
            """Текущие цены"""
            from app.trading.bybit.client import BybitClient
            
            await message.answer("⏳ Загружаю цены...")
            
            client = BybitClient(testnet=False)
            symbols = list(get_enabled_strategies().keys())
            
            try:
                async with client:
                    prices = await client.get_prices(symbols)
                
                if not prices:
                    await message.answer("❌ Не удалось получить цены")
                    return
                
                text = "💹 *Текущие цены:*\n\n"
                for sym, price in sorted(prices.items(), key=lambda x: -x[1]):
                    text += f"• *{sym}*: ${price:,.4f}\n"
                
                text += f"\n⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
                
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.answer(f"❌ Ошибка: {e}")
        
        # ============ КОМАНДЫ НАСТРОЕК ============
        
        @self.dp.message(Command("set_size"))
        async def cmd_set_size(message: types.Message):
            """Установить размер сделки"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            from app.core.monitor import market_monitor
            
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    await message.answer(
                        "Использование: /set\\_size 100\n\n"
                        f"Текущий размер: ${market_monitor.trade_value_usdt}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                size = float(parts[1])
                if 10 <= size <= 1000:
                    market_monitor.trade_value_usdt = size
                    await message.answer(
                        f"✅ Размер сделки: *${size}*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await message.answer("⚠️ Размер от $10 до $1000")
            except ValueError:
                await message.answer("⚠️ Введи число, например: /set\\_size 100", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("set_confidence"))
        async def cmd_set_confidence(message: types.Message):
            """Установить минимальный confidence"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            from app.core.monitor import market_monitor
            
            try:
                parts = message.text.split()
                if len(parts) < 2:
                    await message.answer(
                        "Использование: /set\\_confidence 70\n\n"
                        f"Текущий: {market_monitor.min_confidence}%",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                conf = int(parts[1])
                if 30 <= conf <= 95:
                    market_monitor.min_confidence = conf
                    await message.answer(
                        f"✅ Min confidence: *{conf}%*\n\n"
                        "AI будет открывать сделки только при уверенности выше этого порога.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await message.answer("⚠️ Confidence от 30% до 95%")
            except ValueError:
                await message.answer("⚠️ Введи число, например: /set\\_confidence 70", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            """Помощь"""
            await cmd_start(message)
    
    # ============ МЕТОДЫ УВЕДОМЛЕНИЙ ============
    
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
            f"💰 Entry: ${signal.entry_price:,.4f}\n"
            f"🛑 Stop Loss: ${signal.stop_loss:,.4f}\n"
            f"🎯 Take Profit: ${signal.take_profit:,.4f}\n\n"
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
            f"💰 Entry: ${trade.entry_price:,.4f}\n"
            f"📦 Size: ${trade.value_usdt:.2f}\n"
            f"🛑 SL: ${trade.stop_loss:,.4f}\n"
            f"🎯 TP: ${trade.take_profit:,.4f}"
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
            f"💰 Entry: ${trade.entry_price:,.4f}\n"
            f"💰 Exit: ${trade.current_price:,.4f}\n"
            f"📊 P&L: {trade.unrealized_pnl_percent:+.2f}% (${trade.unrealized_pnl:+.2f})\n"
            f"{reason_emoji} Причина: {reason_text}"
        )
        
        await self.send_message(text)
    
    async def notify_error(self, error: str):
        """Уведомление об ошибке"""
        
        text = f"⚠️ *ОШИБКА*\n\n`{error}`"
        await self.send_message(text)
    
    async def notify_startup(self):
        """Уведомление о запуске"""
        
        strategies = len(get_enabled_strategies())
        
        text = (
            "🚀 *CryptoDen Bot запущен!*\n\n"
            f"📊 Стратегий: {strategies}\n"
            f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            "Отправь /run для запуска торговли"
        )
        
        await self.send_message(text)
    
    async def start_polling(self):
        """Запустить прослушивание команд"""
        
        if not self.enabled:
            logger.warning("Telegram polling skipped (not configured)")
            # Если телеграм не настроен, просто ждём
            while True:
                await asyncio.sleep(60)
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
