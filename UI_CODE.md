# 🎨 CryptoDen UI Code — Telegram Bot + WebApp

> **Дата:** 2026-01-28  
> **Содержит:** Полный код Telegram бота, клавиатур и WebApp

---

## 📋 СОДЕРЖАНИЕ

1. [telegram_bot.py](#1-telegram_botpy)
2. [keyboards.py](#2-keyboardspy)
3. [webapp.html](#3-webapphtml)

---

## 1. telegram_bot.py

**Путь:** `app/notifications/telegram_bot.py`

```python
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
        """Текст статуса — БЕЗ кнопок!"""
        
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
        mode = "📝 Paper" if self.monitor.paper_trading else "💰 LIVE"
        
        text = f"""
{status}

🧠 AI: {ai}  •  {mode}

━━━━━━━━━━━━━━━━━━━━━━
💰 *Баланс:* ${balance:,.2f}
💵 *Сделка:* ${trade_size:,.2f} ({percent}%)
📊 *Позиции:* {active}/{max_trades}
━━━━━━━━━━━━━━━━━━━━━━
📈 *Сегодня:* ${today_pnl:+,.2f}
💎 *Всего:* ${total_pnl:+,.2f}
🎯 *Win Rate:* {win_rate:.1f}%

_Управление через 🎛 Панель управления_
"""
        return text.strip()
    
    def _apply_settings(self, settings_data: dict):
        """Применить настройки из WebApp"""
        if not settings_data:
            return
        
        self.monitor.ai_enabled = settings_data.get('ai_enabled', True)
        self.monitor.paper_trading = settings_data.get('paper_trading', True)
        self.monitor.balance_percent_per_trade = settings_data.get('risk_percent', 15) / 100
        self.monitor.max_open_trades = settings_data.get('max_trades', 6)
        self.monitor.min_confidence = settings_data.get('ai_confidence', 60)
        
        coins = settings_data.get('coins', {})
        self.monitor.symbols = [c for c, enabled in coins.items() if enabled]
    
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

━━━━━━━━━━━━━━━━━━━━━━
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
                    text += "\n━━━━━━━━━━━━━━━━━━━━━━\n📅 *События:*\n"
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
            text += "━━━━━━━━━━━━━━━━━━━━━━\n"
            text += "💡 _Если RSI > 30 — сигналов не будет_\n"
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
```

---

## 2. keyboards.py

**Путь:** `app/bot/keyboards.py`

```python
"""
Telegram Keyboards — Только навигация
Управление ботом через WebApp!
"""
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)
from app.core.config import settings


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Главная клавиатура — только навигация
    БЕЗ кнопок Запустить/Остановить (они в WebApp)
    """
    
    webapp_url = settings.webapp_url or "https://app.cryptoden.ru"
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            # Панель управления — WebApp
            [KeyboardButton(
                text="🎛 Панель управления",
                web_app=WebAppInfo(url=webapp_url)
            )],
            # Навигация
            [
                KeyboardButton(text="📊 Статус"),
                KeyboardButton(text="📈 Сделки")
            ],
            [
                KeyboardButton(text="📰 Новости"),
                KeyboardButton(text="📋 История")
            ],
            # Помощь
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    return keyboard
```

---

## 3. webapp.html

**Путь:** `app/webapp/templates/webapp.html`

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>CryptoDen | Settings</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 50%, #d9e2ec 100%);
            min-height: 100vh;
            overflow-x: hidden;
            position: relative;
        }
        
        /* ==================== ANIMATED BACKGROUND ==================== */
        .bg-container {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            z-index: 0;
            pointer-events: none;
        }
        
        .chart-lines {
            position: absolute;
            width: 100%;
            height: 100%;
            opacity: 0.15;
        }
        
        .chart-line {
            position: absolute;
            height: 2px;
            background: linear-gradient(90deg, transparent, #3b82f6, #06b6d4, transparent);
            animation: chartMove 8s ease-in-out infinite;
        }
        
        .chart-line:nth-child(1) { top: 20%; width: 60%; left: -10%; animation-delay: 0s; }
        .chart-line:nth-child(2) { top: 35%; width: 80%; left: 20%; animation-delay: 1s; }
        .chart-line:nth-child(3) { top: 50%; width: 70%; left: -5%; animation-delay: 2s; }
        .chart-line:nth-child(4) { top: 65%; width: 90%; left: 10%; animation-delay: 3s; }
        .chart-line:nth-child(5) { top: 80%; width: 50%; left: 30%; animation-delay: 4s; }
        
        @keyframes chartMove {
            0%, 100% { transform: translateX(-20%) scaleY(1); opacity: 0.3; }
            50% { transform: translateX(20%) scaleY(2); opacity: 0.6; }
        }
        
        .floating-coins {
            position: absolute;
            width: 100%;
            height: 100%;
        }
        
        .coin {
            position: absolute;
            opacity: 0.12;
            animation: float 20s ease-in-out infinite;
        }
        
        .coin:nth-child(1) { top: 10%; left: 5%; animation-delay: 0s; }
        .coin:nth-child(2) { top: 25%; right: 10%; animation-delay: 2s; }
        .coin:nth-child(3) { top: 45%; left: 8%; animation-delay: 4s; }
        .coin:nth-child(4) { top: 60%; right: 5%; animation-delay: 6s; }
        .coin:nth-child(5) { top: 75%; left: 15%; animation-delay: 8s; }
        
        @keyframes float {
            0%, 100% { transform: translateY(0) rotate(0deg) scale(1); }
            25% { transform: translateY(-20px) rotate(5deg) scale(1.05); }
            50% { transform: translateY(-10px) rotate(-3deg) scale(1.02); }
            75% { transform: translateY(-25px) rotate(3deg) scale(1.08); }
        }
        
        .particles {
            position: absolute;
            width: 100%;
            height: 100%;
        }
        
        .particle {
            position: absolute;
            width: 4px;
            height: 4px;
            background: linear-gradient(135deg, #3b82f6, #06b6d4);
            border-radius: 50%;
            animation: sparkle 4s ease-in-out infinite;
        }
        
        .particle:nth-child(1) { top: 15%; left: 20%; animation-delay: 0s; }
        .particle:nth-child(2) { top: 30%; right: 15%; animation-delay: 0.5s; }
        .particle:nth-child(3) { top: 50%; left: 10%; animation-delay: 1s; }
        .particle:nth-child(4) { top: 70%; right: 25%; animation-delay: 1.5s; }
        .particle:nth-child(5) { top: 85%; left: 30%; animation-delay: 2s; }
        
        @keyframes sparkle {
            0%, 100% { opacity: 0.2; transform: scale(1); }
            50% { opacity: 0.8; transform: scale(1.5); }
        }
        
        /* ==================== MAIN CONTENT ==================== */
        .main-container {
            position: relative;
            z-index: 1;
            padding: 20px;
            padding-bottom: 40px;
            max-width: 500px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            padding: 20px 0;
            animation: fadeInDown 0.6s ease;
        }
        
        .logo {
            font-size: 48px;
            margin-bottom: 10px;
            animation: pulse 2s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        
        .header h1 {
            font-size: 28px;
            font-weight: 700;
            background: linear-gradient(135deg, #1e3a5f, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }
        
        .header p {
            color: #64748b;
            font-size: 14px;
            font-weight: 500;
        }
        
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* ==================== CONTROL CARD ==================== */
        .control-card {
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.9);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
            padding: 24px;
            margin-bottom: 20px;
            animation: fadeInUp 0.5s ease;
        }
        
        .bot-status-display {
            margin-bottom: 20px;
        }
        
        .status-indicator {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            margin-bottom: 12px;
        }
        
        .status-dot {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: #94a3b8;
            transition: all 0.3s ease;
        }
        
        .status-dot.stopped {
            background: #ef4444;
            box-shadow: 0 0 12px rgba(239, 68, 68, 0.5);
            animation: pulse-red 2s infinite;
        }
        
        .status-dot.running {
            background: #22c55e;
            box-shadow: 0 0 12px rgba(34, 197, 94, 0.5);
            animation: pulse-green 2s infinite;
        }
        
        @keyframes pulse-red {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.7; transform: scale(1.2); }
        }
        
        @keyframes pulse-green {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.8; transform: scale(1.15); }
        }
        
        .status-text {
            font-size: 18px;
            font-weight: 700;
            color: #1e293b;
        }
        
        .status-info {
            display: flex;
            justify-content: center;
            gap: 20px;
            font-size: 13px;
            color: #64748b;
            flex-wrap: wrap;
        }
        
        .status-info-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .main-control-btn {
            width: 100%;
            padding: 18px 32px;
            border: none;
            border-radius: 14px;
            font-size: 18px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            transition: all 0.3s ease;
        }
        
        .main-control-btn:disabled {
            background: #e2e8f0;
            color: #94a3b8;
            cursor: not-allowed;
        }
        
        .main-control-btn.start {
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: white;
            box-shadow: 0 6px 20px rgba(34, 197, 94, 0.4);
        }
        
        .main-control-btn.start:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 28px rgba(34, 197, 94, 0.5);
        }
        
        .main-control-btn.stop {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: white;
            box-shadow: 0 6px 20px rgba(239, 68, 68, 0.4);
        }
        
        .main-control-btn.stop:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 28px rgba(239, 68, 68, 0.5);
        }
        
        .main-control-btn .btn-icon {
            font-size: 22px;
        }
        
        .main-control-btn.loading {
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            pointer-events: none;
        }
        
        .main-control-btn.loading .btn-icon {
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        
        /* ==================== CARDS ==================== */
        .card {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.8);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.04);
            margin-bottom: 16px;
            overflow: hidden;
            animation: fadeInUp 0.6s ease;
            animation-fill-mode: both;
        }
        
        .card:nth-child(2) { animation-delay: 0.1s; }
        .card:nth-child(3) { animation-delay: 0.2s; }
        .card:nth-child(4) { animation-delay: 0.3s; }
        .card:nth-child(5) { animation-delay: 0.4s; }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 18px 20px;
            cursor: pointer;
            transition: background 0.3s ease;
            user-select: none;
        }
        
        .card-header:hover {
            background: rgba(59, 130, 246, 0.05);
        }
        
        .card-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .card-icon {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            background: linear-gradient(135deg, #3b82f6, #06b6d4);
            color: white;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }
        
        .card-title h3 {
            font-size: 16px;
            font-weight: 600;
            color: #1e293b;
        }
        
        .card-title .subtitle {
            font-size: 12px;
            color: #64748b;
            margin-top: 2px;
        }
        
        .card-arrow {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: rgba(59, 130, 246, 0.1);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #3b82f6;
            font-size: 12px;
            transition: all 0.3s ease;
        }
        
        .card.open .card-arrow {
            transform: rotate(180deg);
            background: #3b82f6;
            color: white;
        }
        
        .card-content {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            padding: 0 20px;
        }
        
        .card.open .card-content {
            max-height: 600px;
            padding: 0 20px 20px;
        }
        
        .status-badge {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 8px;
        }
        
        .status-badge.success {
            background: rgba(34, 197, 94, 0.15);
            color: #16a34a;
        }
        
        .status-badge.warning {
            background: rgba(245, 158, 11, 0.15);
            color: #d97706;
        }
        
        /* ==================== INPUTS ==================== */
        .input-group {
            margin-bottom: 16px;
        }
        
        .input-group label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: #475569;
            margin-bottom: 8px;
        }
        
        .input-wrapper {
            position: relative;
        }
        
        .input-wrapper input {
            width: 100%;
            padding: 14px 16px;
            padding-right: 50px;
            border: 2px solid #e2e8f0;
            border-radius: 12px;
            font-size: 15px;
            color: #1e293b;
            background: rgba(255, 255, 255, 0.8);
            transition: all 0.3s ease;
        }
        
        .input-wrapper input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.15);
        }
        
        .input-toggle {
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            font-size: 18px;
            cursor: pointer;
            opacity: 0.5;
            transition: opacity 0.3s;
        }
        
        .input-toggle:hover {
            opacity: 1;
        }
        
        .toggle-group {
            display: flex;
            gap: 10px;
            margin-top: 16px;
        }
        
        .toggle-btn {
            flex: 1;
            padding: 14px 16px;
            border: 2px solid #e2e8f0;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.6);
            font-size: 14px;
            font-weight: 600;
            color: #64748b;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        
        .toggle-btn:hover {
            border-color: #3b82f6;
            background: rgba(59, 130, 246, 0.05);
        }
        
        .toggle-btn.active {
            border-color: #3b82f6;
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(6, 182, 212, 0.1));
            color: #3b82f6;
        }
        
        .toggle-btn.active.danger {
            border-color: #ef4444;
            background: rgba(239, 68, 68, 0.1);
            color: #ef4444;
        }
        
        /* ==================== COINS GRID ==================== */
        .coins-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }
        
        .coin-btn {
            padding: 14px 8px;
            border: 2px solid #e2e8f0;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.6);
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
        }
        
        .coin-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        
        .coin-btn.active {
            border-color: #22c55e;
            background: rgba(34, 197, 94, 0.1);
        }
        
        .coin-btn .coin-icon {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 12px;
            color: white;
        }
        
        .coin-btn .coin-name {
            font-size: 12px;
            font-weight: 600;
            color: #475569;
        }
        
        .coin-btn .coin-status {
            font-size: 10px;
            color: #94a3b8;
        }
        
        .coin-btn.active .coin-status {
            color: #22c55e;
        }
        
        .coin-btc { background: linear-gradient(135deg, #f7931a, #ffab40); }
        .coin-eth { background: linear-gradient(135deg, #627eea, #8c9eff); }
        .coin-bnb { background: linear-gradient(135deg, #f3ba2f, #ffd54f); }
        .coin-sol { background: linear-gradient(135deg, #9945ff, #14f195); }
        .coin-xrp { background: linear-gradient(135deg, #23292f, #546e7a); }
        .coin-ada { background: linear-gradient(135deg, #0033ad, #1e88e5); }
        .coin-doge { background: linear-gradient(135deg, #c2a633, #ffca28); }
        .coin-link { background: linear-gradient(135deg, #2a5ada, #5c6bc0); }
        .coin-avax { background: linear-gradient(135deg, #e84142, #ff5252); }
        
        /* ==================== SLIDERS ==================== */
        .slider-group {
            margin-bottom: 20px;
        }
        
        .slider-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        
        .slider-label {
            font-size: 14px;
            font-weight: 600;
            color: #475569;
        }
        
        .slider-value {
            font-size: 16px;
            font-weight: 700;
            color: #3b82f6;
            background: rgba(59, 130, 246, 0.1);
            padding: 4px 12px;
            border-radius: 8px;
        }
        
        .slider-wrapper {
            position: relative;
            height: 8px;
            background: #e2e8f0;
            border-radius: 4px;
            overflow: visible;
        }
        
        .slider-fill {
            position: absolute;
            left: 0;
            top: 0;
            height: 100%;
            background: linear-gradient(90deg, #3b82f6, #06b6d4);
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        
        input[type="range"] {
            position: absolute;
            width: 100%;
            height: 100%;
            top: 0;
            left: 0;
            opacity: 0;
            cursor: pointer;
            -webkit-appearance: none;
        }
        
        .slider-thumb {
            position: absolute;
            top: 50%;
            transform: translate(-50%, -50%);
            width: 24px;
            height: 24px;
            background: white;
            border: 3px solid #3b82f6;
            border-radius: 50%;
            box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
            transition: all 0.3s ease;
            pointer-events: none;
        }
        
        .warning-box {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 12px;
            padding: 14px 16px;
            margin-top: 16px;
            font-size: 13px;
            color: #dc2626;
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }
        
        .warning-box.hidden {
            display: none;
        }
        
        .info-text {
            font-size: 12px;
            color: #94a3b8;
            text-align: center;
            margin-top: 12px;
        }
        
        @media (max-width: 380px) {
            .coins-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            .header h1 {
                font-size: 24px;
            }
        }
    </style>
</head>
<body>
    <!-- Animated Background -->
    <div class="bg-container">
        <div class="chart-lines">
            <div class="chart-line"></div>
            <div class="chart-line"></div>
            <div class="chart-line"></div>
            <div class="chart-line"></div>
            <div class="chart-line"></div>
        </div>
        
        <div class="floating-coins">
            <div class="coin" style="width: 60px;">
                <svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="16" fill="#f7931a"/><path d="M22.5 14.2c.3-2-1.2-3-3.3-3.8l.7-2.7-1.6-.4-.7 2.7c-.4-.1-.8-.2-1.3-.3l.7-2.7-1.6-.4-.7 2.7c-.3-.1-.7-.2-1-.2l-2.3-.6-.4 1.7s1.2.3 1.2.3c.7.2.8.6.8 1l-.8 3.2c0 .1.1.1.1.2h-.1l-1.1 4.5c-.1.2-.3.5-.8.4 0 0-1.2-.3-1.2-.3l-.8 1.9 2.1.5c.4.1.8.2 1.2.3l-.7 2.8 1.6.4.7-2.8c.4.1.9.2 1.3.3l-.7 2.7 1.6.4.7-2.8c2.9.6 5.1.3 6-2.3.7-2.1 0-3.3-1.5-4 1.1-.3 1.9-1 2.1-2.5z" fill="white"/></svg>
            </div>
            <div class="coin" style="width: 50px;">
                <svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="16" fill="#627eea"/><path d="M16 4v8.9l7.5 3.3L16 4z" fill="white" fill-opacity="0.6"/><path d="M16 4l-7.5 12.2 7.5-3.3V4z" fill="white"/></svg>
            </div>
            <div class="coin" style="width: 45px;">
                <svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="16" fill="url(#sol)"/><defs><linearGradient id="sol" x1="0" y1="0" x2="32" y2="32"><stop stop-color="#9945ff"/><stop offset="1" stop-color="#14f195"/></linearGradient></defs></svg>
            </div>
            <div class="coin" style="width: 55px;">
                <svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="16" fill="#f3ba2f"/><path d="M16 6l3 3-5 5-3-3 5-5zm-6 6l3 3-3 3-3-3 3-3zm12 0l3 3-3 3-3-3 3-3zm-6 6l3 3-5 5-3-3 5-5z" fill="white"/></svg>
            </div>
            <div class="coin" style="width: 40px;">
                <svg viewBox="0 0 32 32" fill="none"><circle cx="16" cy="16" r="16" fill="#23292f"/><path d="M10 10h2.5l3.5 4.5L19.5 10H22l-5 6.5v.5l5 6.5h-2.5L16 19l-3.5 4.5H10l5-6.5v-.5L10 10z" fill="white"/></svg>
            </div>
        </div>
        
        <div class="particles">
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
            <div class="particle"></div>
        </div>
    </div>
    
    <!-- Main Content -->
    <div class="main-container">
        <!-- Header -->
        <div class="header">
            <div class="logo">🤖</div>
            <h1>CryptoDen</h1>
            <p>Professional AI Trading Bot</p>
        </div>
        
        <!-- Control Card with Dynamic Button -->
        <div class="control-card" id="control-card">
            <div class="bot-status-display">
                <div class="status-indicator">
                    <span class="status-dot" id="status-dot"></span>
                    <span class="status-text" id="status-text">Проверка...</span>
                </div>
                <div class="status-info" id="status-info">
                    <!-- Filled by JS -->
                </div>
            </div>
            
            <button class="main-control-btn" id="main-control-btn" onclick="handleMainAction()" disabled>
                <span class="btn-icon" id="btn-icon">⏳</span>
                <span class="btn-text" id="btn-text">Загрузка...</span>
            </button>
        </div>
        
        <!-- Settings Cards (shown only when bot is stopped) -->
        <div id="settings-section">
            <!-- API Keys -->
            <div class="card" id="card-api">
                <div class="card-header" onclick="toggleCard('api')">
                    <div class="card-title">
                        <div class="card-icon">🔐</div>
                        <div>
                            <h3>API Ключи <span class="status-badge warning" id="api-status">Не настроено</span></h3>
                            <div class="subtitle">Подключение к Bybit</div>
                        </div>
                    </div>
                    <div class="card-arrow">▼</div>
                </div>
                <div class="card-content">
                    <div class="input-group">
                        <label>API Key</label>
                        <div class="input-wrapper">
                            <input type="password" id="api-key" placeholder="Введите ваш API ключ">
                            <button class="input-toggle" onclick="togglePassword('api-key')">👁️</button>
                        </div>
                    </div>
                    <div class="input-group">
                        <label>API Secret</label>
                        <div class="input-wrapper">
                            <input type="password" id="api-secret" placeholder="Введите ваш Secret">
                            <button class="input-toggle" onclick="togglePassword('api-secret')">👁️</button>
                        </div>
                    </div>
                    <div class="toggle-group">
                        <button class="toggle-btn active" id="btn-testnet" onclick="setNetwork('testnet')">🧪 Testnet</button>
                        <button class="toggle-btn" id="btn-mainnet" onclick="setNetwork('mainnet')">💰 Mainnet</button>
                    </div>
                </div>
            </div>
            
            <!-- Coins -->
            <div class="card" id="card-coins">
                <div class="card-header" onclick="toggleCard('coins')">
                    <div class="card-title">
                        <div class="card-icon">🪙</div>
                        <div>
                            <h3>Монеты</h3>
                            <div class="subtitle" id="coins-count">Выбрано: 7 из 9</div>
                        </div>
                    </div>
                    <div class="card-arrow">▼</div>
                </div>
                <div class="card-content">
                    <div class="coins-grid" id="coins-grid"></div>
                    <p class="info-text">Стратегии оптимизированы на основе бэктеста 2022-2025</p>
                </div>
            </div>
            
            <!-- Risk -->
            <div class="card" id="card-risk">
                <div class="card-header" onclick="toggleCard('risk')">
                    <div class="card-title">
                        <div class="card-icon">💰</div>
                        <div>
                            <h3>Управление рисками</h3>
                            <div class="subtitle">Размер позиций и лимиты</div>
                        </div>
                    </div>
                    <div class="card-arrow">▼</div>
                </div>
                <div class="card-content">
                    <div class="slider-group">
                        <div class="slider-header">
                            <span class="slider-label">Размер сделки</span>
                            <span class="slider-value" id="risk-value">15%</span>
                        </div>
                        <div class="slider-wrapper">
                            <div class="slider-fill" id="risk-fill" style="width: 50%"></div>
                            <div class="slider-thumb" id="risk-thumb" style="left: 50%"></div>
                            <input type="range" id="risk-slider" min="5" max="25" value="15" oninput="updateSlider('risk')">
                        </div>
                    </div>
                    <div class="slider-group">
                        <div class="slider-header">
                            <span class="slider-label">Макс. сделок</span>
                            <span class="slider-value" id="trades-value">6</span>
                        </div>
                        <div class="slider-wrapper">
                            <div class="slider-fill" id="trades-fill" style="width: 55%"></div>
                            <div class="slider-thumb" id="trades-thumb" style="left: 55%"></div>
                            <input type="range" id="trades-slider" min="1" max="10" value="6" oninput="updateSlider('trades')">
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- AI -->
            <div class="card" id="card-ai">
                <div class="card-header" onclick="toggleCard('ai')">
                    <div class="card-title">
                        <div class="card-icon">🧠</div>
                        <div>
                            <h3>AI Настройки</h3>
                            <div class="subtitle">Claude Sonnet</div>
                        </div>
                    </div>
                    <div class="card-arrow">▼</div>
                </div>
                <div class="card-content">
                    <div class="toggle-group">
                        <button class="toggle-btn active" id="btn-ai-on" onclick="setAI(true)">✅ AI Включён</button>
                        <button class="toggle-btn" id="btn-ai-off" onclick="setAI(false)">❌ Без AI</button>
                    </div>
                    <div class="slider-group" style="margin-top: 20px;">
                        <div class="slider-header">
                            <span class="slider-label">Мин. уверенность</span>
                            <span class="slider-value" id="confidence-value">60%</span>
                        </div>
                        <div class="slider-wrapper">
                            <div class="slider-fill" id="confidence-fill" style="width: 50%"></div>
                            <div class="slider-thumb" id="confidence-thumb" style="left: 50%"></div>
                            <input type="range" id="confidence-slider" min="30" max="90" value="60" oninput="updateSlider('confidence')">
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Mode -->
            <div class="card" id="card-mode">
                <div class="card-header" onclick="toggleCard('mode')">
                    <div class="card-title">
                        <div class="card-icon">📊</div>
                        <div>
                            <h3>Режим торговли</h3>
                            <div class="subtitle" id="mode-subtitle">Paper Trading</div>
                        </div>
                    </div>
                    <div class="card-arrow">▼</div>
                </div>
                <div class="card-content">
                    <div class="toggle-group">
                        <button class="toggle-btn active" id="btn-paper" onclick="setMode('paper')">📝 Paper</button>
                        <button class="toggle-btn" id="btn-live" onclick="setMode('live')">💰 Live</button>
                    </div>
                    <div class="warning-box hidden" id="live-warning">
                        <span>⚠️</span>
                        <span>LIVE режим торгует реальными деньгами!</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        tg.enableClosingConfirmation();
        
        let botRunning = false;
        let botData = {};
        
        let settings = {
            bybit_api_key: "",
            bybit_api_secret: "",
            bybit_testnet: true,
            coins: {
                BTC: true, ETH: true, BNB: true,
                SOL: true, XRP: true, ADA: true,
                DOGE: true, LINK: false, AVAX: false
            },
            risk_percent: 15,
            max_trades: 6,
            ai_enabled: true,
            ai_confidence: 60,
            paper_trading: true
        };
        
        const coinsData = [
            { id: 'BTC', name: 'Bitcoin', color: 'coin-btc' },
            { id: 'ETH', name: 'Ethereum', color: 'coin-eth' },
            { id: 'BNB', name: 'BNB', color: 'coin-bnb' },
            { id: 'SOL', name: 'Solana', color: 'coin-sol' },
            { id: 'XRP', name: 'Ripple', color: 'coin-xrp' },
            { id: 'ADA', name: 'Cardano', color: 'coin-ada' },
            { id: 'DOGE', name: 'Doge', color: 'coin-doge' },
            { id: 'LINK', name: 'Chainlink', color: 'coin-link' },
            { id: 'AVAX', name: 'Avalanche', color: 'coin-avax' }
        ];
        
        // === BOT STATUS ===
        async function checkBotStatus() {
            try {
                const resp = await fetch('/api/bot-status');
                const data = await resp.json();
                
                botRunning = data.running;
                botData = data;
                
                updateControlCard();
            } catch (e) {
                console.error('Status check failed:', e);
                botRunning = false;
                updateControlCard();
            }
        }
        
        function updateControlCard() {
            const dot = document.getElementById('status-dot');
            const text = document.getElementById('status-text');
            const info = document.getElementById('status-info');
            const btn = document.getElementById('main-control-btn');
            const btnIcon = document.getElementById('btn-icon');
            const btnText = document.getElementById('btn-text');
            const settingsSection = document.getElementById('settings-section');
            
            if (botRunning) {
                dot.className = 'status-dot running';
                text.textContent = 'Бот работает';
                
                info.innerHTML = `
                    <span class="status-info-item">💰 $${(botData.balance || 0).toLocaleString()}</span>
                    <span class="status-info-item">📊 ${botData.active_trades || 0} сделок</span>
                    <span class="status-info-item">${botData.paper_trading ? '📝 Paper' : '💰 Live'}</span>
                `;
                
                btn.className = 'main-control-btn stop';
                btn.disabled = false;
                btnIcon.textContent = '🛑';
                btnText.textContent = 'ОСТАНОВИТЬ БОТА';
                
                // Hide settings when running
                settingsSection.style.display = 'none';
                
            } else {
                dot.className = 'status-dot stopped';
                text.textContent = 'Бот остановлен';
                
                info.innerHTML = `<span class="status-info-item">Настройте и запустите</span>`;
                
                btn.className = 'main-control-btn start';
                btn.disabled = false;
                btnIcon.textContent = '🚀';
                btnText.textContent = 'ЗАПУСТИТЬ БОТА';
                
                // Show settings
                settingsSection.style.display = 'block';
            }
        }
        
        async function handleMainAction() {
            const btn = document.getElementById('main-control-btn');
            const btnIcon = document.getElementById('btn-icon');
            const btnText = document.getElementById('btn-text');
            
            btn.className = 'main-control-btn loading';
            btn.disabled = true;
            btnIcon.textContent = '⏳';
            btnText.textContent = botRunning ? 'Останавливаю...' : 'Запускаю...';
            
            if (botRunning) {
                // STOP
                try {
                    await fetch('/api/stop', { method: 'POST' });
                    
                    btnIcon.textContent = '✅';
                    btnText.textContent = 'Готово!';
                    
                    setTimeout(() => tg.close(), 800);
                } catch (e) {
                    console.error('Stop error:', e);
                    alert('Ошибка остановки');
                    checkBotStatus();
                }
            } else {
                // START
                collectSettings();
                
                try {
                    await fetch('/api/start', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(settings)
                    });
                    
                    btnIcon.textContent = '✅';
                    btnText.textContent = 'Запущено!';
                    
                    setTimeout(() => tg.close(), 800);
                } catch (e) {
                    console.error('Start error:', e);
                    alert('Ошибка запуска');
                    checkBotStatus();
                }
            }
        }
        
        function collectSettings() {
            settings.bybit_api_key = document.getElementById('api-key').value;
            settings.bybit_api_secret = document.getElementById('api-secret').value;
        }
        
        // === SETTINGS ===
        async function loadSettings() {
            try {
                const resp = await fetch('/api/settings');
                if (resp.ok) {
                    const data = await resp.json();
                    settings = { ...settings, ...data };
                    applySettings();
                }
            } catch (e) {
                console.log('Using defaults');
            }
        }
        
        function applySettings() {
            document.getElementById('api-key').value = settings.bybit_api_key || '';
            document.getElementById('api-secret').value = settings.bybit_api_secret || '';
            updateApiStatus();
            
            setNetwork(settings.bybit_testnet ? 'testnet' : 'mainnet', false);
            renderCoins();
            
            document.getElementById('risk-slider').value = settings.risk_percent;
            document.getElementById('trades-slider').value = settings.max_trades;
            document.getElementById('confidence-slider').value = settings.ai_confidence;
            updateAllSliders();
            
            setAI(settings.ai_enabled, false);
            setMode(settings.paper_trading ? 'paper' : 'live', false);
        }
        
        function toggleCard(id) {
            document.getElementById('card-' + id).classList.toggle('open');
        }
        
        function togglePassword(inputId) {
            const input = document.getElementById(inputId);
            input.type = input.type === 'password' ? 'text' : 'password';
        }
        
        function updateApiStatus() {
            const key = document.getElementById('api-key').value;
            const secret = document.getElementById('api-secret').value;
            const status = document.getElementById('api-status');
            
            if (key && secret && key.length > 10 && secret.length > 10) {
                status.textContent = '✓ OK';
                status.className = 'status-badge success';
            } else {
                status.textContent = 'Не настроено';
                status.className = 'status-badge warning';
            }
        }
        
        function setNetwork(network) {
            const testnet = document.getElementById('btn-testnet');
            const mainnet = document.getElementById('btn-mainnet');
            
            if (network === 'testnet') {
                testnet.classList.add('active');
                mainnet.classList.remove('active');
                settings.bybit_testnet = true;
            } else {
                mainnet.classList.add('active');
                testnet.classList.remove('active');
                settings.bybit_testnet = false;
            }
        }
        
        function renderCoins() {
            const grid = document.getElementById('coins-grid');
            let count = 0;
            
            grid.innerHTML = coinsData.map(coin => {
                const active = settings.coins[coin.id];
                if (active) count++;
                return `
                    <button class="coin-btn ${active ? 'active' : ''}" onclick="toggleCoin('${coin.id}')">
                        <div class="coin-icon ${coin.color}">${coin.id.charAt(0)}</div>
                        <div class="coin-name">${coin.id}</div>
                        <div class="coin-status">${active ? '✓' : '—'}</div>
                    </button>
                `;
            }).join('');
            
            document.getElementById('coins-count').textContent = `Выбрано: ${count} из ${coinsData.length}`;
        }
        
        function toggleCoin(id) {
            settings.coins[id] = !settings.coins[id];
            renderCoins();
        }
        
        function updateAllSliders() {
            updateSlider('risk');
            updateSlider('trades');
            updateSlider('confidence');
        }
        
        function updateSlider(type) {
            const slider = document.getElementById(type + '-slider');
            const value = parseInt(slider.value);
            const min = parseInt(slider.min);
            const max = parseInt(slider.max);
            const percent = ((value - min) / (max - min)) * 100;
            
            document.getElementById(type + '-fill').style.width = percent + '%';
            document.getElementById(type + '-thumb').style.left = percent + '%';
            
            if (type === 'risk') {
                document.getElementById('risk-value').textContent = value + '%';
                settings.risk_percent = value;
            } else if (type === 'trades') {
                document.getElementById('trades-value').textContent = value;
                settings.max_trades = value;
            } else if (type === 'confidence') {
                document.getElementById('confidence-value').textContent = value + '%';
                settings.ai_confidence = value;
            }
        }
        
        function setAI(enabled) {
            const on = document.getElementById('btn-ai-on');
            const off = document.getElementById('btn-ai-off');
            
            if (enabled) {
                on.classList.add('active');
                off.classList.remove('active');
            } else {
                off.classList.add('active');
                on.classList.remove('active');
            }
            settings.ai_enabled = enabled;
        }
        
        function setMode(mode) {
            const paper = document.getElementById('btn-paper');
            const live = document.getElementById('btn-live');
            const warning = document.getElementById('live-warning');
            const subtitle = document.getElementById('mode-subtitle');
            
            if (mode === 'paper') {
                paper.classList.add('active');
                live.classList.remove('active');
                live.classList.remove('danger');
                warning.classList.add('hidden');
                subtitle.textContent = 'Paper Trading';
                settings.paper_trading = true;
            } else {
                live.classList.add('active');
                live.classList.add('danger');
                paper.classList.remove('active');
                warning.classList.remove('hidden');
                subtitle.textContent = '⚠️ Live Trading';
                settings.paper_trading = false;
            }
        }
        
        document.getElementById('api-key').addEventListener('input', updateApiStatus);
        document.getElementById('api-secret').addEventListener('input', updateApiStatus);
        
        // Init
        checkBotStatus();
        loadSettings();
        renderCoins();
        updateAllSliders();
        
        // Refresh status every 5 sec
        setInterval(checkBotStatus, 5000);
    </script>
</body>
</html>
```

---

## 📊 СВОДКА

| Файл | Строк | Описание |
|------|-------|----------|
| `telegram_bot.py` | ~1015 | Основной Telegram бот |
| `keyboards.py` | ~45 | Reply Keyboard |
| `webapp.html` | ~1210 | WebApp UI |

---

**Создано:** 2026-01-28 21:55 UTC
