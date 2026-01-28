"""
Telegram Bot — Чистый интерфейс
Управление ТОЛЬКО через WebApp
"""
import asyncio
import json
import os
from typing import Optional, Dict

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.core.config import settings
from app.core.logger import logger
from app.bot.keyboards import get_main_keyboard
from app.core.smart_notifications import smart_notifications

# Файлы данных
SETTINGS_FILE = "/root/crypto-bot/data/webapp_settings.json"
START_REQUESTED_FILE = "/root/crypto-bot/data/start_requested.json"
STOP_REQUESTED_FILE = "/root/crypto-bot/data/stop_requested.json"
BOT_STATUS_FILE = "/root/crypto-bot/data/bot_status.json"


def update_bot_status_file(running: bool, balance: float = 1000, active_trades: int = 0, 
                           paper_trading: bool = True, ai_enabled: bool = True):
    """Обновить файл статуса для WebApp"""
    import json
    os.makedirs(os.path.dirname(BOT_STATUS_FILE), exist_ok=True)
    with open(BOT_STATUS_FILE, 'w') as f:
        json.dump({
            "running": running,
            "balance": balance,
            "active_trades": active_trades,
            "paper_trading": paper_trading,
            "ai_enabled": ai_enabled
        }, f)


class TelegramBot:
    """Telegram бот — текст + Reply Keyboard"""
    
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.admin_id: int = settings.admin_chat_id
        self.enabled: bool = False
        
        self._monitor = None
        self._trade_manager = None
        
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
            BotCommand(command="ai", description="🧠 Статус AI системы"),
            BotCommand(command="brain", description="🧠 DirectorBrain статус"),
            BotCommand(command="analyze", description="🧠 Анализ монеты (напр. /analyze BTC)"),
            BotCommand(command="director", description="🎩 Решения Директора"),
            BotCommand(command="director_trades", description="🎩 Сделки Директора"),
            BotCommand(command="whale", description="🐋 Анализ китов"),
            BotCommand(command="grid", description="📊 Grid Bot статус"),
            BotCommand(command="funding", description="💰 Funding Scalper"),
            BotCommand(command="arb", description="🔄 Arbitrage Scanner"),
            BotCommand(command="listing", description="🆕 Listing Hunter"),
            BotCommand(command="market", description="📊 Полная картина рынка"),
            BotCommand(command="debug", description="🔍 Диагностика"),
            BotCommand(command="help", description="❓ Помощь")
        ]
        await self.bot.set_my_commands(commands)
    
    def _get_status_text(self) -> str:
        """Текст статуса с режимами модулей"""
        
        running = self.monitor.running
        status = "🟢 *БОТ РАБОТАЕТ*" if running else "🔴 *БОТ ОСТАНОВЛЕН*"
        
        balance = self.monitor.current_balance
        trade_size = balance * self.monitor.balance_percent_per_trade
        percent = int(self.monitor.balance_percent_per_trade * 100)
        active = len(self.trade_manager.get_active_trades())
        max_trades = self.monitor.max_open_trades
        
        stats = self.trade_manager.get_statistics()
        today_pnl = stats.get('today_pnl', 0)
        total_pnl = stats.get('total_pnl', 0)
        win_rate = stats.get('win_rate', 0)
        
        ai = "✅" if self.monitor.ai_enabled else "❌"
        api_status = "✅ Подключён" if getattr(self.monitor, 'has_api_keys', False) else "❌ Нет"
        
        # Подсчёт режимов модулей
        module_settings = getattr(self.monitor, 'module_settings', {})
        signal_count = sum(1 for m in module_settings.values() if m.get('enabled') and m.get('mode') == 'signal')
        auto_count = sum(1 for m in module_settings.values() if m.get('enabled') and m.get('mode') == 'auto')
        
        # Формируем строку модулей
        modules_text = ""
        module_icons = {
            'director': '🎩',
            'grid': '📊',
            'funding': '💰',
            'arbitrage': '🔄',
            'listing': '🆕',
            'worker': '👷'
        }
        
        for name, config in module_settings.items():
            if config.get('enabled'):
                icon = module_icons.get(name, '📦')
                mode = "🤖" if config.get('mode') == 'auto' else "📢"
                modules_text += f"{icon}{mode} "
        
        text = f"""
{status}

🧠 AI: {ai}  •  🔐 API: {api_status}

💰 *Баланс:* ${balance:,.2f}
💵 *Сделка:* ${trade_size:,.2f} ({percent}%)
📊 *Позиции:* {active}/{max_trades}

📈 *Сегодня:* ${today_pnl:+,.2f}
💎 *Всего:* ${total_pnl:+,.2f}
🎯 *Win Rate:* {win_rate:.1f}%

*Модули:* {modules_text.strip()}

🎛 Панель управления — настройки
"""
        return text.strip()
    
    def _apply_settings(self, settings_data: dict):
        """Применить настройки из WebApp включая режимы модулей"""
        if not settings_data:
            return
        
        # Базовые настройки
        self.monitor.ai_enabled = settings_data.get('ai_enabled', True)
        self.monitor.balance_percent_per_trade = settings_data.get('risk_percent', 15) / 100
        self.monitor.max_open_trades = settings_data.get('max_trades', 6)
        self.monitor.min_confidence = settings_data.get('ai_confidence', 60)
        
        # Монеты
        coins = settings_data.get('coins', {})
        self.monitor.symbols = [c for c, enabled in coins.items() if enabled]
        
        # API ключи (проверяем наличие)
        api_key = settings_data.get('bybit_api_key', '')
        api_secret = settings_data.get('bybit_api_secret', '')
        self.monitor.has_api_keys = bool(api_key and api_secret and len(api_key) > 10 and len(api_secret) > 10)
        self.monitor.bybit_testnet = settings_data.get('bybit_testnet', True)
        
        # Режимы модулей
        modules_config = settings_data.get('modules', {})
        self.monitor.module_settings = {
            'director': modules_config.get('director', {'enabled': True, 'mode': 'signal'}),
            'grid': modules_config.get('grid', {'enabled': True, 'mode': 'signal'}),
            'funding': modules_config.get('funding', {'enabled': True, 'mode': 'signal'}),
            'arbitrage': modules_config.get('arbitrage', {'enabled': False, 'mode': 'signal'}),
            'listing': modules_config.get('listing', {'enabled': True, 'mode': 'signal'}),
            'worker': modules_config.get('worker', {'enabled': True, 'mode': 'signal'}),
        }
        
        # Если нет API ключей — все модули в режиме signal
        if not self.monitor.has_api_keys:
            for module in self.monitor.module_settings:
                self.monitor.module_settings[module]['mode'] = 'signal'
        
        logger.info(f"📱 Settings applied: {len(self.monitor.symbols)} coins, API: {self.monitor.has_api_keys}")
        logger.info(f"📱 Module modes: {self.monitor.module_settings}")
    
    def _register_handlers(self):
        """Регистрация обработчиков"""
        
        # === КОМАНДЫ ===
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            await self._set_commands()
            
            text = self._get_status_text()
            # Отправляем ТОЛЬКО текст + Reply Keyboard (БЕЗ inline!)
            await message.answer(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard()
            )
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            text = """
❓ *Помощь CryptoDen Bot*

*🎛 Панель управления* — открывает настройки:
• Запустить / Остановить бота
• API ключи Bybit
• Выбор монет
• Настройки рисков
• AI параметры

*Кнопки навигации:*
📊 Статус — текущее состояние
📈 Сделки — открытые позиции  
📰 Новости — рыночный контекст
📋 История — закрытые сделки

*Команды модулей:*
/grid — 📊 Grid Bot статус
/funding — 💰 Funding Scalper
/arb — 🔄 Arbitrage Scanner
/listing — 🆕 Listing Hunter
/listing\\_mode — сменить режим (signal/auto)

*AI команды:*
/ai — 🧠 Статус AI системы
/director — 🎩 Решения Директора
/director\\_trades — сделки Директора
/whale — 🐋 Анализ китов
/market — 📊 Полная картина рынка

*Сервис:*
/debug — 🔍 Диагностика
"""
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        # === WEBAPP DATA ===
        
        @self.dp.message(F.web_app_data)
        async def handle_webapp_data(message: types.Message):
            """Получение команд из WebApp"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                data = json.loads(message.web_app_data.data)
                action = data.get('action')
                
                if action == 'start_bot':
                    settings_data = data.get('settings', {})
                    self._apply_settings(settings_data)
                    
                    await message.answer("🚀 *Запускаю бота...*", parse_mode=ParseMode.MARKDOWN)
                    asyncio.create_task(self.monitor.start())
                    
                    await asyncio.sleep(2)
                    text = self._get_status_text()
                    await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
                elif action == 'stop_bot':
                    # Останавливаем smart notifications
                    await smart_notifications.stop()
                    
                    await self.monitor.stop()
                    text = "🛑 *Бот остановлен*\n\n" + self._get_status_text()
                    await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
                elif action == 'update_settings':
                    settings_data = data.get('settings', {})
                    self._apply_settings(settings_data)
                    await message.answer("✅ *Настройки сохранены*", parse_mode=ParseMode.MARKDOWN)
                    
            except Exception as e:
                logger.error(f"WebApp data error: {e}")
        
        # === REPLY KEYBOARD HANDLERS ===
        
        @self.dp.message(F.text == "📊 Статус")
        async def btn_status(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            text = self._get_status_text()
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(F.text == "📈 Сделки")
        async def btn_trades(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            trades = self.trade_manager.get_active_trades()
            
            if not trades:
                text = "📭 *Нет активных сделок*"
            else:
                text = f"📈 *Активные сделки ({len(trades)}):*\n"
                for t in trades:
                    emoji = "🟢" if t.unrealized_pnl >= 0 else "🔴"
                    dir_emoji = "📈" if t.direction == "LONG" else "📉"
                    text += f"""
{dir_emoji} *{t.symbol}* {t.direction}
┣ Вход: ${t.entry_price:,.4f}
┣ {emoji} P&L: {t.unrealized_pnl_percent:+.2f}%
┗ SL: ${t.stop_loss:,.2f} | TP: ${t.take_profit:,.2f}
"""
            await message.answer(text.strip(), parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(F.text == "📰 Новости")
        async def btn_news(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            # Загружаем новости ВСЕГДА, даже если бот остановлен
            loading_msg = await message.answer("📰 *Загружаю новости...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                # Получаем свежие новости
                from app.intelligence.news_parser import news_parser
                news_data = await news_parser.get_market_context()
                
                news = news_data.get('news', [])
                market_mode = news_data.get('market_mode', 'NORMAL')
                
                if not news:
                    await loading_msg.edit_text(
                        "📰 *Новости*\n\n_Нет актуальных новостей_",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                # Режим рынка
                mode_info = {
                    'NORMAL': ('🟢', 'Нормальный', 'Можно торговать'),
                    'NEWS_ALERT': ('🟡', 'Осторожность', 'Важные новости'),
                    'WAIT_EVENT': ('🔴', 'Ожидание', 'Важное событие скоро')
                }
                mode_emoji, mode_name, mode_desc = mode_info.get(market_mode, ('⚪', 'Неизвестно', ''))
                
                text = f"""📰 *Новости крипторынка*

