"""
Smart Notifications — Умная система уведомлений
Координирует ВСЕ сообщения бота с AI анализом
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from app.core.logger import logger
from app.core.market_data_provider import market_data, MarketSnapshot


class MessagePriority(Enum):
    """Приоритеты сообщений"""
    CRITICAL = 10
    HIGH = 8
    MEDIUM = 5
    LOW = 3
    INFO = 1


class ModuleType(Enum):
    """Типы модулей"""
    SYSTEM = "system"
    DIRECTOR = "director"
    GRID = "grid"
    FUNDING = "funding"
    LISTING = "listing"
    WHALE = "whale"
    NEWS = "news"
    WORKER = "worker"


@dataclass
class QueuedMessage:
    """Сообщение в очереди"""
    module: ModuleType
    priority: MessagePriority
    text: str
    ai_prompt: str = None  # Промпт для AI
    ai_context: str = None  # Контекст для AI
    created_at: datetime = field(default_factory=datetime.now)
    
    def __lt__(self, other):
        return self.priority.value > other.priority.value


class BotContext:
    """Контекст бота"""
    
    def __init__(self):
        self.last_signal_time: Optional[datetime] = None
        self.last_signal_symbol: Optional[str] = None
        self.message_history: deque = deque(maxlen=20)
        self.module_last_report: Dict[str, datetime] = {}
        self.startup_time: Optional[datetime] = None
        self.is_startup = True
    
    def record_signal(self, symbol: str, direction: str):
        self.last_signal_time = datetime.now()
        self.last_signal_symbol = symbol
    
    def had_recent_signal(self, minutes: int = 30) -> bool:
        if not self.last_signal_time:
            return False
        return datetime.now() - self.last_signal_time < timedelta(minutes=minutes)
    
    def record_message(self, module: ModuleType, text: str):
        self.message_history.append({
            "module": module,
            "text": text[:100],
            "time": datetime.now()
        })
        self.module_last_report[module.value] = datetime.now()
    
    def time_since_module_report(self, module: ModuleType) -> timedelta:
        last = self.module_last_report.get(module.value)
        if not last:
            return timedelta(hours=24)
        return datetime.now() - last
    
    def is_startup_phase(self) -> bool:
        if not self.startup_time:
            return False
        return datetime.now() - self.startup_time < timedelta(minutes=10)


class SmartNotifications:
    """Умный координатор уведомлений с AI"""
    
    MIN_INTERVAL = timedelta(seconds=90)
    
    MODULE_INTERVALS = {
        ModuleType.DIRECTOR: timedelta(minutes=15),
        ModuleType.GRID: timedelta(minutes=20),
        ModuleType.FUNDING: timedelta(minutes=25),
        ModuleType.LISTING: timedelta(minutes=30),
        ModuleType.WHALE: timedelta(minutes=10),
        ModuleType.NEWS: timedelta(minutes=5),
    }
    
    def __init__(self):
        self.enabled = False
        self.context = BotContext()
        self.queue: List[QueuedMessage] = []
        self.last_sent_time: Optional[datetime] = None
        self._send_callback: Optional[Callable] = None
        self._queue_task: Optional[asyncio.Task] = None
        
        logger.info("📢 SmartNotifications initialized")
    
    def set_send_callback(self, callback: Callable):
        self._send_callback = callback
    
    async def start(self):
        """Запустить систему"""
        self.enabled = True
        self.context.startup_time = datetime.now()
        self.context.is_startup = True
        
        self._queue_task = asyncio.create_task(self._process_queue())
        
        await self._send_startup_message()
        
        logger.info("📢 SmartNotifications started")
    
    async def stop(self):
        """Остановить систему"""
        self.enabled = False
        
        if self._queue_task:
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
        
        self.queue.clear()
        logger.info("📢 SmartNotifications stopped")
    
    async def _send_startup_message(self):
        """Приветственное сообщение"""
        text = """
🚀 *БОТ ЗАПУЩЕН*

- - - - -

✅ Все модули активированы
🔍 Загружаю данные рынка...

- - - - -

⏳ Через минуту начну
   отчёт о состоянии рынка

