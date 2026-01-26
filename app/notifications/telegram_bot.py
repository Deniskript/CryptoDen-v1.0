"""
Telegram Bot — Reply Keyboard интерфейс

Правила:
- Reply Keyboard ВНИЗУ экрана (постоянная)
- Только message handlers (на текст кнопок)
- Никаких inline кнопок
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.core.config import settings
from app.core.logger import logger
from app.bot.keyboards import (
    get_main_keyboard,
    get_coins_keyboard,
    get_settings_keyboard,
    get_confirm_keyboard,
    get_back_keyboard
)


class TelegramBot:
    """Telegram бот с Reply Keyboard"""
    
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.admin_id: int = settings.admin_chat_id
        self.enabled: bool = False
        
        # Состояние пользователя
        self.pending_action: Optional[str] = None
        self.current_menu: str = "main"  # main, coins, settings
        
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
    
    async def _set_commands(self):
        """Установить команды в Menu"""
        
        commands = [
            BotCommand(command="start", description="🔄 Перезапустить бота"),
            BotCommand(command="help", description="❓ Помощь"),
            BotCommand(command="restart", description="🔁 Полный рестарт")
        ]
        
        await self.bot.set_my_commands(commands)
    
    def _get_status_text(self) -> str:
        """Текст статуса"""
        
        running = self.monitor.running
        ai_enabled = self.monitor.ai_enabled
        paper = self.monitor.paper_trading
        
        # Статус бота
        if running:
            status = "🟢 БОТ РАБОТАЕТ"
        else:
            status = "🔴 БОТ ОСТАНОВЛЕН"
        
        # AI статус
        ai = "✅" if ai_enabled else "❌"
        
        # Режим
        mode = "📝 Paper" if paper else "💰 LIVE"
        
        # Баланс
        balance = self.monitor.current_balance
        trade_size = balance * 0.15
        
        # Статистика
        stats = self.trade_manager.get_statistics()
        active = len(self.trade_manager.get_active_trades())
        max_trades = self.monitor.max_open_trades
        
        today_pnl = stats.get('today_pnl', 0)
        pnl_emoji = "📈" if today_pnl >= 0 else "📉"
        
        total_pnl = stats.get('total_pnl', 0)
        win_rate = stats.get('win_rate', 0)
        total_trades = stats.get('total_trades', 0)
        
        # Рыночный режим
        market_mode = self.monitor.market_context.get('market_mode', 'NORMAL')
        market_emoji = {"NORMAL": "🟢", "NEWS_ALERT": "🟡", "WAIT_EVENT": "🔴"}.get(market_mode, "⚪")
        
        text = f"""
╔══════════════════════════════════════╗
       🤖 CryptoDen Trading Bot       
╠══════════════════════════════════════╣

  {status}

  🧠 AI: {ai}  │  {mode}
  {market_emoji} Рынок: {market_mode}

╠══════════════════════════════════════╣
  💰 Баланс: ${balance:,.2f}
  💵 Сделка: ${trade_size:,.2f} (15%)
  📊 Позиции: {active}/{max_trades}
╠══════════════════════════════════════╣
  {pnl_emoji} Сегодня: ${today_pnl:+,.2f}
  💎 Всего: ${total_pnl:+,.2f}
  🎯 Win Rate: {win_rate:.1f}%
  📈 Сделок: {total_trades}
╚══════════════════════════════════════╝
"""
        return text.strip()
    
    def _register_handlers(self):
        """Регистрация обработчиков"""
        
        # ==================== КОМАНДЫ ====================
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            await self._set_commands()
            self.current_menu = "main"
            self.pending_action = None
            
            text = self._get_status_text()
            await message.answer(
                text,
                reply_markup=get_main_keyboard()
            )
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            text = """
❓ Помощь CryptoDen Bot

📱 Кнопки управления:
🚀 Запустить — Старт торговли
🛑 Остановить — Стоп торговли
📊 Статус — Текущее состояние
📈 Сделки — Открытые позиции
📰 Новости — Рыночный контекст
🪙 Монеты — Вкл/выкл монеты
⚙️ Настройки — Параметры бота
📋 История — Закрытые сделки

