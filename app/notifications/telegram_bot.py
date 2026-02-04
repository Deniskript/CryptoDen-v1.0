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
        """Установить команды бота v3.0 — только 2 команды"""
        commands = [
            BotCommand(command="start", description="🏠 Главное меню"),
            BotCommand(command="restart", description="🔄 Перезапуск бота")
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

🚀 CryptoDen — управление ботом
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
            """Главное меню v3.0"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Доступ запрещён")
                return
            
            await self._set_commands()
            
            text = """
🦊 *CryptoDen v3.0*

Добро пожаловать в умного крипто-бота!

🧠 *Adaptive Brain* — анализирует рынок
⚡ *Momentum* — ловит резкие движения
🆕 *Listing Hunter* — новые монеты

Используй кнопки ниже 👇
"""
            await message.answer(
                text.strip(),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_keyboard()
            )
        
        @self.dp.message(Command("restart"))
        async def cmd_restart(message: types.Message):
            """Перезапуск бота v3.0"""
            if not self._is_admin(message.from_user.id):
                await message.answer("⛔ Нет доступа")
                return
            
            await message.answer("🔄 *Перезапускаю бота...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                await self.monitor.stop()
                await asyncio.sleep(2)
                asyncio.create_task(self.monitor.start())
                await message.answer("✅ *Бот перезапущен!*", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Restart error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            text = """
❓ *Помощь CryptoDen Bot*

*🚀 CryptoDen* — открывает настройки:
• Запустить / Остановить бота
• API ключи Bybit
• Выбор монет
• Настройки рисков
• AI параметры
• Режимы модулей (Signal/Auto)

*Кнопки навигации:*
📊 Статус — текущее состояние бота
🐋 Рынок — Fear & Greed, Funding, OI
📰 Новости — рыночный контекст
👤 Кабинет — статистика и P&L

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
/whale — 🐋 Детальный анализ китов
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
                    # Собираем статистику ПЕРЕД остановкой
                    from app.modules.grid_bot import grid_bot
                    from app.modules.listing_hunter import listing_hunter
                    
                    stats = self.trade_manager.get_statistics()
                    
                    # Получаем включённые модули
                    enabled_modules = [
                        name for name, cfg in self.monitor.module_settings.items() 
                        if cfg.get('enabled')
                    ]
                    
                    # Форматируем красивое сообщение
                    text = smart_notifications.format_session_stop_message(
                        cycles=self.monitor.check_count,
                        active_trades=len(self.trade_manager.get_active_trades()),
                        max_trades=self.monitor.max_open_trades,
                        total_trades=stats.get('total_trades', 0),
                        win_rate=stats.get('win_rate', 0),
                        total_pnl=stats.get('total_pnl', 0),
                        grid_cycles=grid_bot.stats.get('total_trades', 0),
                        listings_found=listing_hunter.stats.get('listings_detected', 0),
                        modules_enabled=enabled_modules
                    )
                    
                    # Останавливаем
                    await smart_notifications.stop()
                    await self.monitor.stop()
                    
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
        
        @self.dp.message(F.text == "🐋 Рынок")
        async def btn_market(message: types.Message):
            """Обзор рынка"""
            if not self._is_admin(message.from_user.id):
                return
            
            loading = await message.answer("🐋 *Загружаю данные...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.ai.whale_ai import whale_ai
                
                if whale_ai.last_metrics:
                    m = whale_ai.last_metrics
                    
                    # Fear & Greed
                    if m.fear_greed_index < 25:
                        fg_emoji = "😱"
                        fg_text = "Экстремальный страх"
                    elif m.fear_greed_index < 45:
                        fg_emoji = "😨"
                        fg_text = "Страх"
                    elif m.fear_greed_index < 55:
                        fg_emoji = "😐"
                        fg_text = "Нейтрально"
                    elif m.fear_greed_index < 75:
                        fg_emoji = "😊"
                        fg_text = "Жадность"
                    else:
                        fg_emoji = "🤑"
                        fg_text = "Экстремальная жадность"
                    
                    # Funding
                    if m.funding_rate > 0.05:
                        fund_emoji = "🔴"
                        fund_text = "Много лонгов"
                    elif m.funding_rate < -0.05:
                        fund_emoji = "🟢"
                        fund_text = "Много шортов"
                    else:
                        fund_emoji = "⚪"
                        fund_text = "Нейтрально"
                    
                    text = f"""
🐋 *РЫНОК СЕЙЧАС*

{fg_emoji} *Fear & Greed:* {m.fear_greed_index} — {fg_text}

📊 *Long/Short:* {m.long_ratio:.0f}% / {m.short_ratio:.0f}%

{fund_emoji} *Funding:* {m.funding_rate:+.4f}%
_{fund_text}_

📈 *OI изменение:*
• 1h: {m.oi_change_1h:+.1f}%
• 24h: {m.oi_change_24h:+.1f}%

🔥 *Ликвидации (24h):*
• Long: ${m.liq_long/1e6:.1f}M
• Short: ${m.liq_short/1e6:.1f}M

💡 *Вывод:* {'Рынок перегрет, осторожно с лонгами' if m.fear_greed_index > 70 else 'Страх на рынке, хорошо для покупок' if m.fear_greed_index < 30 else 'Нейтральная ситуация'}
"""
                else:
                    text = "🐋 *Данные загружаются...*\n\nПопробуйте через минуту"
                
                await loading.edit_text(text.strip(), parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                await loading.edit_text(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
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
        
        @self.dp.message(F.text == "👤 Кабинет")
        async def btn_cabinet(message: types.Message):
            """Личный кабинет — статистика"""
            if not self._is_admin(message.from_user.id):
                return
            
            stats = self.trade_manager.get_statistics()
            
            # Расчёт win rate
            total = stats.get('total_trades', 0)
            wins = stats.get('winning_trades', 0)
            win_rate = (wins / total * 100) if total > 0 else 0
            
            # P&L
            total_pnl = stats.get('total_pnl', 0)
            today_pnl = stats.get('today_pnl', 0)
            
            pnl_emoji = "📈" if total_pnl >= 0 else "📉"
            today_emoji = "🟢" if today_pnl >= 0 else "🔴"
            
            text = f"""
👤 *КАБИНЕТ*

💎 *Подписка:* Premium
📅 *Активна до:* ∞

━━━━━━━━━━━━━━━

💰 *Баланс:* ${self.monitor.current_balance:,.2f}

{pnl_emoji} *Общий P&L:* ${total_pnl:+,.2f}
{today_emoji} *Сегодня:* ${today_pnl:+,.2f}

📊 *Статистика:*
• Всего сделок: {total}
• Выигрышных: {wins}
• Win Rate: {win_rate:.1f}%

📈 *Лучшая сделка:* ${stats.get('best_trade', 0):+.2f}
📉 *Худшая сделка:* ${stats.get('worst_trade', 0):+.2f}

━━━━━━━━━━━━━━━

🤖 *Бот:* {'🟢 Работает' if self.monitor.running else '🔴 Остановлен'}
🧠 *AI:* {'✅ Включён' if self.monitor.ai_enabled else '❌ Выключен'}
📝 *Режим:* {'Paper' if self.monitor.paper_trading else '💰 LIVE'}
"""
            
            await message.answer(text.strip(), parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(F.text == "❓ Помощь")
        async def btn_help(message: types.Message):
            if not self._is_admin(message.from_user.id):
                return
            
            text = """
❓ *ПОМОЩЬ — CryptoDen v3.0*

━━━━━━━━━━━━━━━━━━

📱 *КНОПКИ:*

🦊 *CryptoDen* — панель управления
• Включить/выключить бота
• Настроить модули
• API ключи и риски

📊 *Статистика* — результаты торговли
• Win Rate по дням/неделям
• P&L по источникам сигналов
• История сделок

🐋 *Рынок* — whale метрики
• Fear & Greed Index
• Long/Short Ratio
• Funding Rate

📰 *Новости* — крипто новости
• Sentiment анализ
• Важные события

🔍 *Анализ* — анализ монеты
• Выбери монету
• Получи рекомендацию AI

━━━━━━━━━━━━━━━━━━

⚙️ *КОМАНДЫ:*
/start — главное меню
/restart — перезапуск бота

━━━━━━━━━━━━━━━━━━

🧠 *МОДУЛИ:*
• Brain — умный анализ рынка
• Momentum — резкие движения
• Listing — новые монеты
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
            """🧠 Adaptive Brain v3.0 — статус единого AI мозга"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.brain import adaptive_brain
                
                text = f"""
🧠 *Adaptive Brain v3.0*

━━━━━━━━━━━━━━━━━━

📊 *Монеты:*
• Топ-20: {len(adaptive_brain.COINS_TOP20)}
• Динамические: {len(adaptive_brain.dynamic_coins)}
• Всего: {len(adaptive_brain.COINS_TOP20) + len(adaptive_brain.dynamic_coins)}

💾 *Кэш:* {len(adaptive_brain._cache)} записей

⚙️ *Настройки:*
• Модель: {adaptive_brain.model}
• Мин. уверенность: {adaptive_brain.MIN_CONFIDENCE}%
• Интервал анализа: {adaptive_brain.ANALYSIS_INTERVAL} сек

🎯 *Пороги:*
• Long ratio max: {adaptive_brain.THRESHOLDS['long_ratio_max']}%
• Short ratio max: {adaptive_brain.THRESHOLDS['short_ratio_max']}%
• Funding extreme: {adaptive_brain.THRESHOLDS['funding_extreme']}%
• Fear extreme: {adaptive_brain.THRESHOLDS['fear_extreme_low']}-{adaptive_brain.THRESHOLDS['fear_extreme_high']}
• RSI: {adaptive_brain.THRESHOLDS['rsi_oversold']}-{adaptive_brain.THRESHOLDS['rsi_overbought']}

━━━━━━━━━━━━━━━━━━

✅ *Статус:* Активен
⚡ *v3.0 — Один мозг вместо 4 агентов!*

*Команды:*
/analyze BTC — анализ монеты
/momentum — Momentum Detector
/brain_trades — активные сделки
"""
                await message.answer(text.strip(), parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Adaptive Brain status error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("stats"))
        async def cmd_stats(message: types.Message):
            """📊 Статистика торговли с Win Rate"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.core.statistics import trading_statistics
                
                # Получить форматированную статистику
                stats_text = trading_statistics.format_stats_message()
                
                await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Stats error: {e}")
                await message.answer(f"❌ *Ошибка получения статистики:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("analyze"))
        async def cmd_analyze(message: types.Message):
            """🧠 Adaptive Brain — анализ монеты"""
            if not self._is_admin(message.from_user.id):
                return
            
            # Получаем символ из аргументов
            args = message.text.split()
            if len(args) < 2:
                await message.answer("❌ *Использование:* /analyze BTC", parse_mode=ParseMode.MARKDOWN)
                return
            
            symbol = args[1].upper()
            
            loading = await message.answer(f"🧠 *Анализирую {symbol}...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.brain import adaptive_brain, TradeAction
                
                # Анализ через Adaptive Brain
                decision = await adaptive_brain.analyze(symbol)
                
                # Форматирование результата
                emoji = "🟢" if decision.action == TradeAction.LONG else "🔴" if decision.action == TradeAction.SHORT else "⚪"
                action_text = decision.action.value
                
                text = f"""
{emoji} *{symbol} — {action_text}*

━━━━━━━━━━━━━━━━━━

📊 *Режим рынка:* {decision.regime.value.upper()}
⚠️ *Уверенность:* {decision.confidence}%

━━━━━━━━━━━━━━━━━━

🧠 *Анализ:*
{decision.reasoning[:350]}{'...' if len(decision.reasoning) > 350 else ''}

━━━━━━━━━━━━━━━━━━

📈 *Ключевые факторы:*
"""
                for factor in decision.key_factors[:5]:
                    text += f"• {factor}\n"
                
                if decision.restrictions:
                    text += "\n⚠️ *Ограничения:*\n"
                    for r in decision.restrictions[:3]:
                        text += f"• {r}\n"
                
                if decision.action in [TradeAction.LONG, TradeAction.SHORT]:
                    text += f"""
━━━━━━━━━━━━━━━━━━

📍 *Вход:* ${decision.entry_price:,.2f}
🛑 *Стоп:* ${decision.stop_loss:,.2f}
🎯 *Цель:* ${decision.take_profit:,.2f}
"""
                
                await loading.edit_text(text.strip(), parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Adaptive Brain analyze error: {e}")
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
        
        @self.dp.message(Command("momentum"))
        async def cmd_momentum(message: types.Message):
            """⚡ Momentum Detector — детектор резких движений"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.brain import momentum_detector
                
                text = f"""
⚡ *Momentum Detector*

━━━━━━━━━━━━━━━━━━

🔍 *Отслеживание:* Каждые 5 секунд

📊 *Пороги срабатывания:*
• 1 мин: ±{momentum_detector.THRESHOLDS['price_change_1m']}%
• 5 мин: ±{momentum_detector.THRESHOLDS['price_change_5m']}%
• Объём: {momentum_detector.THRESHOLDS['volume_ratio']}x

🕐 *Кулдаун:* {momentum_detector.ALERT_COOLDOWN} сек

📈 *Статус:* {'🟢 Активен' if momentum_detector._running else '🔴 Остановлен'}

━━━━━━━━━━━━━━━━━━

💾 *История цен (последние 5):*
"""
                
                for symbol, history in list(momentum_detector._price_history.items())[:5]:
                    text += f"• {symbol}: {len(history)} точек\n"
                
                if not momentum_detector._price_history:
                    text += "  _Пока нет данных_\n"
                
                text += f"""
━━━━━━━━━━━━━━━━━━

⚡ *v3.0 — Мгновенная реакция на рынок!*
"""
                
                await message.answer(text.strip(), parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Momentum Detector error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("brain_trades"))
        async def cmd_brain_trades(message: types.Message):
            """🧠 Сделки Adaptive Brain"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.core.trade_tracker import trade_tracker
                
                active = trade_tracker.get_active_trades()
                
                if not active:
                    await message.answer("📊 *Нет активных сделок от Adaptive Brain*", parse_mode=ParseMode.MARKDOWN)
                    return
                
                text = "🧠 *АКТИВНЫЕ СДЕЛКИ ADAPTIVE BRAIN*\n\n"
                
                for trade in active:
                    emoji = "🟢" if trade.direction == "LONG" else "🔴"
                    pnl_emoji = "📈" if trade.pnl_percent >= 0 else "📉"
                    
                    text += f"""
{emoji} *{trade.symbol} {trade.direction}*
• Вход: ${trade.entry_price:,.2f}
• Текущая: ${trade.current_price:,.2f}
• SL: ${trade.stop_loss:,.2f}
• TP: ${trade.take_profit:,.2f}
{pnl_emoji} P&L: {trade.pnl_percent:+.2f}% (${trade.pnl_usd:+.2f})
• Уверенность: {trade.confidence}%

"""
                
                await message.answer(text.strip(), parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Brain trades error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("tracker"))
        async def cmd_tracker(message: types.Message):
            """🎯 Trade Tracker — статистика сигнальных сделок"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.core.trade_tracker import trade_tracker
                
                text = trade_tracker.get_status_text()
                
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Tracker error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("session"))
        async def cmd_session(message: types.Message):
            """📊 Session Tracker — статистика сеансов"""
            if not self._is_admin(message.from_user.id):
                return
            
            try:
                from app.core.session_tracker import session_tracker
                
                text = session_tracker.get_status_text()
                
                await message.answer(text, parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Session error: {e}")
                await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("market"))
        async def cmd_market(message: types.Message):
            """📊 Полная картина рынка от Adaptive Brain"""
            if not self._is_admin(message.from_user.id):
                return
            
            loading = await message.answer("🧠 *Анализирую рынок...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.brain import adaptive_brain
                from app.ai.whale_ai import whale_ai
                import asyncio
                
                # Получаем метрики
                m = whale_ai.last_metrics
                
                if not m:
                    await loading.edit_text("⏳ *Данные загружаются...*\n\nПопробуйте через минуту", parse_mode=ParseMode.MARKDOWN)
                    return
                
                # Анализируем топ-3 монеты
                top_coins = ["BTC", "ETH", "SOL"]
                decisions = []
                
                for symbol in top_coins:
                    try:
                        decision = await adaptive_brain.analyze(symbol)
                        decisions.append((symbol, decision))
                    except Exception as e:
                        logger.error(f"Market analyze error for {symbol}: {e}")
                
                # Формируем отчёт
                text = f"""
🧠 *ADAPTIVE BRAIN — РЫНОК*

━━━━━━━━━━━━━━━━━━

🐋 *Whale метрики:*
• Fear & Greed: {m.fear_greed_index} ({
    "Extreme Fear" if m.fear_greed_index < 25 else 
    "Fear" if m.fear_greed_index < 45 else 
    "Neutral" if m.fear_greed_index < 55 else 
    "Greed" if m.fear_greed_index < 75 else 
    "Extreme Greed"
})
• Long/Short: {m.long_ratio:.0f}% / {m.short_ratio:.0f}%
• Funding: {m.funding_rate:+.4f}%
• OI 24h: {m.oi_change_24h:+.1f}%

━━━━━━━━━━━━━━━━━━

📊 *Анализ топ-монет:*

"""
                
                for symbol, decision in decisions:
                    emoji = "🟢" if decision.action.value == "LONG" else "🔴" if decision.action.value == "SHORT" else "⚪"
                    text += f"""
{emoji} *{symbol}:* {decision.action.value}
• Режим: {decision.regime.value}
• Уверенность: {decision.confidence}%
• {decision.reasoning[:80]}...

"""
                
                text += f"""
━━━━━━━━━━━━━━━━━━

💡 *Рекомендация:*
"""
                
                # Общая рекомендация
                if m.fear_greed_index < 30:
                    text += "Страх на рынке — хорошо для покупок"
                elif m.fear_greed_index > 70:
                    text += "Жадность — осторожно с покупками"
                else:
                    text += "Нейтральный рынок — ждите сигналы"
                
                await loading.edit_text(text.strip(), parse_mode=ParseMode.MARKDOWN)
                
            except Exception as e:
                logger.error(f"Market data error: {e}")
                await loading.edit_text(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
        
        @self.dp.message(Command("ai"))
        async def cmd_ai_status(message: types.Message):
            """🧠 Статус AI системы v3.0"""
            if not self._is_admin(message.from_user.id):
                return
            
            loading = await message.answer("🔄 *Собираю данные...*", parse_mode=ParseMode.MARKDOWN)
            
            try:
                from app.ai.whale_ai import whale_ai
                from app.brain import adaptive_brain, momentum_detector
                
                # Whale AI
                whale_text = "🐋 *Whale AI (Разведка)*\n"
                if whale_ai.last_metrics:
                    m = whale_ai.last_metrics
                    whale_text += f"• Funding: {m.funding_rate:+.4f}%\n"
                    whale_text += f"• L/S: {m.long_ratio:.0f}% / {m.short_ratio:.0f}%\n"
                    whale_text += f"• F&G: {m.fear_greed_index}\n"
                else:
                    whale_text += "• _Нет данных_\n"
                
                # Adaptive Brain
                brain_text = "\n🧠 *Adaptive Brain (Главный мозг)*\n"
                brain_text += f"• Модель: {adaptive_brain.model}\n"
                brain_text += f"• Монет: {len(adaptive_brain.COINS_TOP20) + len(adaptive_brain.dynamic_coins)}\n"
                brain_text += f"• Кэш: {len(adaptive_brain._cache)} записей\n"
                brain_text += f"• Мин. уверенность: {adaptive_brain.MIN_CONFIDENCE}%\n"
                
                # Momentum Detector
                momentum_text = "\n⚡ *Momentum Detector (Резкие движения)*\n"
                momentum_text += f"• Статус: {'🟢 Активен' if momentum_detector._running else '🔴 Остановлен'}\n"
                momentum_text += f"• Порог 1м: ±{momentum_detector.THRESHOLDS['price_change_1m']}%\n"
                momentum_text += f"• Порог 5м: ±{momentum_detector.THRESHOLDS['price_change_5m']}%\n"
                
                # Monitor
                monitor_text = "\n📊 *Monitor (Управление)*\n"
                monitor_text += f"• Running: {'✅' if self.monitor.running else '❌'}\n"
                monitor_text += f"• Cycles: {self.monitor.check_count}\n"
                monitor_text += f"• Balance: ${self.monitor.current_balance:,.2f}\n"
                
                text = f"""🧠 *AI SYSTEM v3.0*

━━━━━━━━━━━━━━━━━━

{whale_text}
{brain_text}
{momentum_text}
{monitor_text}

━━━━━━━━━━━━━━━━━━

⚡ *v3.0 — Один мозг вместо 4 агентов!*

*Команды:*
/brain — статус Adaptive Brain
/analyze BTC — анализ монеты
/momentum — Momentum Detector
/brain_trades — активные сделки
"""
                
                await loading.edit_text(text.strip(), parse_mode=ParseMode.MARKDOWN)
                
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
            # Если ошибка Markdown — отправляем без форматирования
            if "parse entities" in str(e).lower() or "can't parse" in str(e).lower():
                try:
                    await self.bot.send_message(self.admin_id, text)
                    logger.warning(f"Sent without Markdown due to: {e}")
                except Exception as e2:
                    logger.error(f"Telegram error (retry): {e2}")
            else:
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
                        # Собираем статистику ПЕРЕД остановкой
                        from app.modules.grid_bot import grid_bot
                        from app.modules.listing_hunter import listing_hunter
                        
                        stats = self.trade_manager.get_statistics()
                        enabled_modules = [
                            name for name, cfg in self.monitor.module_settings.items() 
                            if cfg.get('enabled')
                        ]
                        
                        text = smart_notifications.format_session_stop_message(
                            cycles=self.monitor.check_count,
                            active_trades=len(self.trade_manager.get_active_trades()),
                            max_trades=self.monitor.max_open_trades,
                            total_trades=stats.get('total_trades', 0),
                            win_rate=stats.get('win_rate', 0),
                            total_pnl=stats.get('total_pnl', 0),
                            grid_cycles=grid_bot.stats.get('total_trades', 0),
                            listings_found=listing_hunter.stats.get('listings_detected', 0),
                            modules_enabled=enabled_modules
                        )
                        
                        await smart_notifications.stop()
                        await self.monitor.stop()
                        update_bot_status_file(running=False)
                        
                        await self.bot.send_message(self.admin_id, text, parse_mode=ParseMode.MARKDOWN)
                        
            except Exception as e:
                logger.error(f"Check request error: {e}")
            
            await asyncio.sleep(2)
    
    async def send_animated_startup(self, settings_data: dict):
        """
        🚀 Анимированный запуск бота
        """
        
        # Определяем режим
        has_api = bool(
            settings_data.get('bybit_api_key') and 
            settings_data.get('bybit_api_secret') and
            len(settings_data.get('bybit_api_key', '')) > 10
        )
        
        # ШАГ 1
        msg = await self.bot.send_message(
            self.admin_id,
            "⏳ *Запускаю CryptoDen...*",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(0.8)
        
        # ШАГ 2
        await msg.edit_text(
            "⏳ *Запускаю CryptoDen...*\n"
            "✅ Подключение к данным",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(0.8)
        
        # ШАГ 3
        await msg.edit_text(
            "⏳ *Запускаю CryptoDen...*\n"
            "✅ Подключение к данным\n"
            "✅ Загрузка индикаторов",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(0.8)
        
        # ШАГ 4
        await msg.edit_text(
            "⏳ *Запускаю CryptoDen...*\n"
            "✅ Подключение к данным\n"
            "✅ Загрузка индикаторов\n"
            "✅ Анализ рынка",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(1)
        
        # Получаем реальные данные
        market = await self._get_market_data_for_startup()
        
        # Финальное сообщение
        if has_api:
            final_text = self._format_startup_auto(settings_data, market)
        else:
            final_text = self._format_startup_signal(settings_data, market)
        
        await msg.edit_text(final_text, parse_mode=ParseMode.MARKDOWN)
    
    async def _get_market_data_for_startup(self) -> dict:
        """Получить реальные данные рынка"""
        data = {
            "btc_price": 0,
            "btc_rsi": 50,
            "fear_greed": 50,
            "fear_greed_text": "Нейтрально",
            "funding_rate": 0,
            "minutes_to_funding": 120,
        }
        
        try:
            # Цена BTC
            from app.trading.bybit.client import BybitClient
            async with BybitClient(testnet=False) as client:
                price = await client.get_price("BTC")
                if price:
                    data["btc_price"] = price
            
            # RSI
            from app.backtesting.data_loader import BybitDataLoader
            from app.strategies.indicators import TechnicalIndicators
            
            loader = BybitDataLoader()
            df = loader.load_from_cache("BTC", "5m")
            if df is not None and len(df) >= 20:
                ind = TechnicalIndicators()
                data["btc_rsi"] = ind.rsi(df['close'].tail(50), 14)
            
            # Fear & Greed + Funding
            from app.ai.whale_ai import whale_ai
            if whale_ai.last_metrics:
                data["fear_greed"] = whale_ai.last_metrics.fear_greed_index
                data["funding_rate"] = whale_ai.last_metrics.funding_rate
            else:
                try:
                    metrics = await whale_ai.get_market_metrics("BTC")
                    if metrics:
                        data["fear_greed"] = metrics.fear_greed_index
                        data["funding_rate"] = metrics.funding_rate
                except:
                    pass
            
            # Fear & Greed текст
            fg = data["fear_greed"]
            if fg < 25:
                data["fear_greed_text"] = "Экстремальный страх"
            elif fg < 45:
                data["fear_greed_text"] = "Страх"
            elif fg < 55:
                data["fear_greed_text"] = "Нейтрально"
            elif fg < 75:
                data["fear_greed_text"] = "Жадность"
            else:
                data["fear_greed_text"] = "Экстремальная жадность"
            
            # Время до Funding
            from datetime import datetime
            now = datetime.utcnow()
            for h in [0, 8, 16]:
                if now.hour < h:
                    data["minutes_to_funding"] = (h - now.hour) * 60 - now.minute
                    break
            else:
                data["minutes_to_funding"] = (24 - now.hour) * 60 - now.minute
                
        except Exception as e:
            logger.error(f"Startup market data error: {e}")
        
        return data
    
    def _format_startup_signal(self, settings_data: dict, market: dict) -> str:
        """Сообщение для SIGNAL режима (без API)"""
        
        # Fear & Greed
        fg = market.get("fear_greed", 50)
        if fg < 25:
            fg_emoji = "😱"
        elif fg < 45:
            fg_emoji = "😨"
        elif fg < 55:
            fg_emoji = "😐"
        elif fg < 75:
            fg_emoji = "😊"
        else:
            fg_emoji = "🤑"
        
        # RSI
        rsi = market.get("btc_rsi", 50)
        if rsi < 30:
            rsi_text = "перепродан ✅"
        elif rsi > 70:
            rsi_text = "перекуплен ⚠️"
        else:
            rsi_text = "нейтрально"
        
        # Funding
        mins = market.get("minutes_to_funding", 120)
        hours = mins // 60
        mins_left = mins % 60
        funding_time = f"{hours}ч {mins_left}мин" if hours > 0 else f"{mins_left} мин"
        
        # Модули
        modules = self.monitor.module_settings
        module_icons = {
            'director': '🎩', 'grid': '📊', 'funding': '💰',
            'arbitrage': '🔄', 'listing': '🆕', 'worker': '👷'
        }
        active = [module_icons.get(n, '📦') for n, cfg in modules.items() if cfg.get('enabled')]
        
        # Монеты
        active_coins = self.monitor.symbols
        coins_text = ", ".join(active_coins[:6])
        if len(active_coins) > 6:
            coins_text += f" +{len(active_coins)-6}"
        
        # BTC
        btc_price = market.get("btc_price", 0)
        btc_str = f"${btc_price:,.0f}" if btc_price > 0 else "загрузка..."
        
        from datetime import datetime
        return f"""
🚀 *CryptoDen ЗАПУЩЕН!*

📢 *Режим:* Сигналы
_Вы получаете рекомендации, торгуете сами_

━━━━━━━━━━━━━━━━━━

📊 *РЫНОК СЕЙЧАС:*

₿ *BTC:* {btc_str}
📉 *RSI:* {rsi:.0f} ({rsi_text})
{fg_emoji} *Fear & Greed:* {fg} ({market.get('fear_greed_text', 'Нейтрально')})
💰 *Funding:* {market.get('funding_rate', 0):+.3f}%
⏰ *До начисления:* {funding_time}

━━━━━━━━━━━━━━━━━━

🔔 *Модули:* {" ".join(active)}
🪙 *Монеты:* {coins_text}

━━━━━━━━━━━━━━━━━━

💡 *Что дальше:*
Анализирую рынок... Сигнал придёт 
с объяснением и рекомендацией!

⏰ {datetime.now().strftime('%H:%M:%S')}
""".strip()
    
    def _format_startup_auto(self, settings_data: dict, market: dict) -> str:
        """Сообщение для AUTO режима (с API)"""
        
        # Базовые данные из signal формата
        base = self._format_startup_signal(settings_data, market)
        
        # Добавляем баланс
        balance = self.monitor.current_balance
        trade_size = balance * self.monitor.balance_percent_per_trade
        pct = int(self.monitor.balance_percent_per_trade * 100)
        
        # Заменяем заголовок
        from datetime import datetime
        header = f"""
🚀 *CryptoDen ЗАПУЩЕН!*

🤖 *Режим:* Авто-торговля
_Бот торгует самостоятельно_

💰 *Баланс:* ${balance:,.2f}
📊 *Позиций:* 0/{self.monitor.max_open_trades}
🎯 *Сделка:* ${trade_size:.0f} ({pct}%)
"""
        
        # Заменяем первую часть
        parts = base.split("━━━━━━━━━━━━━━━━━━")
        if len(parts) >= 2:
            return header.strip() + "\n\n━━━━━━━━━━━━━━━━━━" + "━━━━━━━━━━━━━━━━━━".join(parts[1:])
        
        return base
    
    async def _apply_settings_and_start(self, settings_data: dict):
        """Применить настройки и запустить с анимацией"""
        try:
            self._apply_settings(settings_data)
            logger.info(f"📱 Settings applied: {len(self.monitor.symbols)} coins")
            
            # Запускаем smart notifications (без startup сообщения!)
            await smart_notifications.start()
            
            # АНИМИРОВАННЫЙ ЗАПУСК
            await self.send_animated_startup(settings_data)
            
            # Запускаем монитор
            asyncio.create_task(self.monitor.start())
            
            # Обновляем статус для WebApp
            update_bot_status_file(
                running=True,
                balance=self.monitor.current_balance,
                active_trades=len(self.trade_manager.get_active_trades()),
                paper_trading=self.monitor.paper_trading,
                ai_enabled=self.monitor.ai_enabled
            )
            
        except Exception as e:
            logger.error(f"Apply settings error: {e}")
            await self.send_message(f"❌ *Ошибка:* {e}")
    
    async def stop(self):
        if self.bot:
            await self.bot.session.close()


telegram_bot = TelegramBot()
