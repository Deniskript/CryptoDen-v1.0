"""
Telegram Bot — Чистый интерфейс с WebApp
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, CallbackQuery

from app.core.config import settings
from app.core.logger import logger
from app.bot.keyboards import (
    get_main_keyboard,
    get_start_button,
    get_stop_button,
    get_confirm_stop
)

# Файлы данных
SETTINGS_FILE = "/root/crypto-bot/data/webapp_settings.json"
START_REQUESTED_FILE = "/root/crypto-bot/data/start_requested.json"


class TelegramBot:
    """Telegram бот с WebApp настройками"""
    
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.admin_id: int = settings.admin_chat_id
        self.enabled: bool = False
        
        self._monitor = None
        self._trade_manager = None
        
        # Монеты (для запуска без WebApp)
        self.enabled_coins: Dict[str, bool] = {
            'BTC': True, 'ETH': True, 'BNB': True,
            'SOL': True, 'XRP': True, 'ADA': True,
            'DOGE': True, 'LINK': False, 'AVAX': False
        }
        
        self._setup()
    
    def _setup(self):
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
        if self._monitor is None:
            from app.core.monitor import market_monitor
            self._monitor = market_monitor
        return self._monitor
    
    @property
    def trade_manager(self):
        if self._trade_manager is None:
            from app.trading import trade_manager
            self._trade_manager = trade_manager
        return self._trade_manager
    
    def _is_admin(self, user_id: int) -> bool:
        return user_id == self.admin_id
    
    async def _set_commands(self):
        commands = [
            BotCommand(command="start", description="🔄 Главное меню"),
            BotCommand(command="help", description="❓ Помощь")
        ]
        await self.bot.set_my_commands(commands)
    
    def _get_status_message(self) -> str:
        """Формирует сообщение статуса"""
        
        running = self.monitor.running
        
        if running:
            status = "🟢 БОТ РАБОТАЕТ"
        else:
            status = "🔴 БОТ ОСТАНОВЛЕН"
        
        # Данные
        balance = self.monitor.current_balance
        trade_size = balance * self.monitor.balance_percent_per_trade
        active = len(self.trade_manager.get_active_trades())
        max_trades = self.monitor.max_open_trades
        
        stats = self.trade_manager.get_statistics()
        today_pnl = stats.get('today_pnl', 0)
        total_pnl = stats.get('total_pnl', 0)
        win_rate = stats.get('win_rate', 0)
        
        pnl_emoji = "📈" if today_pnl >= 0 else "📉"
        
        # AI и режим
        ai = "✅" if self.monitor.ai_enabled else "❌"
        mode = "📝 Paper" if self.monitor.paper_trading else "💰 LIVE"
        
        # Рынок
        market_mode = self.monitor.market_context.get('market_mode', 'NORMAL')
        market_emoji = {"NORMAL": "🟢", "NEWS_ALERT": "🟡", "WAIT_EVENT": "🔴"}.get(market_mode, "⚪")
        
        text = f"""
{status}

🧠 AI: {ai}  •  {mode}
{market_emoji} Рынок: {market_mode}

━━━━━━━━━━━━━━━━━━━━━━
💰 Баланс: ${balance:,.2f}
💵 Сделка: ${trade_size:,.2f} ({int(self.monitor.balance_percent_per_trade*100)}%)
📊 Позиции: {active}/{max_trades}
━━━━━━━━━━━━━━━━━━━━━━
{pnl_emoji} Сегодня: ${today_pnl:+,.2f}
💎 Всего: ${total_pnl:+,.2f}
🎯 Win Rate: {win_rate:.1f}%
"""
        return text.strip()
    
    def _register_handlers(self):
        """Регистрация обработчиков"""
        
        # === КОМАНДЫ ===
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            await self._set_commands()
            await self._send_main_screen(message)
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            text = """
❓ Помощь CryptoDen Bot

Управление:
🚀 Запустить — открывает настройки
🛑 Остановить — останавливает торговлю

Информация:
📊 Статус — текущее состояние
📈 Сделки — открытые позиции
📰 Новости — рыночный контекст
📋 История — закрытые сделки