📋 Правила торговли:
• Размер сделки: 15% от баланса
• Макс. сделок: 6 одновременно
• Стратегии: зафиксированы из бэктеста

📝 Команды меню:
/start — Перезапустить
/help — Эта помощь
/restart — Полный рестарт
"""
            await message.answer(text, reply_markup=get_main_keyboard())
        
        @self.dp.message(Command("restart"))
        async def cmd_restart(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            if self.monitor.running:
                await self.monitor.stop()
            
            self.current_menu = "main"
            self.pending_action = None
            
            await message.answer(
                "🔄 Бот перезапущен",
                reply_markup=get_main_keyboard()
            )
        
        # ==================== ГЛАВНЫЕ КНОПКИ ====================
        
        @self.dp.message(F.text == "🚀 Запустить")
        async def btn_start(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            if self.monitor.running:
                await message.answer("⚠️ Бот уже запущен!")
                return
            
            await message.answer(
                "🚀 Запускаю бота...\n\n"
                "• AI анализ включён\n"
                "• Поиск сигналов начат\n"
                "• Мониторинг 24/7"
            )
            
            # Обновляем список активных монет
            self.monitor.symbols = [
                coin for coin, enabled in self.enabled_coins.items() 
                if enabled
            ]
            
            # Запускаем в фоне
            asyncio.create_task(self.monitor.start())
            
            await asyncio.sleep(2)
            
            text = self._get_status_text()
            await message.answer(text, reply_markup=get_main_keyboard())
        
        @self.dp.message(F.text == "🛑 Остановить")
        async def btn_stop(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            if not self.monitor.running:
                await message.answer("⚠️ Бот не запущен!")
                return
            
            self.pending_action = "stop_bot"
            active = len(self.trade_manager.get_active_trades())
            
            await message.answer(
                f"🛑 Остановить бота?\n\n"
                f"⚠️ Активных сделок: {active}\n"
                f"Они останутся открытыми!",
                reply_markup=get_confirm_keyboard()
            )
        
        @self.dp.message(F.text == "✅ Да, подтверждаю")
        async def btn_confirm(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            if self.pending_action == "stop_bot":
                await self.monitor.stop()
                await message.answer(
                    "🛑 Бот остановлен",
                    reply_markup=get_main_keyboard()
                )
            
            elif self.pending_action == "switch_live":
                self.monitor.paper_trading = False
                await message.answer(
                    "🔴 LIVE TRADING ВКЛЮЧЁН!\n\n"
                    "⚠️ Бот торгует реальными деньгами!",
                    reply_markup=get_main_keyboard()
                )
            
            self.pending_action = None
            self.current_menu = "main"
        
        @self.dp.message(F.text == "❌ Отмена")
        async def btn_cancel(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            self.pending_action = None
            
            if self.current_menu == "settings":
                await message.answer("↩️ Отменено", reply_markup=get_settings_keyboard())
            elif self.current_menu == "coins":
                await message.answer("↩️ Отменено", reply_markup=get_coins_keyboard(self.enabled_coins))
            else:
                self.current_menu = "main"
                await message.answer("↩️ Отменено", reply_markup=get_main_keyboard())
        
        @self.dp.message(F.text == "📊 Статус")
        async def btn_status(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            text = self._get_status_text()
            await message.answer(text, reply_markup=get_main_keyboard())
        
        @self.dp.message(F.text == "📈 Сделки")
        async def btn_trades(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            trades = self.trade_manager.get_active_trades()
            
            if not trades:
                await message.answer(
                    "📭 Нет активных сделок\n\n"
                    "Бот ищет сигналы...",
                    reply_markup=get_main_keyboard()
                )
                return
            
            text = f"📈 Активные сделки ({len(trades)}):\n\n"
            
            total_pnl = 0
            for t in trades:
                pnl_emoji = "🟢" if t.unrealized_pnl >= 0 else "🔴"
                dir_emoji = "📈" if t.direction == "LONG" else "📉"
                total_pnl += t.unrealized_pnl
                
                text += f"""
{dir_emoji} {t.symbol} {t.direction}
┣ Вход: ${t.entry_price:,.4f}
┣ Сейчас: ${t.current_price:,.4f}
┣ {pnl_emoji} P&L: {t.unrealized_pnl_percent:+.2f}%
┣ SL: ${t.stop_loss:,.4f}
┗ TP: ${t.take_profit:,.4f}