{mode_emoji} *Режим: {mode_name}*
_{mode_desc}_

"""
                
                # Словарь переводов
                translations = {
                    'fed': '🏦 ФРС', 'rate': 'ставка', 'rates': 'ставки',
                    'fomc': 'заседание ФРС', 'powell': 'Пауэлл', 'inflation': 'инфляция',
                    'sec': '⚖️ SEC', 'etf': 'ETF', 'approve': 'одобрение',
                    'reject': 'отклонение', 'delay': 'отсрочка', 'regulation': 'регулирование',
                    'bitcoin': '₿ BTC', 'btc': '₿ BTC', 'halving': 'халвинг',
                    'whale': '🐋 кит', 'whales': '🐋 киты',
                    'ethereum': 'Ξ ETH', 'eth': 'Ξ ETH',
                    'rally': '📈 рост', 'crash': '📉 обвал', 'pump': '🚀 рост',
                    'dump': '💥 падение', 'bullish': '🐂 бычий', 'bearish': '🐻 медвежий',
                    'all-time high': '🏆 ATH', 'ath': '🏆 ATH',
                    'blackrock': '🏢 BlackRock', 'grayscale': '🏢 Grayscale',
                    'binance': 'Binance', 'coinbase': 'Coinbase',
                    'hack': '🔓 взлом', 'exploit': '🔓 эксплойт',
                    'lawsuit': '⚖️ иск', 'ban': '🚫 запрет',
                    'trump': '🇺🇸 Трамп', 'china': '🇨🇳 Китай',
                }
                
                def get_hint(title: str) -> str:
                    hints = []
                    title_lower = title.lower()
                    for eng, rus in translations.items():
                        if eng in title_lower and rus not in hints:
                            hints.append(rus)
                    return ' • '.join(hints[:3]) if hints else None
                
                def get_impact_emoji(sentiment: float, importance: str) -> str:
                    if importance == 'HIGH':
                        return '🔴' if sentiment < 0 else '🟢' if sentiment > 0 else '🟡'
                    elif importance == 'MEDIUM':
                        return '🟠' if sentiment < 0 else '🟢' if sentiment > 0 else '⚪'
                    return '⚪'
                
                def get_impact_text(sentiment: float) -> str:
                    if sentiment > 0.3:
                        return '💹 Позитивно'
                    elif sentiment < -0.3:
                        return '📉 Негативно'
                    return '➖ Нейтрально'
                
                # Новости
                for n in news[:6]:
                    title = n.get('title', '')
                    sentiment = n.get('sentiment', 0)
                    importance = n.get('importance', 'LOW')
                    
                    impact_emoji = get_impact_emoji(sentiment, importance)
                    hint = get_hint(title)
                    impact = get_impact_text(sentiment)
                    
                    if len(title) > 55:
                        title = title[:52] + '...'
                    
                    text += f"\n{impact_emoji} *{title}*\n"
                    if hint:
                        text += f"   📝 _{hint}_\n"
                    text += f"   {impact}\n"
                
                # События
                events = news_data.get('calendar', [])
                if events:
                    text += "\n📅 *События:*\n"
                    for e in events[:3]:
                        event_name = e.get('event', '')
                        text += f"⏰ {event_name}\n"
                
                from datetime import datetime
                text += f"\n_Обновлено: {datetime.now().strftime('%H:%M')}_"
                
                await loading_msg.edit_text(text.strip(), parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"News error: {e}")
                await loading_msg.edit_text(
                    f"📰 *Ошибка загрузки*\n\n_{str(e)[:80]}_",
                    parse_mode=ParseMode.MARKDOWN
                )
        
        @self.dp.message(F.text == "📋 История")
        async def btn_history(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            history = self.trade_manager.trade_history[-10:]
            
            if not history:
                await message.answer("📋 *История пуста*", parse_mode=ParseMode.MARKDOWN)
                return
            
            text = "📋 *Последние сделки:*\n\n"
            for t in reversed(history):
                emoji = "✅" if t.unrealized_pnl >= 0 else "❌"
                text += f"{emoji} {t.symbol}: {t.unrealized_pnl_percent:+.2f}%\n"
            
            stats = self.trade_manager.get_statistics()
            text += f"\n*Итого:* ${stats.get('total_pnl', 0):+.2f}"
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(F.text == "❓ Помощь")
        async def btn_help(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            text = """
