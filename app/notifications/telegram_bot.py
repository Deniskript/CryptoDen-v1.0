"""
Telegram Bot — Красивый интерфейс + управление

Правила:
- Размер сделки = 15% от баланса
- Стратегии ЗАФИКСИРОВАНЫ из бэктеста
- Максимум 6 открытых сделок
- Пользователь может только ВКЛ/ВЫКЛ монету
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery

from app.core.config import settings
from app.core.logger import logger
from app.bot.keyboards import (
    get_main_keyboard,
    get_confirm_keyboard,
    get_back_keyboard,
    get_trades_keyboard,
    get_coins_keyboard,
    get_settings_keyboard,
)


class TelegramBot:
    """Telegram бот с красивым интерфейсом"""
    
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.admin_id: int = settings.admin_chat_id
        self.enabled: bool = False
        
        # Ссылки на модули (lazy loading)
        self._monitor = None
        self._trade_manager = None
        
        # Какие монеты включены
        self.enabled_coins: Dict[str, bool] = {
            'BTC': True,
            'ETH': True,
            'BNB': True,
            'SOL': True,
            'XRP': True,
            'ADA': True,
            'DOGE': True,
            'LINK': True,
            'AVAX': True,
        }
        
        self._setup()
    
    def _setup(self):
        """Инициализация"""
        
        token = settings.telegram_bot_token
        
        if not token or not self.admin_id:
            logger.warning("Telegram not configured")
            return
        
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.enabled = True
        
        self._register_handlers()
        logger.info("✅ Telegram bot initialized")
    
    @property
    def monitor(self):
        """Lazy loading монитора"""
        if self._monitor is None:
            from app.core.monitor import market_monitor
            self._monitor = market_monitor
        return self._monitor
    
    @property
    def trade_manager(self):
        """Lazy loading trade manager"""
        if self._trade_manager is None:
            from app.trading import trade_manager
            self._trade_manager = trade_manager
        return self._trade_manager
    
    def _is_admin(self, user_id: int) -> bool:
        """Проверка админа"""
        return user_id == self.admin_id
    
    async def _get_status_text(self) -> str:
        """Сформировать текст статуса"""
        
        running = self.monitor.running
        ai_enabled = self.monitor.ai_enabled
        paper = self.monitor.paper_trading
        
        # Эмодзи статуса
        status_emoji = "🟢" if running else "🔴"
        status_text = "РАБОТАЕТ" if running else "ОСТАНОВЛЕН"
        
        ai_emoji = "🧠" if ai_enabled else "❌"
        ai_text = "Включён" if ai_enabled else "Выключен"
        
        mode_emoji = "📝" if paper else "💰"
        mode_text = "Paper Trading" if paper else "LIVE TRADING"
        
        # Баланс и статистика
        balance = self.monitor.current_balance
        stats = self.trade_manager.get_statistics()
        active_trades = len(self.trade_manager.get_active_trades())
        max_trades = self.monitor.max_open_trades
        
        # P&L
        total_pnl = stats.get('total_pnl', 0)
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        
        # Размер следующей сделки
        trade_size = self.monitor.get_trade_size()
        
        # Market mode
        market_mode = self.monitor.market_context.get('market_mode', 'UNKNOWN')
        market_emoji = {"NORMAL": "🟢", "NEWS_ALERT": "🟡", "WAIT_EVENT": "🔴"}.get(market_mode, "⚪")
        
        text = f"""
{status_emoji} *БОТ {status_text}*

{ai_emoji} AI: {ai_text}
{mode_emoji} Режим: {mode_text}
{market_emoji} Рынок: {market_mode}

💰 *Баланс:* ${balance:,.2f}
💵 *Размер сделки:* ${trade_size:,.2f} (15%)
📊 *Активных сделок:* {active_trades}/{max_trades}

{pnl_emoji} *P&L:* ${total_pnl:+,.2f}
📈 *Всего сделок:* {stats.get('total_trades', 0)}
🎯 *Win Rate:* {stats.get('win_rate', 0):.1f}%