🔔 Буду сообщать обо всём важном!
"""
        await self._send_now(text.strip(), ModuleType.SYSTEM)
    
    # ==========================================
    # 🧠 AI АНАЛИЗ
    # ==========================================
    
    async def _get_ai_analysis(self, prompt: str, context: str) -> Optional[str]:
        """Получить AI анализ через Haiku"""
        try:
            from app.intelligence.haiku_explainer import haiku_explainer, ExplainRequest
            
            # Формируем запрос
            result = await haiku_explainer.explain(
                ExplainRequest(
                    type="market_status",
                    data={"prompt": prompt, "context": context}
                )
            )
            
            return result
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return None
    
    # ==========================================
    # 📤 МЕТОДЫ ДОБАВЛЕНИЯ В ОЧЕРЕДЬ
    # ==========================================
    
    async def queue_director_status(
        self,
        snapshot: MarketSnapshot = None,
        has_signal: bool = False
    ):
        """Статус Директора с реальными данными"""
        
        if self.context.had_recent_signal(30) and not has_signal:
            return
        
        if not self._can_module_report(ModuleType.DIRECTOR):
            return
        
        # Получаем реальные данные если не переданы
        if not snapshot:
            snapshot = await market_data.get_snapshot()
        
        # RSI статус
        rsi_emoji, rsi_text = market_data.get_rsi_status(snapshot.btc_rsi)
        fg_emoji = market_data.get_fg_emoji(snapshot.fear_greed)
        
        # Определяем что видит директор
        if snapshot.btc_rsi < 35:
            outlook = "📈 Близко к зоне покупки!"
            outlook_detail = "RSI в зоне перепроданности"
        elif snapshot.btc_rsi > 65:
            outlook = "📉 Близко к зоне продажи!"
            outlook_detail = "RSI в зоне перекупленности"
        else:
            outlook = "⏳ Жду лучшую точку входа"
            outlook_detail = "RSI в нейтральной зоне"
        
        text = f"""
🎩 *ДИРЕКТОР*

- - - - -

📊 *Состояние рынка:*

💰 BTC: *${snapshot.btc_price:,.0f}*
📈 RSI: *{snapshot.btc_rsi:.0f}* {rsi_emoji} {rsi_text}
{fg_emoji} Настроение: *{snapshot.fear_greed}* ({snapshot.fear_greed_text})

- - - - -

🔍 *Что я вижу:*

• {outlook_detail}
• Слежу за BTC, ETH, SOL, BNB...
• {outlook}
"""
        
        # AI контекст
        ai_context = f"""
BTC цена: ${snapshot.btc_price:,.0f}
RSI(14): {snapshot.btc_rsi:.0f}
Fear & Greed: {snapshot.fear_greed} ({snapshot.fear_greed_text})
Изменение 24ч: {snapshot.btc_change_24h:+.1f}%
"""
        
        ai_prompt = "Дай краткий анализ рынка (2-3 предложения). Что ожидать? Когда может быть сигнал?"
        
        msg = QueuedMessage(
            module=ModuleType.DIRECTOR,
            priority=MessagePriority.MEDIUM,
            text=text.strip(),
            ai_prompt=ai_prompt,
            ai_context=ai_context
        )
        
        self._add_to_queue(msg)
    
    async def queue_signal(
        self,
        symbol: str,
        direction: str,
        entry: float,
        tp: float,
        sl: float,
        rsi: float,
        strategy: str,
        win_rate: float
    ):
        """СИГНАЛ — высший приоритет"""
        
        self.context.record_signal(symbol, direction)
        self._clear_low_priority()
        
        if direction == "LONG":
            dir_emoji = "🟢"
            dir_text = "ПОКУПКА"
        else:
            dir_emoji = "🔴"
            dir_text = "ПРОДАЖА"
        
        tp_pct = abs((tp - entry) / entry * 100)
        sl_pct = abs((sl - entry) / entry * 100)
        
        text = f"""
🔔 *СИГНАЛ*

- - - - -

{dir_emoji} *{dir_text} {symbol}*

- - - - -

💰 *Вход:* ${entry:,.2f}
🎯 *Цель:* ${tp:,.2f} (+{tp_pct:.1f}%)
🛑 *Стоп:* ${sl:,.2f} (-{sl_pct:.1f}%)

- - - - -

📊 Стратегия: {strategy}
🎯 Успешность: {win_rate:.0f}%

- - - - -

⚠️ Откройте позицию вручную!
"""
        
        ai_context = f"""