"""
            
            text += f"💰 Общий P&L: ${total_pnl:+.2f}"
            
            await message.answer(text.strip(), reply_markup=get_main_keyboard())
        
        @self.dp.message(F.text == "📰 Новости")
        async def btn_news(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            context = self.monitor.market_context
            
            if not context:
                await message.answer(
                    "📰 Новости не загружены\n\n"
                    "Запустите бота для получения данных.",
                    reply_markup=get_main_keyboard()
                )
                return
            
            mode = context.get('market_mode', 'UNKNOWN')
            mode_emoji = {"NORMAL": "🟢", "NEWS_ALERT": "🟡", "WAIT_EVENT": "🔴"}.get(mode, "⚪")
            
            text = f"""
📰 Рыночный контекст

{mode_emoji} Режим: {mode}

"""
            
            # Новости
            news = context.get('news', [])[:5]
            if news:
                text += "📋 Последние новости:\n"
                for n in news:
                    s = n.get('sentiment', 0)
                    emoji = "🟢" if s > 0 else "🔴" if s < 0 else "⚪"
                    title = n.get('title', '')[:40]
                    imp = n.get('importance', 'LOW')
                    text += f"{emoji} {title}... ({imp})\n"
            
            # События
            events = context.get('calendar', [])
            if events:
                text += "\n📅 Ближайшие события:\n"
                for e in events[:3]:
                    text += f"⏰ {e.get('event', '')}\n"
                    text += f"   {e.get('importance', '')} | {e.get('expected_impact', '')}\n"
            
            await message.answer(text.strip(), reply_markup=get_main_keyboard())
        
        @self.dp.message(F.text == "🪙 Монеты")
        async def btn_coins(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            self.current_menu = "coins"
            
            text = """
🪙 Управление монетами

Нажмите на монету чтобы вкл/выкл
Стратегии зафиксированы из бэктеста
"""
            
            await message.answer(
                text,
                reply_markup=get_coins_keyboard(self.enabled_coins)
            )
        
        # Обработка нажатия на монету
        @self.dp.message(F.text.regexp(r'^[✅❌] [A-Z]+$'))
        async def btn_toggle_coin(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            # Парсим монету из текста кнопки
            parts = message.text.split()
            if len(parts) == 2:
                coin = parts[1]
                
                if coin in self.enabled_coins:
                    self.enabled_coins[coin] = not self.enabled_coins[coin]
                    status_text = "✅ включена" if self.enabled_coins[coin] else "❌ выключена"
                    
                    await message.answer(
                        f"🪙 {coin} {status_text}",
                        reply_markup=get_coins_keyboard(self.enabled_coins)
                    )
        
        @self.dp.message(F.text == "⚙️ Настройки")
        async def btn_settings(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            self.current_menu = "settings"
            
            paper = self.monitor.paper_trading
            mode = "📝 Paper Trading" if paper else "💰 LIVE Trading"
            ai = "✅ Включён" if self.monitor.ai_enabled else "❌ Выключён"
            conf = self.monitor.min_confidence
            
            text = f"""
⚙️ Настройки

Текущие параметры:
• Режим: {mode}
• AI: {ai}
• Min Confidence: {conf}%
• Размер сделки: 15% от баланса
• Макс. сделок: 6

Выберите раздел:
"""
            
            await message.answer(
                text,
                reply_markup=get_settings_keyboard()
            )
        
        @self.dp.message(F.text == "🔑 API Ключи")
        async def btn_api_keys(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            has_keys = bool(settings.bybit_api_key and settings.bybit_api_secret)
            testnet = settings.bybit_testnet
            
            key_status = "✅ Настроены" if has_keys else "❌ Не настроены"
            net_status = "🧪 Testnet" if testnet else "💰 Mainnet"
            
            text = f"""