❓ *Как пользоваться ботом*

1️⃣ Нажмите *🎛 Панель управления*
2️⃣ Настройте API ключи Bybit
3️⃣ Выберите монеты для торговли
4️⃣ Настройте риски
5️⃣ Нажмите *ЗАПУСТИТЬ БОТА*

*Правила:*
• 15% от баланса на сделку
• Максимум 6 сделок
• AI анализирует каждый сигнал

*Команды AI:*
/ai — полный статус AI системы
/director — решения Директора
/whale — анализ китов
/debug — диагностика
"""
            await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("debug"))
        async def cmd_debug(message: types.Message):
            """Диагностика бота"""
            if not self._is_admin(message.from_user.id):
                return
            
            loading = await message.answer("🔍 *Диагностика...*", parse_mode=ParseMode.MARKDOWN)
            
            text = "🔍 *ДИАГНОСТИКА*\n\n"
            
            # 1. Монитор
            text += "*1. Монитор:*\n"
            if self.monitor:
                text += f"• Running: {'✅' if self.monitor.running else '❌'}\n"
                text += f"• Symbols: {len(self.monitor.symbols)}\n"
                text += f"• AI: {'✅' if self.monitor.ai_enabled else '❌'}\n"
                text += f"• Paper: {'✅' if self.monitor.paper_trading else '❌ LIVE'}\n"
                text += f"• Balance: ${self.monitor.current_balance:,.2f}\n"
                text += f"• Cycles: {self.monitor.check_count}\n\n"
            else:
                text += "• ❌ Не инициализирован\n\n"
            
            # 2. Bybit
            text += "*2. Bybit API:*\n"
            try:
                from app.trading.bybit.client import BybitClient
                async with BybitClient(testnet=False) as client:
                    price = await client.get_price('BTC')
                    if price:
                        text += f"• Статус: ✅\n"
                        text += f"• BTC: ${price:,.2f}\n\n"
                    else:
                        text += "• Статус: ⚠️ Нет данных\n\n"
            except Exception as e:
                text += f"• Статус: ❌ {str(e)[:30]}\n\n"
            
            # 3. Стратегии
            text += "*3. Стратегии:*\n"
            try:
                from app.strategies import get_enabled_strategies, strategy_checker
                strategies = get_enabled_strategies()
                text += f"• Загружено: {len(strategies)}\n"
                status = strategy_checker.get_status()
                text += f"• Сигналов сегодня: {status.get('total_today', 0)}\n\n"
            except Exception as e:
                text += f"• Ошибка: {str(e)[:30]}\n\n"
            
            # 4. Кэш данных
            text += "*4. Кэш данных:*\n"
            try:
                from app.backtesting.data_loader import BybitDataLoader
                loader = BybitDataLoader()
                df = loader.load_from_cache('BTC', '5m')
                if df is not None and len(df) > 0:
                    text += f"• BTC: ✅ {len(df)} свечей\n"
                    text += f"• Цена: ${df['close'].iloc[-1]:,.2f}\n\n"
                else:
                    text += "• ⚠️ Нет данных в кэше\n\n"
            except Exception as e:
                text += f"• Ошибка: {str(e)[:30]}\n\n"
            
            # 5. Индикаторы BTC
            text += "*5. Индикаторы BTC:*\n"
            try:
                from app.strategies.indicators import TechnicalIndicators
                from app.backtesting.data_loader import BybitDataLoader
                loader = BybitDataLoader()
                df = loader.load_from_cache('BTC', '5m')
                if df is not None and len(df) >= 50:
                    df = df.tail(100).copy()
                    ind = TechnicalIndicators()
                    rsi = ind.rsi(df['close'], 14)
                    ema21 = ind.ema(df['close'], 21)
                    price = df['close'].iloc[-1]
                    
                    text += f"• RSI(14): {rsi:.1f}\n"
                    text += f"• EMA(21): ${ema21:,.0f}\n"
                    
                    # Анализ
                    rsi_ok = '✅' if rsi < 30 else '❌'
                    ema_ok = '✅' if price > ema21 else '❌'
                    text += f"• RSI<30: {rsi_ok}\n"
                    text += f"• Price>EMA: {ema_ok}\n\n"
                else:
                    text += "• ⚠️ Нет данных\n\n"
            except Exception as e:
                text += f"• Ошибка: {str(e)[:30]}\n\n"
            
            # 6. Новости
            text += "*6. Новости:*\n"
            try:
                from app.intelligence.news_parser import news_parser
                context = await news_parser.get_market_context()
                news_count = len(context.get('news', []))
                mode = context.get('market_mode', 'UNKNOWN')
                text += f"• Режим: {mode}\n"
                text += f"• Новостей: {news_count}\n\n"
            except Exception as e:
                text += f"• Ошибка: {str(e)[:30]}\n\n"
            
            # Вывод
            text += "\n💡 _Если RSI > 30 — сигналов не будет_\n"
            text += "_Это нормально! Бот ждёт подходящий момент._"
            
            await loading.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("whale"))
        async def cmd_whale(message: types.Message):
            """🐋 Whale AI — анализ рыночных метрик"""
            if not self._is_admin(message.from_user.id):
                return
            
            loading = await message.answer("🐋 *Анализирую рынок...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.ai.whale_ai import whale_ai, check_whale_activity
                
                # Анализируем BTC
                alert = await check_whale_activity("BTC")
                
                # Получаем отчёт
                text = whale_ai.get_status_text()
                text += f"\n\n*Рекомендация:*\n{alert.recommendation}"
                
                # Если есть алерты — добавляем
                if alert.level.value != "calm":
                    text += f"\n\n*⚠️ Сигналы:*\n{alert.message}"
                
                # Добавляем bias
                bias = whale_ai.get_trading_bias()
                bias_emoji = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"}.get(bias, "⚪")
                text += f"\n\n{bias_emoji} *Bias:* {bias}"
                
                await loading.edit_text(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Whale AI error: {e}")
                await loading.edit_text(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("brain"))
        async def cmd_brain(message: types.Message):
            """🧠 DirectorBrain — статус AI анализа рынка"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.ai.director_brain import director_brain
                text = director_brain.get_status_text()
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"DirectorBrain status error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("analyze"))
        async def cmd_analyze(message: types.Message):
            """🧠 DirectorBrain — принудительный анализ"""
            if not self._is_admin(message.from_user.id):
                return
            
            # Получаем символ из аргументов
            args = message.text.split()
            symbol = args[1].upper() if len(args) > 1 else "BTC"
            
            loading = await message.answer(f"🧠 *Анализирую {symbol}...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.ai.director_brain import director_brain
                
                # Принудительный анализ
                decision = await director_brain.analyze_symbol(symbol, force=True)
                
                emoji = "🟢" if decision.action == "LONG" else "🔴" if decision.action == "SHORT" else "⏸"
                manip_text = f"⚠️ {decision.manipulation_type.value}" if decision.manipulation_detected else "❌ Нет"
                
                entry_text = f"${decision.entry_price:,.2f}" if decision.entry_price else "N/A"
                sl_text = f"${decision.stop_loss:,.2f}" if decision.stop_loss else "N/A"
                tp_text = f"${decision.take_profit:,.2f}" if decision.take_profit else "N/A"
                
                text = f"""
🧠 *Анализ {symbol}*

{emoji} *Решение: {decision.action}*
📊 Уверенность: {decision.confidence}%

*Фаза рынка:* {decision.market_phase.value}
*Направление 1h:* {decision.direction_1h}
*Манипуляция:* {manip_text}

*Entry:* {entry_text}
*Stop Loss:* {sl_text}
*Take Profit:* {tp_text}

*Анализ:*
_{decision.reasoning[:400]}{'...' if len(decision.reasoning) > 400 else ''}_

*Ключевые факторы:*
"""
                for factor in decision.key_factors[:5]:
                    text += f"• {factor}\n"
                
                await loading.edit_text(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"DirectorBrain analyze error: {e}")
                await loading.edit_text(f"❌ *Ошибка анализа:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("grid"))
        async def cmd_grid(message: types.Message):
            """📊 Grid Bot — статус сетки ордеров"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.modules.grid_bot import grid_bot
                
                text = grid_bot.get_status_text()
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Grid status error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("funding"))
        async def cmd_funding(message: types.Message):
            """💰 Funding Scalper — статус"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.modules.funding_scalper import funding_scalper
                
                # Обновляем данные перед показом
                await funding_scalper.fetch_funding_rates()
                
                text = funding_scalper.get_status_text()
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Funding status error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("arb"))
        async def cmd_arbitrage(message: types.Message):
            """🔄 Arbitrage Scanner — статус"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.modules.arbitrage import arbitrage_scanner
                
                # Сканируем перед показом
                await arbitrage_scanner.scan_opportunities()
                
                text = arbitrage_scanner.get_status_text()
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Arbitrage status error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("listing"))
        async def cmd_listing(message: types.Message):
            """🆕 Listing Hunter — статус"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.modules.listing_hunter import listing_hunter
                
                text = listing_hunter.get_status_text()
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Listing status error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("listing_mode"))
        async def cmd_listing_mode(message: types.Message):
            """🆕 Изменить режим Listing Hunter"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.modules.listing_hunter import listing_hunter
                
                args = message.text.split()
                
                if len(args) < 2:
                    await message.answer(
                        "📋 *Использование:*\n"
                        "`/listing_mode auto` — авто-торговля\n"
                        "`/listing_mode signal` — только сигналы\n\n"
                        f"Текущий режим: *{listing_hunter.config.mode}*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                mode = args[1].lower()
                
                if listing_hunter.set_mode(mode):
                    emoji = "🤖" if mode == "auto" else "📢"
                    await message.answer(
                        f"{emoji} Режим изменён на: *{mode}*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await message.answer("❌ Неверный режим. Используйте: auto или signal")
                
            except Exception as e:
                logger.error(f"Listing mode error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("director"))
        async def cmd_director(message: types.Message):
            """🎩 Director AI — стратегические решения"""
            if not self._is_admin(message.from_user.id):
                return
            
            loading = await message.answer("🎩 *Анализирую ситуацию...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.ai.director_ai import director_ai, get_director_decision
                
                # Получаем решение
                command = await get_director_decision()
                
                # Статус
                text = director_ai.get_status_text()
                
                await loading.edit_text(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Director AI error: {e}")
                await loading.edit_text(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("director_trades"))
        async def cmd_director_trades(message: types.Message):
            """🎩 Сделки Director Trader"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.ai.director_ai import director_trader
                
                text = director_trader.get_status_text()
                
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Director trades error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("market"))
        async def cmd_market(message: types.Message):
            """📊 Полная картина рынка (все парсеры)"""
            if not self._is_admin(message.from_user.id):
                return
            
            loading = await message.answer("📊 *Собираю данные рынка...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.parsers.coinglass_parser import get_market_data
                from app.parsers.twitter_parser import twitter_parser
                from app.parsers.rss_parser import rss_parser
                
                # Собираем всё параллельно
                import asyncio
                market_task = get_market_data("BTC")
                whale_task = twitter_parser.get_whale_summary()
                news_task = rss_parser.get_news_summary()
                
                market, whale, news = await asyncio.gather(
                    market_task, whale_task, news_task,
                    return_exceptions=True
                )
                
                # Обрабатываем ошибки
                if isinstance(market, Exception):
                    market = {"liquidations": {}, "open_interest": {}, "funding": {}, "analysis": {}}
                if isinstance(whale, Exception):
                    whale = {}
                if isinstance(news, Exception):
                    news = {}
                
                # Формируем отчёт
                liq = market.get("liquidations", {})
                oi = market.get("open_interest", {})
                funding = market.get("funding", {})
                analysis = market.get("analysis", {})
                
                text = f"""📊 *ПОЛНАЯ КАРТИНА РЫНКА (BTC)*

🔥 *Ликвидации (1h):*
  📉 Long: ${liq.get('long_1h', 0)/1e6:.1f}M
  📈 Short: ${liq.get('short_1h', 0)/1e6:.1f}M
  🎯 Dominant: {liq.get('dominant', 'neutral')}

📈 *Open Interest:*
  📊 Change 1h: {oi.get('change_1h', 0):+.1f}%
  📊 Change 24h: {oi.get('change_24h', 0):+.1f}%
  📈 Trend: {oi.get('trend', 'neutral')}

💰 *Funding:*
  💵 Rate: {funding.get('current', 0):+.4f}%
  🎯 Sentiment: {funding.get('sentiment', 'neutral')}

🐋 *Киты (Twitter):*
  💸 Net Flow: ${whale.get('net_flow', 0)/1e6:+.1f}M
  🎯 Sentiment: {whale.get('sentiment', 'neutral')}

📰 *Новости (RSS):*
  📊 Total: {news.get('total', 0)}
  🚨 Critical: {news.get('critical', 0)}
  🎯 Sentiment: {news.get('sentiment', 'neutral')}

🎯 *Анализ:*
  ⚠️ Risk Score: {analysis.get('risk_score', 0)}/100
  📊 Overall: {analysis.get('overall_sentiment', 'neutral')}
"""
                
                # Добавляем сигналы
                signals = analysis.get('signals', [])
                if signals:
                    text += "\n*⚠️ Сигналы:*\n"
                    for s in signals[:5]:
                        text += f"  • {s}\n"
                
                await loading.edit_text(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Market data error: {e}")
                await loading.edit_text(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("ai"))
        async def cmd_ai_status(message: types.Message):
            """📊 Полный статус AI системы"""
            if not self._is_admin(message.from_user.id):
                return
            
            loading = await message.answer("🔄 *Собираю данные...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.ai.whale_ai import whale_ai
                from app.ai.director_ai import director_ai
                from app.ai.trading_coordinator import trading_coordinator
                
                # Whale AI (не делаем запрос, используем кэш)
                whale_text = "🐋 *Whale AI*\n"
                if whale_ai.last_metrics:
                    m = whale_ai.last_metrics
                    whale_text += f"• Funding: {m.funding_rate:+.4f}%\n"
                    whale_text += f"• L/S: {m.long_ratio:.0f}% / {m.short_ratio:.0f}%\n"
                    whale_text += f"• F&G: {m.fear_greed}\n"
                else:
                    whale_text += "• _Нет данных_\n"
                
                # Director AI
                director_text = "\n🎩 *Director AI*\n"
                director_text += f"• Mode: {director_ai.current_mode.value}\n"
                if director_ai.situation:
                    s = director_ai.situation
                    risk_emoji = {"normal": "🟢", "elevated": "🟡", "high": "🟠", "extreme": "🔴"}
                    director_text += f"• Risk: {risk_emoji.get(s.risk_level, '⚪')} {s.risk_level} ({s.risk_score}/100)\n"
                director_text += f"• LONG: {'✅' if director_ai.allow_new_longs else '🚫'}\n"
                director_text += f"• SHORT: {'✅' if director_ai.allow_new_shorts else '🚫'}\n"
                director_text += f"• Size: x{director_ai.size_multiplier:.1f}\n"
                
                # Coordinator
                coord_text = "\n🎯 *Coordinator*\n"
                coord_text += f"• Сигналов: {trading_coordinator.signals_generated}\n"
                coord_text += f"• Выполнено: {trading_coordinator.actions_executed}\n"
                coord_text += f"• Вмешательств: {trading_coordinator.director_interventions}\n"
                
                # Monitor
                monitor_text = "\n📊 *Monitor*\n"
                monitor_text += f"• Running: {'✅' if self.monitor.running else '❌'}\n"
                monitor_text += f"• Cycles: {self.monitor.check_count}\n"
                monitor_text += f"• Balance: ${self.monitor.current_balance:,.2f}\n"
                
                text = f"""🧠 *AI SYSTEM STATUS*

{whale_text}
{director_text}
{coord_text}
{monitor_text}
"""
                
                await loading.edit_text(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"AI status error: {e}")
                await loading.edit_text(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
    
    # === УВЕДОМЛЕНИЯ ===
    
    async def send_message(self, text: str):
        if not self.enabled:
            return
        try:
            await self.bot.send_message(self.admin_id, text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Telegram error: {e}")
    
    async def notify_signal(self, signal):
        emoji = "📈" if signal.direction == "LONG" else "📉"
        text = f"""
{emoji} *СИГНАЛ: {signal.symbol}*

{signal.direction} • {signal.strategy_name}
WR: {signal.win_rate:.1f}%

Entry: ${signal.entry_price:,.4f}
"""
        await self.send_message(text.strip())
    
    async def notify_trade_opened(self, trade):
        emoji = "📈" if trade.direction == "LONG" else "📉"
        text = f"""
✅ *ОТКРЫТА: {trade.symbol}*

{emoji} {trade.direction} • ${trade.value_usdt:,.2f}
🎯 Entry: ${trade.entry_price:,.4f}
"""
        await self.send_message(text.strip())
    
    async def notify_trade_closed(self, trade):
        emoji = "✅" if trade.unrealized_pnl >= 0 else "❌"
        reason = trade.close_reason.value if trade.close_reason else "manual"
        text = f"""
{emoji} *ЗАКРЫТА: {trade.symbol}*

P&L: *{trade.unrealized_pnl_percent:+.2f}%* (${trade.unrealized_pnl:+.2f})
Причина: {reason}
"""
        await self.send_message(text.strip())
    
    async def notify_ai_decision(self, decision):
        text = f"""
🧠 *AI: {decision.action.value.upper()}*

Confidence: {decision.confidence}%
{decision.reason}
"""
        await self.send_message(text.strip())
    
    async def notify_error(self, error: str):
        await self.send_message(f"⚠️ *Ошибка:* {error}")
    
    async def start_polling(self):
        if not self.enabled:
            return
        await self._set_commands()
        
        # Настраиваем smart notifications
        smart_notifications.set_send_callback(self.send_message)
        
        # Инициализируем файл статуса (бот остановлен)
        update_bot_status_file(running=False)
        
        # Запускаем фоновую проверку запроса запуска из WebApp
        asyncio.create_task(self._check_start_request())
        
        logger.info("📱 Telegram bot started")
        await self.dp.start_polling(self.bot)
    
    async def _check_start_request(self):
        """Проверяет запросы на запуск/остановку из WebApp каждые 2 секунды"""
        while True:
            try:
                # Проверяем запрос на ЗАПУСК
                if os.path.exists(START_REQUESTED_FILE):
                    with open(START_REQUESTED_FILE, 'r') as f:
                        data = json.load(f)
                    
                    if data.get('requested') and not self.monitor.running:
                        os.remove(START_REQUESTED_FILE)
                        settings_data = data.get('settings', {})
                        await self._apply_settings_and_start(settings_data)
                
                # Проверяем запрос на ОСТАНОВКУ
                if os.path.exists(STOP_REQUESTED_FILE):
                    os.remove(STOP_REQUESTED_FILE)
                    
                    if self.monitor.running:
                        # Останавливаем smart notifications
                        await smart_notifications.stop()
                        
                        await self.monitor.stop()
                        
                        # Обновляем статус для WebApp
                        update_bot_status_file(running=False)
                        
                        await self.send_message("🛑 *Бот остановлен через WebApp*")
                        
                        text = self._get_status_text()
                        await self.bot.send_message(self.admin_id, text, parse_mode=ParseMode.MARKDOWN)
                        
            except Exception as e:
                logger.error(f"Check request error: {e}")
            
            await asyncio.sleep(2)
    
    async def _apply_settings_and_start(self, settings_data: dict):
        """Применить настройки из WebApp и запустить бота"""
        try:
            self._apply_settings(settings_data)
            
            logger.info(f"📱 WebApp settings applied: {len(self.monitor.symbols)} coins")
            
            # Уведомляем
            await self.send_message("🚀 *Запускаю бота из WebApp...*")
            
            # Запускаем smart notifications
            await smart_notifications.start()
            
            # Запускаем последовательность презентации модулей
            startup_data = {
                "btc_price": self.monitor.current_balance,  # Временно
                "btc_rsi": 50,
                "fear_greed": 50,
                "coins_count": len(self.monitor.symbols),
                "minutes_to_funding": 120,
            }
            asyncio.create_task(smart_notifications.send_startup_sequence(startup_data))
            
            # Запускаем
            asyncio.create_task(self.monitor.start())
            
            await asyncio.sleep(3)
            
            # Обновляем статус для WebApp
            update_bot_status_file(
                running=True,
                balance=self.monitor.current_balance,
                active_trades=len(self.trade_manager.get_active_trades()),
                paper_trading=self.monitor.paper_trading,
                ai_enabled=self.monitor.ai_enabled
            )
            
            # Отправляем статус
            text = self._get_status_text()
            await self.bot.send_message(self.admin_id, text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Apply settings error: {e}")
            await self.send_message(f"❌ *Ошибка:* {e}")
    
    async def stop(self):
        if self.bot:
            await self.bot.session.close()


telegram_bot = TelegramBot()