Сигнал: {direction} {symbol}
Цена входа: ${entry:,.2f}
RSI: {rsi:.0f}
Стратегия: {strategy}
Win Rate: {win_rate:.0f}%
"""
        
        ai_prompt = "Объясни почему сейчас хороший момент для входа (2-3 предложения). Какие риски?"
        
        msg = QueuedMessage(
            module=ModuleType.DIRECTOR,
            priority=MessagePriority.CRITICAL,
            text=text.strip(),
            ai_prompt=ai_prompt,
            ai_context=ai_context
        )
        
        self._add_to_queue(msg)
    
    async def queue_news(
        self,
        title: str,
        source: str,
        sentiment: float,
        importance: str
    ):
        """Новость с AI анализом"""
        
        if importance not in ["HIGH", "MEDIUM"]:
            return
        
        if not self._can_module_report(ModuleType.NEWS):
            return
        
        # Определяем тон
        if sentiment > 0.2:
            sent_emoji = "🟢"
            sent_text = "Позитивная"
        elif sentiment < -0.2:
            sent_emoji = "🔴"
            sent_text = "Негативная"
        else:
            sent_emoji = "⚪"
            sent_text = "Нейтральная"
        
        importance_ru = "🔥 ВАЖНАЯ" if importance == "HIGH" else "📌 Средняя"
        
        # НЕ обрезаем заголовок сильно
        short_title = title[:100] + "..." if len(title) > 100 else title
        
        text = f"""
📰 *НОВОСТЬ*

- - - - -

📢 *"{short_title}"*

{sent_emoji} Тон: {sent_text}
{importance_ru}

- - - - -

🔍 *Источник:* {source}
"""
        
        ai_context = f"""
Заголовок: {title}
Источник: {source}
Sentiment Score: {sentiment}
"""
        
        ai_prompt = """
Объясни эту новость простым языком (3-4 предложения на русском):
1. Что произошло
2. Как это повлияет на Биткоин и крипторынок
3. Что делать трейдеру
"""
        
        msg = QueuedMessage(
            module=ModuleType.NEWS,
            priority=MessagePriority.HIGH if importance == "HIGH" else MessagePriority.MEDIUM,
            text=text.strip(),
            ai_prompt=ai_prompt,
            ai_context=ai_context
        )
        
        self._add_to_queue(msg)
    
    async def queue_listing(
        self,
        name: str,
        symbol: str,
        exchange: str,
        listing_type: str,
        is_tradeable: bool
    ):
        """Листинг с AI анализом"""
        
        priority = MessagePriority.CRITICAL if is_tradeable else MessagePriority.HIGH
        
        if is_tradeable:
            status = "⚡ *ТОРГИ НАЧАЛИСЬ!*"
            action = "🚀 Можно покупать!"
        else:
            status = "⏳ *Ожидается листинг*"
            action = "🔔 Сообщу когда начнутся торги"
        
        text = f"""
🆕 *ЛИСТИНГ*

- - - - -

🔥 *{name}* ({symbol})
🏦 Биржа: *{exchange}*

{status}

- - - - -

💡 {action}
"""
        
        ai_context = f"""
Листинг: {name} ({symbol})
Биржа: {exchange}
Тип: {listing_type}
Торги начались: {'Да' if is_tradeable else 'Нет'}
"""
        
        ai_prompt = """
Оцени этот листинг (3-4 предложения на русском):
1. Что это за проект (если знаешь)
2. Какой потенциал роста в первые часы
3. Какие риски и когда лучше входить
4. Общая оценка: стоит ли покупать
"""
        
        msg = QueuedMessage(
            module=ModuleType.LISTING,
            priority=priority,
            text=text.strip(),
            ai_prompt=ai_prompt,
            ai_context=ai_context
        )
        
        self._add_to_queue(msg)
    
    async def queue_grid_status(
        self,
        symbol: str,
        price: float,
        support: float,
        resistance: float
    ):
        """Статус Grid Bot"""
        
        if not self._can_module_report(ModuleType.GRID):
            return
        
        distance_to_support = ((price - support) / price) * 100
        distance_to_resistance = ((resistance - price) / price) * 100
        
        if distance_to_support < 0.3:
            hint = "🟢 Близко к покупке!"
        elif distance_to_resistance < 0.3:
            hint = "🔴 Близко к продаже!"
        else:
            hint = "⏳ Жду подхода к уровням"
        
        text = f"""
📊 *СЕТКА*

- - - - -