🔑 API Ключи Bybit

Статус: {key_status}
Сеть: {net_status}

⚠️ Для изменения API ключей
отредактируйте файл .env на сервере:

BYBIT_API_KEY=ваш_ключ
BYBIT_API_SECRET=ваш_секрет
BYBIT_TESTNET=true/false

После изменения перезапустите бота.
"""
            
            await message.answer(text, reply_markup=get_back_keyboard())
        
        @self.dp.message(F.text == "💰 Риски")
        async def btn_risks(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            text = f"""
💰 Управление рисками

Текущие настройки:
• Размер сделки: 15% от баланса
• Макс. сделок: 6 одновременно
• Min Confidence AI: {self.monitor.min_confidence}%

⚠️ Эти параметры оптимизированы
на основе бэктеста 2022-2025.

Не рекомендуется менять без
понимания последствий.
"""
            
            await message.answer(text, reply_markup=get_back_keyboard())
        
        @self.dp.message(F.text == "🧠 AI Настройки")
        async def btn_ai_settings(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            ai_enabled = self.monitor.ai_enabled
            ai_status = "✅ Включён" if ai_enabled else "❌ Выключён"
            
            text = f"""
🧠 AI Настройки

Статус: {ai_status}
Модель: Claude Sonnet 4.5
Min Confidence: {self.monitor.min_confidence}%

Что делает AI:
• Анализирует новости
• Подтверждает сигналы
• Двигает SL/TP
• Определяет размер (0.5x-1.5x)

Команды:
Отправьте "ai on" или "ai off"
для включения/выключения AI
"""
            
            await message.answer(text, reply_markup=get_back_keyboard())
        
        @self.dp.message(F.text.lower() == "ai on")
        async def btn_ai_on(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            self.monitor.ai_enabled = True
            await message.answer("🧠 AI ВКЛЮЧЁН", reply_markup=get_main_keyboard())
            self.current_menu = "main"
        
        @self.dp.message(F.text.lower() == "ai off")
        async def btn_ai_off(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            self.monitor.ai_enabled = False
            await message.answer(
                "❌ AI ВЫКЛЮЧЕН\n\n"
                "Торговля только по стратегиям.",
                reply_markup=get_main_keyboard()
            )
            self.current_menu = "main"
        
        @self.dp.message(F.text == "📝 Paper/Live")
        async def btn_paper_live(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            paper = self.monitor.paper_trading
            
            if paper:
                # Переход на LIVE
                self.pending_action = "switch_live"
                
                await message.answer(
                    "⚠️ ВНИМАНИЕ!\n\n"
                    "Вы собираетесь включить LIVE TRADING!\n\n"
                    "• Бот будет торговать РЕАЛЬНЫМИ деньгами\n"
                    "• Убытки будут РЕАЛЬНЫМИ\n"
                    "• Убедитесь что API ключи настроены\n\n"
                    "Вы уверены?",
                    reply_markup=get_confirm_keyboard()
                )
            else:
                # Переход на Paper
                self.monitor.paper_trading = True
                await message.answer(
                    "📝 Paper Trading включён\n\n"
                    "Торговля виртуальными деньгами.",
                    reply_markup=get_settings_keyboard()
                )
        
        @self.dp.message(F.text == "📋 История")
        async def btn_history(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            history = self.trade_manager.trade_history[-10:]
            
            if not history:
                await message.answer(
                    "📋 История пуста\n\n"
                    "Закрытых сделок пока нет.",
                    reply_markup=get_main_keyboard()
                )
                return
            
            text = f"📋 Последние сделки ({len(history)}):\n\n"
            
            for t in reversed(history):
                emoji = "✅" if t.unrealized_pnl >= 0 else "❌"
                text += f"{emoji} {t.symbol} {t.direction}\n"
                text += f"   P&L: {t.unrealized_pnl_percent:+.2f}% (${t.unrealized_pnl:+.2f})\n"
                if t.close_reason:
                    text += f"   Причина: {t.close_reason.value}\n"
                text += "\n"
            
            stats = self.trade_manager.get_statistics()
            text += f"Итого: ${stats.get('total_pnl', 0):+.2f}"
            
            await message.answer(text.strip(), reply_markup=get_main_keyboard())
        
        @self.dp.message(F.text == "◀️ Назад")
        async def btn_back(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            self.current_menu = "main"
            self.pending_action = None
            
            text = self._get_status_text()
            await message.answer(text, reply_markup=get_main_keyboard())
    
    # ==================== УВЕДОМЛЕНИЯ ====================
    
    async def send_message(self, text: str, keyboard=None):
        """Отправить сообщение админу"""
        if not self.enabled:
            return
        
        try:
            await self.bot.send_message(
                self.admin_id,
                text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Telegram error: {e}")
    
    async def notify_signal(self, signal):
        """Уведомление о сигнале"""
        emoji = "📈" if signal.direction == "LONG" else "📉"
        
        text = f"""
{emoji} СИГНАЛ: {signal.symbol}