⏰ {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC
"""
        return text.strip()
    
    def _register_handlers(self):
        """Регистрация обработчиков"""
        
        # ============ КОМАНДЫ ============
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            text = await self._get_status_text()
            keyboard = get_main_keyboard(
                self.monitor.running,
                self.monitor.ai_enabled
            )
            
            await message.answer(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            await cmd_start(message)
        
        # ============ CALLBACK: УПРАВЛЕНИЕ ============
        
        @self.dp.callback_query(F.data == "start_bot")
        async def cb_start_bot(callback: CallbackQuery):
            if not self._is_admin(callback.from_user.id):
                await callback.answer("⛔ Доступ запрещён", show_alert=True)
                return
            
            if self.monitor.running:
                await callback.answer("⚠️ Бот уже запущен!", show_alert=True)
                return
            
            await callback.answer("🚀 Запускаю...")
            
            # Обновляем список активных монет
            self.monitor.symbols = [
                coin for coin, enabled in self.enabled_coins.items() 
                if enabled
            ]
            
            # Запускаем монитор в фоне
            asyncio.create_task(self.monitor.start())
            
            # Ждём немного и обновляем сообщение
            await asyncio.sleep(2)
            
            text = await self._get_status_text()
            keyboard = get_main_keyboard(True, self.monitor.ai_enabled)
            
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        
        @self.dp.callback_query(F.data == "stop_bot")
        async def cb_stop_bot(callback: CallbackQuery):
            if not self._is_admin(callback.from_user.id):
                await callback.answer("⛔ Доступ запрещён", show_alert=True)
                return
            
            if not self.monitor.running:
                await callback.answer("⚠️ Бот не запущен!", show_alert=True)
                return
            
            active = len(self.trade_manager.get_active_trades())
            
            await callback.message.edit_text(
                f"🛑 *Остановить бота?*\n\n"
                f"⚠️ Активных сделок: {active}\n"
                f"Они останутся открытыми!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_confirm_keyboard("stop")
            )
        
        @self.dp.callback_query(F.data == "confirm_stop")
        async def cb_confirm_stop(callback: CallbackQuery):
            await self.monitor.stop()
            await callback.answer("🛑 Бот остановлен")
            
            text = await self._get_status_text()
            keyboard = get_main_keyboard(False, self.monitor.ai_enabled)
            
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        
        @self.dp.callback_query(F.data == "toggle_ai")
        async def cb_toggle_ai(callback: CallbackQuery):
            if not self._is_admin(callback.from_user.id):
                return
            
            self.monitor.ai_enabled = not self.monitor.ai_enabled
            status = "включён ✅" if self.monitor.ai_enabled else "выключен ❌"
            
            await callback.answer(f"🧠 AI {status}")
            
            text = await self._get_status_text()
            keyboard = get_main_keyboard(
                self.monitor.running,
                self.monitor.ai_enabled
            )
            
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        
        # ============ CALLBACK: ИНФОРМАЦИЯ ============
        
        @self.dp.callback_query(F.data == "status")
        async def cb_status(callback: CallbackQuery):
            text = await self._get_status_text()
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_back_keyboard()
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "trades")
        async def cb_trades(callback: CallbackQuery):
            trades = self.trade_manager.get_active_trades()
            
            if not trades:
                text = "📭 *Нет активных сделок*\n\n"
                text += f"Лимит: {self.monitor.max_open_trades} сделок\n"
                text += f"Размер: ${self.monitor.get_trade_size():,.2f} (15%)"
            else:
                text = f"📈 *Активные сделки:* ({len(trades)}/{self.monitor.max_open_trades})\n"
                
                total_pnl = 0
                for t in trades:
                    emoji = "🟢" if t.unrealized_pnl >= 0 else "🔴"
                    direction_emoji = "📈" if t.direction == "LONG" else "📉"
                    total_pnl += t.unrealized_pnl
                    
                    text += f"""
{emoji} *{t.symbol}* {direction_emoji} {t.direction}
├ Вход: ${t.entry_price:,.4f}
├ Сейчас: ${t.current_price:,.4f}
├ P&L: {t.unrealized_pnl_percent:+.2f}% (${t.unrealized_pnl:+.2f})
├ SL: ${t.stop_loss:,.4f}
└ TP: ${t.take_profit:,.4f}
"""
                text += f"\n💰 *Общий P&L:* ${total_pnl:+,.2f}"
            
            await callback.message.edit_text(
                text.strip(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_trades_keyboard(bool(trades))
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "refresh_trades")
        async def cb_refresh_trades(callback: CallbackQuery):
            await callback.answer("🔄 Обновлено")
            await cb_trades(callback)
        
        @self.dp.callback_query(F.data == "news")
        async def cb_news(callback: CallbackQuery):
            context = self.monitor.market_context
            
            mode = context.get('market_mode', 'UNKNOWN')
            mode_emoji = {"NORMAL": "🟢", "NEWS_ALERT": "🟡", "WAIT_EVENT": "🔴"}.get(mode, "⚪")
            
            text = f"📰 *Рыночный контекст*\n\n{mode_emoji} Режим: *{mode}*\n\n"
            
            # Новости
            news = context.get('news', [])[:5]
            if news:
                text += "*Последние новости:*\n"
                for n in news:
                    s = n.get('sentiment', 0)
                    emoji = "🟢" if s > 0 else "🔴" if s < 0 else "⚪"
                    title = n.get('title', '')[:60]
                    text += f"{emoji} {title}...\n\n"
            else:
                text += "_Нет свежих новостей_\n\n"
            
            # События
            events = context.get('calendar', [])
            if events:
                text += "*Ближайшие события:*\n"
                for e in events[:3]:
                    text += f"⏰ {e.get('event', '')}\n"
            
            await callback.message.edit_text(
                text.strip(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_back_keyboard()
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "strategies")
        async def cb_strategies(callback: CallbackQuery):
            from app.strategies import get_enabled_strategies
            
            strategies = get_enabled_strategies()
            
            text = "📊 *Стратегии (из бэктеста)*\n\n"
            text += "_Автоматически выбраны лучшие_\n"
            text += "_стратегии для каждой монеты_\n\n"
            
            for symbol, s in strategies.items():
                enabled = "✅" if self.enabled_coins.get(symbol, False) else "❌"
                text += f"{enabled} *{symbol}*\n"
                text += f"    {s.name}\n"
                text += f"    WR: {s.avg_win_rate:.1f}%\n\n"
            
            await callback.message.edit_text(
                text.strip(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_back_keyboard()
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "balance")
        async def cb_balance(callback: CallbackQuery):
            balance = self.monitor.current_balance
            trade_size = self.monitor.get_trade_size()
            active = len(self.trade_manager.get_active_trades())
            max_trades = self.monitor.max_open_trades
            
            stats = self.trade_manager.get_statistics()
            total_pnl = stats.get('total_pnl', 0)
            
            text = f"""
💰 *БАЛАНС*

💵 *Текущий:* ${balance:,.2f}
📊 *P&L:* ${total_pnl:+,.2f}

📦 *Размер сделки:* ${trade_size:,.2f}
_= 15% от баланса_

📈 *Активных:* {active}/{max_trades}
💵 *В сделках:* ${sum(t.value_usdt for t in self.trade_manager.get_active_trades()):,.2f}
"""
            
            await callback.message.edit_text(
                text.strip(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_back_keyboard()
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "history")
        async def cb_history(callback: CallbackQuery):
            history = self.trade_manager.trade_history[-10:]
            
            if not history:
                text = "📋 *История сделок*\n\n_Пока нет закрытых сделок_"
            else:
                text = f"📋 *Последние {len(history)} сделок:*\n\n"
                
                for t in reversed(history):
                    emoji = "✅" if t.unrealized_pnl >= 0 else "❌"
                    text += f"{emoji} *{t.symbol}* {t.direction}\n"
                    text += f"    P&L: {t.unrealized_pnl_percent:+.2f}% (${t.unrealized_pnl:+.2f})\n"
                    if t.close_reason:
                        text += f"    Причина: {t.close_reason.value}\n"
                    text += "\n"
            
            await callback.message.edit_text(
                text.strip(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_back_keyboard()
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "refresh")
        async def cb_refresh(callback: CallbackQuery):
            await callback.answer("🔄 Обновлено")
            text = await self._get_status_text()
            keyboard = get_main_keyboard(
                self.monitor.running,
                self.monitor.ai_enabled
            )
            
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        
        @self.dp.callback_query(F.data == "back")
        async def cb_back(callback: CallbackQuery):
            text = await self._get_status_text()
            keyboard = get_main_keyboard(
                self.monitor.running,
                self.monitor.ai_enabled
            )
            
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data == "cancel")
        async def cb_cancel(callback: CallbackQuery):
            await callback.answer("Отменено")
            await cb_back(callback)
        
        # ============ CALLBACK: НАСТРОЙКИ ============
        
        @self.dp.callback_query(F.data == "coins")
        async def cb_coins(callback: CallbackQuery):
            text = "🪙 *Активные монеты*\n\n"
            text += "_Нажми чтобы включить/выключить_\n"
            text += "_Стратегии зафиксированы из бэктеста_"
            
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_coins_keyboard(self.enabled_coins)
            )
            await callback.answer()
        
        @self.dp.callback_query(F.data.startswith("toggle_coin_"))
        async def cb_toggle_coin(callback: CallbackQuery):
            coin = callback.data.replace("toggle_coin_", "")
            
            if coin in self.enabled_coins:
                self.enabled_coins[coin] = not self.enabled_coins[coin]
                status = "включён ✅" if self.enabled_coins[coin] else "выключен ❌"
                await callback.answer(f"{coin} {status}")
            
            text = "🪙 *Активные монеты*\n\n"
            text += "_Нажми чтобы включить/выключить_"
            
            await callback.message.edit_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_coins_keyboard(self.enabled_coins)
            )
        
        @self.dp.callback_query(F.data == "toggle_mode")
        async def cb_toggle_mode(callback: CallbackQuery):
            if self.monitor.paper_trading:
                # Предупреждение о Live
                await callback.message.edit_text(
                    "⚠️ *ВНИМАНИЕ!*\n\n"
                    "Переключение на *LIVE* торговлю!\n"
                    "Будут использоваться *РЕАЛЬНЫЕ* деньги!\n\n"
                    "Убедись что:\n"
                    "• API ключи настроены\n"
                    "• На балансе есть USDT\n"
                    "• Ты понимаешь риски",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_confirm_keyboard("live")
                )
            else:
                self.monitor.paper_trading = True
                await callback.answer("📝 Paper Trading включён")
                
                text = await self._get_status_text()
                keyboard = get_main_keyboard(
                    self.monitor.running,
                    self.monitor.ai_enabled
                )
                
                await callback.message.edit_text(
                    text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
        
        @self.dp.callback_query(F.data == "confirm_live")
        async def cb_confirm_live(callback: CallbackQuery):
            self.monitor.paper_trading = False
            await callback.answer("🔴 LIVE Trading включён!")
            
            await callback.message.edit_text(
                "🔴 *LIVE TRADING ВКЛЮЧЁН!*\n\n"
                "⚠️ Бот торгует *РЕАЛЬНЫМИ* деньгами!\n\n"
                "Чтобы вернуться в Paper режим,\n"
                "нажми 💰 Live/Paper ещё раз.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_back_keyboard()
            )
    
    # ============ УВЕДОМЛЕНИЯ ============
    
    async def send_message(self, text: str, parse_mode: str = ParseMode.MARKDOWN):
        """Отправить сообщение админу"""
        if not self.enabled:
            logger.debug(f"Telegram disabled: {text[:50]}...")
            return
        
        try:
            await self.bot.send_message(
                self.admin_id,
                text,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"Telegram error: {e}")
    
    async def notify_signal(self, signal):
        """Уведомление о сигнале"""
        emoji = "📈" if signal.direction == "LONG" else "📉"
        
        text = f"""
{emoji} *СИГНАЛ: {signal.symbol}*

Направление: {signal.direction}
Стратегия: {signal.strategy_name}
Win Rate: {signal.win_rate:.1f}%

💰 Entry: ${signal.entry_price:,.4f}
🛑 SL: ${signal.stop_loss:,.4f}
🎯 TP: ${signal.take_profit:,.4f}
"""
        await self.send_message(text.strip())
    
    async def notify_trade_opened(self, trade):
        """Уведомление об открытии сделки"""
        emoji = "📈" if trade.direction == "LONG" else "📉"
        
        text = f"""
✅ *СДЕЛКА ОТКРЫТА*

{emoji} {trade.symbol} {trade.direction}
💰 Вход: ${trade.entry_price:,.4f}
📦 Размер: ${trade.value_usdt:,.2f} (15% баланса)
🛑 SL: ${trade.stop_loss:,.4f}
🎯 TP: ${trade.take_profit:,.4f}
"""
        await self.send_message(text.strip())
    
    async def notify_trade_closed(self, trade):
        """Уведомление о закрытии сделки"""
        emoji = "✅" if trade.unrealized_pnl >= 0 else "❌"
        
        reason = trade.close_reason.value if trade.close_reason else "unknown"
        reason_emoji = {
            "take_profit": "🎯",
            "stop_loss": "🛑",
            "trailing_stop": "📈",
            "manual": "👤",
        }.get(reason, "❓")
        
        text = f"""
{emoji} *СДЕЛКА ЗАКРЫТА*

{trade.symbol} {trade.direction}
💰 Вход: ${trade.entry_price:,.4f}
💰 Выход: ${trade.current_price:,.4f}
📊 P&L: {trade.unrealized_pnl_percent:+.2f}% (${trade.unrealized_pnl:+.2f})
{reason_emoji} Причина: {reason}

💰 Баланс: ${self.monitor.current_balance:,.2f}
"""
        await self.send_message(text.strip())
    
    async def notify_ai_decision(self, decision):
        """Уведомление о решении AI"""
        
        text = f"""
🧠 *AI РЕШЕНИЕ*

{decision.symbol}: {decision.action.value.upper()}
Уверенность: {decision.confidence}%
📝 {decision.reason}
"""
        if decision.news_influence and decision.news_influence != "none":
            text += f"📰 Новость: {decision.news_influence}"
        
        await self.send_message(text.strip())
    
    async def notify_error(self, error: str):
        """Уведомление об ошибке"""
        text = f"⚠️ *ОШИБКА*\n\n`{error}`"
        await self.send_message(text)
    
    async def notify_startup(self):
        """Уведомление о готовности"""
        from app.strategies import get_enabled_strategies
        
        strategies = len(get_enabled_strategies())
        enabled_coins = sum(1 for v in self.enabled_coins.values() if v)
        
        text = f"""
🤖 *CryptoDen Bot Ready!*

📊 Стратегий: {strategies}
🪙 Монет: {enabled_coins}

📱 Отправь /start для управления
"""
        await self.send_message(text.strip())
    
    async def start_polling(self):
        """Запустить бота"""
        if not self.enabled:
            logger.warning("Telegram not configured, waiting...")
            while True:
                await asyncio.sleep(60)
            return
        
        logger.info("📱 Telegram bot polling started")
        await self.dp.start_polling(self.bot)
    
    async def stop(self):
        """Остановить"""
        if self.bot:
            await self.bot.session.close()
            logger.info("📱 Telegram bot stopped")


# Глобальный экземпляр
telegram_bot = TelegramBot()