💰 {symbol}: *${price:,.0f}*

📉 Покупка: ${support:,.0f} (-{distance_to_support:.1f}%)
📈 Продажа: ${resistance:,.0f} (+{distance_to_resistance:.1f}%)

- - - - -

{hint}
"""
        
        msg = QueuedMessage(
            module=ModuleType.GRID,
            priority=MessagePriority.LOW,
            text=text.strip(),
            ai_prompt=None,
            ai_context=None
        )
        
        self._add_to_queue(msg)
    
    async def queue_funding_status(
        self,
        rates: Dict[str, float],
        minutes_to_funding: int
    ):
        """Статус Funding"""
        
        if not self._can_module_report(ModuleType.FUNDING):
            return
        
        # Топ-3 по абсолютному значению
        sorted_rates = sorted(rates.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        
        lines = []
        has_opportunity = False
        
        for symbol, rate in sorted_rates:
            pct = rate * 100
            
            if abs(pct) >= 0.05:
                emoji = "⚠️"
                has_opportunity = True
            else:
                emoji = "✅"
            
            lines.append(f"{emoji} {symbol}: *{pct:+.3f}%*")
        
        if has_opportunity:
            hint = "🔥 Есть возможность заработать!"
        else:
            hint = "✅ Всё спокойно, ставки в норме"
        
        # Часы и минуты
        hours = minutes_to_funding // 60
        mins = minutes_to_funding % 60
        
        if hours > 0:
            time_text = f"{hours}ч {mins}мин"
        else:
            time_text = f"{mins} мин"
        
        text = f"""
💰 *ФАНДИНГ*

- - - - -

⏰ До начисления: *{time_text}*

{chr(10).join(lines)}

- - - - -

{hint}
"""
        
        ai_prompt = "Объясни что означают эти ставки финансирования (2-3 предложения). Как заработать?"
        ai_context = f"Funding rates: {rates}, До начисления: {minutes_to_funding} мин"
        
        msg = QueuedMessage(
            module=ModuleType.FUNDING,
            priority=MessagePriority.MEDIUM if has_opportunity else MessagePriority.LOW,
            text=text.strip(),
            ai_prompt=ai_prompt if has_opportunity else None,
            ai_context=ai_context if has_opportunity else None
        )
        
        self._add_to_queue(msg)
    
    async def queue_whale(
        self,
        coin: str,
        amount: float,
        direction: str,
        whale_type: str
    ):
        """Движение китов"""
        
        if not self._can_module_report(ModuleType.WHALE):
            return
        
        if direction == "to_exchange":
            emoji = "🔴"
            action = "перевели НА биржу"
            hint = "⚠️ Возможна крупная продажа"
        else:
            emoji = "🟢"
            action = "вывели С биржи"
            hint = "💎 Накапливают, не продают"
        
        text = f"""
🐋 *КИТЫ*

- - - - -

{emoji} *{amount:,.0f} {coin}* {action}

- - - - -

{hint}
"""
        
        ai_context = f"""