Направление: {signal.direction}
Стратегия: {signal.strategy_name}
Win Rate: {signal.win_rate:.1f}%

💰 Entry: ${signal.entry_price:,.4f}
🛑 SL: ${signal.stop_loss:,.4f}
🎯 TP: ${signal.take_profit:,.4f}
"""
        await self.send_message(text.strip())
    
    async def notify_trade_opened(self, trade):
        """Уведомление об открытии"""
        emoji = "📈" if trade.direction == "LONG" else "📉"
        
        text = f"""
✅ СДЕЛКА ОТКРЫТА

{emoji} {trade.symbol} {trade.direction}

💰 Вход: ${trade.entry_price:,.4f}
📦 Размер: ${trade.value_usdt:,.2f}
🛑 SL: ${trade.stop_loss:,.4f}
🎯 TP: ${trade.take_profit:,.4f}
"""
        await self.send_message(text.strip())
    
    async def notify_trade_closed(self, trade):
        """Уведомление о закрытии"""
        emoji = "✅" if trade.unrealized_pnl >= 0 else "❌"
        
        reason = trade.close_reason.value if trade.close_reason else "unknown"
        reason_emoji = {
            "take_profit": "🎯",
            "stop_loss": "🛑",
            "trailing_stop": "📈",
            "manual": "👤",
        }.get(reason, "❓")
        
        text = f"""
{emoji} СДЕЛКА ЗАКРЫТА

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
        
        if decision.action.value in ["open_long", "open_short"]:
            emoji = "🟢"
            action = "ОТКРЫТЬ"
        elif decision.action.value == "wait":
            emoji = "🟡"
            action = "ЖДАТЬ"
        else:
            emoji = "⚪"
            action = decision.action.value.upper()
        
        text = f"""
🧠 AI РЕШЕНИЕ

{emoji} Действие: {action}
📊 Уверенность: {decision.confidence}%
💡 Причина: {decision.reason}
"""
        
        if decision.news_influence:
            text += f"📰 Новость: {decision.news_influence}"
        
        await self.send_message(text.strip())
    
    async def notify_error(self, error: str):
        """Уведомление об ошибке"""
        await self.send_message(f"⚠️ Ошибка: {error}")
    
    async def notify_startup(self):
        """Уведомление о готовности"""
        from app.strategies import get_enabled_strategies
        
        strategies = len(get_enabled_strategies())
        enabled_coins = sum(1 for v in self.enabled_coins.values() if v)
        
        text = f"""
🤖 CryptoDen Bot Ready!

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
        
        await self._set_commands()
        logger.info("📱 Telegram bot polling started")
        await self.dp.start_polling(self.bot)
    
    async def stop(self):
        """Остановить"""
        if self.bot:
            await self.bot.session.close()
            logger.info("📱 Telegram bot stopped")


# Глобальный экземпляр
telegram_bot = TelegramBot()