Правила:
• Сделка = 15% от баланса
• Макс 6 сделок одновременно
• Стратегии из бэктеста
"""
            await message.answer(text, reply_markup=get_main_keyboard())
        
        # === WEBAPP DATA ===
        
        @self.dp.message(F.web_app_data)
        async def handle_webapp_data(message: types.Message):
            """Получение данных из WebApp"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                data = json.loads(message.web_app_data.data)
                
                if data.get('action') == 'start_bot':
                    settings_data = data.get('settings', {})
                    
                    # Применяем настройки
                    self.monitor.ai_enabled = settings_data.get('ai_enabled', True)
                    self.monitor.paper_trading = settings_data.get('paper_trading', True)
                    self.monitor.balance_percent_per_trade = settings_data.get('risk_percent', 15) / 100
                    self.monitor.max_open_trades = settings_data.get('max_trades', 6)
                    self.monitor.min_confidence = settings_data.get('ai_confidence', 60)
                    
                    # Монеты
                    coins = settings_data.get('coins', {})
                    self.monitor.symbols = [c for c, enabled in coins.items() if enabled]
                    self.enabled_coins = coins
                    
                    # Запускаем
                    await message.answer(
                        "🚀 Запускаю бота...",
                        reply_markup=get_main_keyboard()
                    )
                    
                    asyncio.create_task(self.monitor.start())
                    
                    await asyncio.sleep(2)
                    await self._send_main_screen(message)
                    
            except Exception as e:
                logger.error(f"WebApp data error: {e}")
                await message.answer(f"❌ Ошибка: {e}")
        
        # === CALLBACK (start/stop) ===
        
        @self.dp.callback_query(F.data == "start_bot")
        async def cb_start(callback: CallbackQuery):
            """Запуск без WebApp"""
            if not self._is_admin(callback.from_user.id):
                return
            
            if self.monitor.running:
                await callback.answer("⚠️ Бот уже запущен!")
                return
            
            # Запускаем с текущими настройками
            self.monitor.symbols = [c for c, enabled in self.enabled_coins.items() if enabled]
            
            await callback.message.edit_text("🚀 Запускаю бота...")
            await callback.answer()
            
            asyncio.create_task(self.monitor.start())
            
            await asyncio.sleep(2)
            await self._send_main_screen(callback.message, edit=True)
        
        @self.dp.callback_query(F.data == "stop_bot")
        async def cb_stop(callback: CallbackQuery):
            if not self._is_admin(callback.from_user.id):
                return
            
            if not self.monitor.running:
                await callback.answer("⚠️ Бот не запущен!")
                return
            
            active = len(self.trade_manager.get_active_trades())
            
            await callback.message.edit_text(
                f"🛑 Остановить бота?\n\n"
                f"⚠️ Активных сделок: {active}\n"
                f"Они останутся открытыми!",
                reply_markup=get_confirm_stop()
            )
        
        @self.dp.callback_query(F.data == "confirm_stop")
        async def cb_confirm_stop(callback: CallbackQuery):
            if not self._is_admin(callback.from_user.id):
                return
            
            await self.monitor.stop()
            await callback.answer("🛑 Бот остановлен")
            await self._send_main_screen(callback.message, edit=True)
        
        @self.dp.callback_query(F.data == "cancel_stop")
        async def cb_cancel_stop(callback: CallbackQuery):
            if not self._is_admin(callback.from_user.id):
                return
            
            await callback.answer("Отменено")
            await self._send_main_screen(callback.message, edit=True)
        
        # === REPLY KEYBOARD ===
        
        @self.dp.message(F.text == "📊 Статус")
        async def btn_status(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            await self._send_main_screen(message)
        
        @self.dp.message(F.text == "📈 Сделки")
        async def btn_trades(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            trades = self.trade_manager.get_active_trades()
            
            if not trades:
                text = "📭 Нет активных сделок"
            else:
                text = f"📈 Активные сделки ({len(trades)}):\n"
                
                total_pnl = 0
                for t in trades:
                    emoji = "🟢" if t.unrealized_pnl >= 0 else "🔴"
                    dir_emoji = "📈" if t.direction == "LONG" else "📉"
                    total_pnl += t.unrealized_pnl
                    
                    text += f"""
{dir_emoji} {t.symbol} {t.direction}
┣ Вход: ${t.entry_price:,.4f}
┣ Сейчас: ${t.current_price:,.4f}
┣ {emoji} P&L: {t.unrealized_pnl_percent:+.2f}%
┗ SL: ${t.stop_loss:,.2f} | TP: ${t.take_profit:,.2f}
"""
                text += f"\n💰 Общий P&L: ${total_pnl:+.2f}"
            
            await message.answer(text.strip(), reply_markup=get_main_keyboard())
        
        @self.dp.message(F.text == "📰 Новости")
        async def btn_news(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            context = self.monitor.market_context
            
            if not context:
                await message.answer(
                    "📰 Новости не загружены\n\nЗапустите бота.",
                    reply_markup=get_main_keyboard()
                )
                return
            
            mode = context.get('market_mode', 'UNKNOWN')
            mode_emoji = {"NORMAL": "🟢", "NEWS_ALERT": "🟡", "WAIT_EVENT": "🔴"}.get(mode, "⚪")
            
            text = f"📰 Рынок: {mode} {mode_emoji}\n\n"
            
            news = context.get('news', [])[:5]
            if news:
                for n in news:
                    s = n.get('sentiment', 0)
                    emoji = "🟢" if s > 0 else "🔴" if s < 0 else "⚪"
                    title = n.get('title', '')[:45]
                    text += f"{emoji} {title}...\n"
            
            events = context.get('calendar', [])
            if events:
                text += "\n📅 События:\n"
                for e in events[:3]:
                    text += f"⏰ {e.get('event', '')}\n"
            
            await message.answer(text.strip(), reply_markup=get_main_keyboard())
        
        @self.dp.message(F.text == "📋 История")
        async def btn_history(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            history = self.trade_manager.trade_history[-10:]
            
            if not history:
                await message.answer("📋 История пуста", reply_markup=get_main_keyboard())
                return
            
            text = f"📋 Последние сделки:\n\n"
            
            for t in reversed(history):
                emoji = "✅" if t.unrealized_pnl >= 0 else "❌"
                text += f"{emoji} {t.symbol} {t.direction}: {t.unrealized_pnl_percent:+.2f}%\n"
            
            stats = self.trade_manager.get_statistics()
            text += f"\nИтого: ${stats.get('total_pnl', 0):+.2f}"
            
            await message.answer(text, reply_markup=get_main_keyboard())
    
    async def _send_main_screen(self, message: types.Message, edit: bool = False):
        """Отправить главный экран"""
        
        text = self._get_status_message()
        
        if self.monitor.running:
            inline_kb = get_stop_button()
        else:
            inline_kb = get_start_button()
        
        if edit:
            try:
                await message.edit_text(text, reply_markup=inline_kb)
            except:
                await message.answer(text, reply_markup=inline_kb)
        else:
            # Отправляем статус с inline кнопкой
            await message.answer(text, reply_markup=inline_kb)
            # Reply keyboard устанавливается автоматически
    
    # === УВЕДОМЛЕНИЯ ===
    
    async def send_message(self, text: str):
        if not self.enabled:
            return
        try:
            await self.bot.send_message(self.admin_id, text)
        except Exception as e:
            logger.error(f"Telegram error: {e}")
    
    async def notify_signal(self, signal):
        emoji = "📈" if signal.direction == "LONG" else "📉"
        text = f"""
{emoji} СИГНАЛ: {signal.symbol}

{signal.direction} • {signal.strategy_name}
WR: {signal.win_rate:.1f}%

Entry: ${signal.entry_price:,.4f}
SL: ${signal.stop_loss:,.4f} | TP: ${signal.take_profit:,.4f}
"""
        await self.send_message(text.strip())
    
    async def notify_trade_opened(self, trade):
        emoji = "📈" if trade.direction == "LONG" else "📉"
        text = f"""
✅ ОТКРЫТА: {trade.symbol}

{emoji} {trade.direction} • ${trade.value_usdt:,.2f}
Entry: ${trade.entry_price:,.4f}
SL: ${trade.stop_loss:,.4f} | TP: ${trade.take_profit:,.4f}
"""
        await self.send_message(text.strip())
    
    async def notify_trade_closed(self, trade):
        emoji = "✅" if trade.unrealized_pnl >= 0 else "❌"
        reason = trade.close_reason.value if trade.close_reason else "unknown"
        text = f"""
{emoji} ЗАКРЫТА: {trade.symbol}

P&L: {trade.unrealized_pnl_percent:+.2f}% (${trade.unrealized_pnl:+.2f})
Причина: {reason}
"""
        await self.send_message(text.strip())
    
    async def notify_ai_decision(self, decision):
        text = f"""
🧠 AI: {decision.action.value.upper()}

Confidence: {decision.confidence}%
{decision.reason}
"""
        await self.send_message(text.strip())
    
    async def notify_error(self, error: str):
        await self.send_message(f"⚠️ Ошибка: {error}")
    
    async def notify_startup(self):
        """Уведомление о готовности"""
        enabled_count = sum(1 for v in self.enabled_coins.values() if v)
        
        text = f"""
🤖 CryptoDen Bot Ready!

📊 Монет: {enabled_count}
📱 Отправь /start для управления
"""
        await self.send_message(text.strip())
    
    async def start_polling(self):
        if not self.enabled:
            logger.warning("Telegram not configured")
            return
        await self._set_commands()
        logger.info("📱 Telegram bot polling started")
        
        # Запускаем фоновую проверку запроса запуска из WebApp
        asyncio.create_task(self._check_start_request())
        
        await self.dp.start_polling(self.bot)
    
    async def _check_start_request(self):
        """Проверяет запрос на запуск из WebApp каждые 2 секунды"""
        while True:
            try:
                if os.path.exists(START_REQUESTED_FILE):
                    with open(START_REQUESTED_FILE, 'r') as f:
                        data = json.load(f)
                    
                    if data.get('requested') and not self.monitor.running:
                        # Удаляем файл сразу
                        os.remove(START_REQUESTED_FILE)
                        
                        # Применяем настройки
                        settings_data = data.get('settings', {})
                        await self._apply_settings_and_start(settings_data)
                        
            except Exception as e:
                logger.error(f"Check start request error: {e}")
            
            await asyncio.sleep(2)
    
    async def _apply_settings_and_start(self, settings_data: dict):
        """Применить настройки из WebApp и запустить бота"""
        try:
            # Применяем настройки
            self.monitor.ai_enabled = settings_data.get('ai_enabled', True)
            self.monitor.paper_trading = settings_data.get('paper_trading', True)
            self.monitor.balance_percent_per_trade = settings_data.get('risk_percent', 15) / 100
            self.monitor.max_open_trades = settings_data.get('max_trades', 6)
            self.monitor.min_confidence = settings_data.get('ai_confidence', 60)
            
            # Монеты
            coins = settings_data.get('coins', {})
            self.monitor.symbols = [c for c, enabled in coins.items() if enabled]
            self.enabled_coins = coins
            
            logger.info(f"📱 WebApp settings applied: {len(self.monitor.symbols)} coins")
            
            # Уведомляем
            await self.send_message("🚀 Запускаю бота из WebApp...")
            
            # Запускаем
            asyncio.create_task(self.monitor.start())
            
            await asyncio.sleep(3)
            
            # Отправляем статус
            text = self._get_status_message()
            await self.bot.send_message(
                self.admin_id, 
                text, 
                reply_markup=get_stop_button()
            )
            
        except Exception as e:
            logger.error(f"Apply settings error: {e}")
            await self.send_message(f"❌ Ошибка: {e}")
    
    async def stop(self):
        if self.bot:
            await self.bot.session.close()


telegram_bot = TelegramBot()