Движение: {amount:,.0f} {coin}
Направление: {direction}
Тип: {whale_type}
"""
        
        ai_prompt = "Объясни что означает это движение китов (2-3 предложения). Как повлияет на цену?"
        
        msg = QueuedMessage(
            module=ModuleType.WHALE,
            priority=MessagePriority.HIGH,
            text=text.strip(),
            ai_prompt=ai_prompt,
            ai_context=ai_context
        )
        
        self._add_to_queue(msg)
    
    async def queue_startup_module(self, module: ModuleType, text: str):
        """Добавить сообщение модуля при запуске (с AI)"""
        msg = QueuedMessage(
            module=module,
            priority=MessagePriority.INFO,
            text=text.strip(),
            ai_prompt=None,
            ai_context=None
        )
        self._add_to_queue(msg)
    
    # ==========================================
    # 🔧 ВНУТРЕННИЕ МЕТОДЫ
    # ==========================================
    
    def _add_to_queue(self, msg: QueuedMessage):
        """Добавить сообщение в очередь"""
        self.queue.append(msg)
        self.queue.sort()
    
    def _can_module_report(self, module: ModuleType) -> bool:
        """Может ли модуль сейчас отчитаться"""
        if self.context.is_startup_phase():
            return True
        
        interval = self.MODULE_INTERVALS.get(module, timedelta(minutes=10))
        time_since = self.context.time_since_module_report(module)
        
        return time_since >= interval
    
    def _clear_low_priority(self):
        """Очистить низкоприоритетные сообщения"""
        self.queue = [
            msg for msg in self.queue 
            if msg.priority.value >= MessagePriority.HIGH.value
        ]
    
    async def _process_queue(self):
        """Обработка очереди сообщений"""
        while self.enabled:
            try:
                await self._process_one()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
                await asyncio.sleep(10)
    
    async def _process_one(self):
        """Обработать одно сообщение из очереди"""
        if not self.queue:
            return
        
        # Проверяем интервал
        if self.last_sent_time:
            elapsed = datetime.now() - self.last_sent_time
            
            next_msg = self.queue[0]
            if next_msg.priority == MessagePriority.CRITICAL:
                min_wait = timedelta(seconds=30)
            else:
                min_wait = self.MIN_INTERVAL
            
            if elapsed < min_wait:
                return
        
        # Берём сообщение
        msg = self.queue.pop(0)
        
        # Добавляем AI анализ если есть промпт
        final_text = msg.text
        
        if msg.ai_prompt and msg.ai_context:
            try:
                from app.intelligence.haiku_explainer import haiku_explainer, ExplainRequest
                
                # Специальный промпт для AI
                full_prompt = f"{msg.ai_prompt}\n\nКонтекст:\n{msg.ai_context}"
                
                explanation = await haiku_explainer.explain(
                    ExplainRequest(
                        type="market_status",
                        data={"prompt": full_prompt, "context": msg.ai_context}
                    )
                )
                
                if explanation:
                    final_text = msg.text + f"""

- - - - -

🧠 *Анализ:*
_{explanation}_
"""
            except Exception as e:
                logger.error(f"AI explain error: {e}")
        
        # Отправляем
        await self._send_now(final_text, msg.module)
    
    async def _send_now(self, text: str, module: ModuleType):
        """Отправить сообщение сейчас"""
        if not self._send_callback:
            logger.warning("No send callback set!")
            return
        
        try:
            await self._send_callback(text)
            self.last_sent_time = datetime.now()
            self.context.record_message(module, text)
            logger.debug(f"📤 Sent {module.value} message")
        except Exception as e:
            logger.error(f"Send error: {e}")
    
    async def send_startup_sequence(self, initial_data: Dict = None):
        """Отправить ОДНО сообщение при запуске с реальными данными"""
        
        # Получаем реальные данные рынка
        snapshot = await market_data.get_snapshot(force_refresh=True)
        
        # Часы и минуты для funding
        minutes_to_funding = initial_data.get('minutes_to_funding', 120) if initial_data else 120
        hours = minutes_to_funding // 60
        mins = minutes_to_funding % 60
        funding_time = f"{hours}ч {mins}мин" if hours > 0 else f"{mins} мин"
        
        coins_count = initial_data.get('coins_count', 7) if initial_data else 7
        coins_list = initial_data.get('coins', ['BTC', 'ETH', 'SOL']) if initial_data else ['BTC', 'ETH', 'SOL']
        
        # RSI статус
        rsi_emoji, rsi_text = market_data.get_rsi_status(snapshot.btc_rsi)
        fg_emoji = market_data.get_fg_emoji(snapshot.fear_greed)
        
        # Ждём 30 сек после запуска
        await asyncio.sleep(30)
        
        # ОДНО сообщение с полной информацией
        startup_text = f"""
🚀 *CryptoDen запущен*

📊 *Рынок сейчас:*
• BTC: *${snapshot.btc_price:,.0f}*
• RSI: {rsi_emoji} {snapshot.btc_rsi:.0f} ({rsi_text})
• Страх/Жадность: {fg_emoji} {snapshot.fear_greed}

🎯 *Активные модули:*

📊 *Сетка* — отслеживаю {coins_count} монет
   {', '.join(coins_list[:5])}

💰 *Фандинг* — до начисления {funding_time}

🆕 *Листинги* — слежу за Binance, Bybit, OKX

🐋 *Киты* — мониторю крупные движения

✅ *Все системы работают*
"""
        
        await self.queue_startup_module(ModuleType.DIRECTOR, startup_text)
        
        # Конец startup фазы
        self.context.is_startup = False
        
        logger.info("✅ Startup sequence completed (single message)")


# Синглтон
smart_notifications = SmartNotifications()
