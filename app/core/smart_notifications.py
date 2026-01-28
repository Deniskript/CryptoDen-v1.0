"""
Smart Notifications — Умная система уведомлений
Координирует ВСЕ сообщения бота, знает контекст, не спамит
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from app.core.logger import logger
from app.intelligence.haiku_explainer import haiku_explainer, ExplainRequest


class MessagePriority(Enum):
    """Приоритеты сообщений"""
    CRITICAL = 10    # Сигнал, срочный листинг
    HIGH = 8         # Важная новость, whale
    MEDIUM = 5       # Статус модуля, funding
    LOW = 3          # Периодический отчёт
    INFO = 1         # Фоновая информация


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
    needs_ai: bool = False
    ai_type: str = None
    ai_data: Dict = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def __lt__(self, other):
        """Для сортировки по приоритету"""
        return self.priority.value > other.priority.value


class BotContext:
    """Контекст бота — что происходило"""
    
    def __init__(self):
        # Последние сигналы
        self.last_signal_time: Optional[datetime] = None
        self.last_signal_symbol: Optional[str] = None
        self.last_signal_direction: Optional[str] = None
        
        # Активные позиции
        self.active_positions: List[str] = []
        
        # История сообщений (последние 20)
        self.message_history: deque = deque(maxlen=20)
        
        # Когда модули последний раз отчитывались
        self.module_last_report: Dict[str, datetime] = {}
        
        # Флаги состояния
        self.is_startup = True  # Первые 10 минут после запуска
        self.startup_time: Optional[datetime] = None
    
    def record_signal(self, symbol: str, direction: str):
        """Записать что был сигнал"""
        self.last_signal_time = datetime.now()
        self.last_signal_symbol = symbol
        self.last_signal_direction = direction
    
    def had_recent_signal(self, minutes: int = 30) -> bool:
        """Был ли сигнал недавно"""
        if not self.last_signal_time:
            return False
        return datetime.now() - self.last_signal_time < timedelta(minutes=minutes)
    
    def record_message(self, module: ModuleType, text: str):
        """Записать отправленное сообщение"""
        self.message_history.append({
            "module": module,
            "text": text[:100],
            "time": datetime.now()
        })
        self.module_last_report[module.value] = datetime.now()
    
    def time_since_module_report(self, module: ModuleType) -> timedelta:
        """Сколько времени с последнего отчёта модуля"""
        last = self.module_last_report.get(module.value)
        if not last:
            return timedelta(hours=24)  # Давно не отчитывался
        return datetime.now() - last
    
    def is_startup_phase(self) -> bool:
        """Находимся ли в фазе запуска (первые 10 мин)"""
        if not self.startup_time:
            return False
        return datetime.now() - self.startup_time < timedelta(minutes=10)


class SmartNotifications:
    """
    Умный координатор уведомлений
    
    - Единая очередь сообщений
    - Знает контекст (не противоречит себе)
    - Распределяет по времени
    - Приоритеты
    - AI объяснения через Haiku
    """
    
    # Минимальный интервал между сообщениями
    MIN_INTERVAL = timedelta(seconds=90)  # 1.5 минуты
    
    # Интервалы для модулей (когда могут отчитываться)
    MODULE_INTERVALS = {
        ModuleType.DIRECTOR: timedelta(minutes=15),
        ModuleType.GRID: timedelta(minutes=20),
        ModuleType.FUNDING: timedelta(minutes=25),
        ModuleType.LISTING: timedelta(minutes=30),
        ModuleType.WHALE: timedelta(minutes=10),
        ModuleType.NEWS: timedelta(minutes=5),
        ModuleType.WORKER: timedelta(minutes=15),
    }
    
    # Порядок презентации при запуске
    STARTUP_ORDER = [
        ModuleType.DIRECTOR,
        ModuleType.GRID,
        ModuleType.FUNDING,
        ModuleType.LISTING,
        ModuleType.WHALE,
    ]
    
    def __init__(self):
        self.enabled = False
        self.context = BotContext()
        
        # Очередь сообщений
        self.queue: List[QueuedMessage] = []
        
        # Последнее отправленное сообщение
        self.last_sent_time: Optional[datetime] = None
        
        # Callback для отправки
        self._send_callback: Optional[Callable] = None
        
        # Задача обработки очереди
        self._queue_task: Optional[asyncio.Task] = None
        
        # Счётчик для startup
        self._startup_index = 0
        
        logger.info("📢 SmartNotifications initialized")
    
    def set_send_callback(self, callback: Callable):
        """Установить функцию отправки сообщений"""
        self._send_callback = callback
    
    async def start(self):
        """Запустить систему уведомлений"""
        self.enabled = True
        self.context.startup_time = datetime.now()
        self.context.is_startup = True
        self._startup_index = 0
        
        # Запускаем обработку очереди
        self._queue_task = asyncio.create_task(self._process_queue())
        
        # Отправляем приветствие
        await self._send_startup_message()
        
        logger.info("📢 SmartNotifications started")
    
    async def stop(self):
        """Остановить систему"""
        self.enabled = False
        self.context.is_startup = False
        
        if self._queue_task:
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass
        
        # Очищаем очередь
        self.queue.clear()
        
        logger.info("📢 SmartNotifications stopped")
    
    async def _send_startup_message(self):
        """Отправить сообщение о запуске"""
        text = """
🚀 *БОТ ЗАПУЩЕН*

- - - - -

✅ Все модули активированы
🔍 Начинаю анализ рынка

- - - - -

⏳ Через минуту каждый модуль
   расскажет о своей работе

🔔 Буду сообщать обо всём важном!
"""
        await self._send_now(text.strip(), ModuleType.SYSTEM)
    
    # ==========================================
    # 📤 МЕТОДЫ ДОБАВЛЕНИЯ В ОЧЕРЕДЬ
    # ==========================================
    
    async def queue_director_status(
        self,
        symbol: str,
        price: float,
        rsi: float,
        fear_greed: int,
        has_signal: bool = False
    ):
        """Добавить статус Директора в очередь"""
        
        # Если недавно был сигнал — не пишем "нет сигнала"
        if self.context.had_recent_signal(30) and not has_signal:
            return
        
        # Проверяем интервал
        if not self._can_module_report(ModuleType.DIRECTOR):
            return
        
        if has_signal:
            return  # Сигналы идут через queue_signal
        
        # Определяем состояние RSI
        if rsi < 30:
            rsi_status = "🟢 перепродан"
            rsi_hint = "Близко к зоне покупки!"
        elif rsi < 40:
            rsi_status = "🟡 низкий"
            rsi_hint = "Слежу за возможностью LONG"
        elif rsi > 70:
            rsi_status = "🔴 перекуплен"
            rsi_hint = "Возможен разворот вниз"
        elif rsi > 60:
            rsi_status = "🟡 высокий"
            rsi_hint = "Слежу за возможностью SHORT"
        else:
            rsi_status = "⚪ нейтрально"
            rsi_hint = "Жду более чёткий сигнал"
        
        # Определяем Fear & Greed
        if fear_greed < 25:
            fg_emoji = "😨"
            fg_text = "Страх"
        elif fear_greed < 45:
            fg_emoji = "😟"
            fg_text = "Осторожность"
        elif fear_greed > 75:
            fg_emoji = "🤑"
            fg_text = "Жадность"
        elif fear_greed > 55:
            fg_emoji = "😊"
            fg_text = "Оптимизм"
        else:
            fg_emoji = "😐"
            fg_text = "Нейтрально"
        
        text = f"""
🎩 *ДИРЕКТОР*

- - - - -

📊 *Анализ рынка:*

💰 {symbol}: *${price:,.0f}*
📈 RSI: *{rsi:.0f}* {rsi_status}
{fg_emoji} Настроение: *{fear_greed}* ({fg_text})

- - - - -

🧠 *Мой вывод:*

{rsi_hint}
"""
        
        msg = QueuedMessage(
            module=ModuleType.DIRECTOR,
            priority=MessagePriority.MEDIUM,
            text=text.strip(),
            needs_ai=True,
            ai_type="no_signal",
            ai_data={
                "symbol": symbol,
                "price": price,
                "rsi": rsi,
                "fear_greed": fear_greed,
                "trend": "нейтральный" if 40 < rsi < 60 else ("бычий" if rsi < 40 else "медвежий")
            }
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
        """Добавить СИГНАЛ в очередь (высший приоритет)"""
        
        # Записываем в контекст
        self.context.record_signal(symbol, direction)
        
        # Очищаем очередь от низкоприоритетных
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

💡 *Рекомендация:*
Откройте позицию вручную на бирже
"""
        
        msg = QueuedMessage(
            module=ModuleType.DIRECTOR,
            priority=MessagePriority.CRITICAL,
            text=text.strip(),
            needs_ai=True,
            ai_type="signal",
            ai_data={
                "symbol": symbol,
                "direction": direction,
                "entry": entry,
                "rsi": rsi,
                "strategy": strategy,
                "win_rate": win_rate
            }
        )
        
        self._add_to_queue(msg)
    
    async def queue_grid_status(
        self,
        symbol: str,
        price: float,
        support: float,
        resistance: float
    ):
        """Добавить статус Grid Bot"""
        
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
            needs_ai=False
        )
        
        self._add_to_queue(msg)
    
    async def queue_funding_status(
        self,
        rates: Dict[str, float],
        minutes_to_funding: int
    ):
        """Добавить статус Funding"""
        
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
        
        msg = QueuedMessage(
            module=ModuleType.FUNDING,
            priority=MessagePriority.MEDIUM if has_opportunity else MessagePriority.LOW,
            text=text.strip(),
            needs_ai=has_opportunity,
            ai_type="funding" if has_opportunity else None,
            ai_data={"rates": rates, "minutes": minutes_to_funding} if has_opportunity else None
        )
        
        self._add_to_queue(msg)
    
    async def queue_news(
        self,
        title: str,
        source: str,
        sentiment: float,
        importance: str
    ):
        """Добавить новость"""
        
        # Только важные новости
        if importance not in ["HIGH", "MEDIUM"]:
            return
        
        if not self._can_module_report(ModuleType.NEWS):
            return
        
        # Определяем настроение
        if sentiment > 0.2:
            sent_emoji = "🟢"
            sent_text = "Позитивная"
        elif sentiment < -0.2:
            sent_emoji = "🔴"
            sent_text = "Негативная"
        else:
            sent_emoji = "⚪"
            sent_text = "Нейтральная"
        
        # Важность на русском
        importance_ru = "🔥 ВАЖНАЯ" if importance == "HIGH" else "📌 Средняя"
        
        # Обрезаем длинный заголовок
        short_title = title[:80] + "..." if len(title) > 80 else title
        
        text = f"""
📰 *НОВОСТЬ*

- - - - -

📢 *"{short_title}"*

{sent_emoji} Тон: {sent_text}
{importance_ru}

- - - - -
"""
        
        msg = QueuedMessage(
            module=ModuleType.NEWS,
            priority=MessagePriority.HIGH if importance == "HIGH" else MessagePriority.MEDIUM,
            text=text.strip(),
            needs_ai=True,
            ai_type="news",
            ai_data={
                "title": title,
                "source": source,
                "sentiment": sentiment
            }
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
        """Добавить листинг"""
        
        priority = MessagePriority.CRITICAL if is_tradeable else MessagePriority.HIGH
        
        if is_tradeable:
            status = "⚡ *ТОРГИ НАЧАЛИСЬ!*"
            action = "🚀 Можно покупать прямо сейчас!"
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

📊 *Оценка:* ⭐⭐⭐⭐ (4/5)
💰 *Потенциал:* +50-150%
⚠️ *Риск:* Средний

- - - - -

💡 {action}
"""
        
        msg = QueuedMessage(
            module=ModuleType.LISTING,
            priority=priority,
            text=text.strip(),
            needs_ai=True,
            ai_type="listing",
            ai_data={
                "name": name,
                "symbol": symbol,
                "exchange": exchange,
                "type": listing_type
            }
        )
        
        self._add_to_queue(msg)
    
    async def queue_whale(
        self,
        coin: str,
        amount: float,
        direction: str,  # "to_exchange", "from_exchange"
        whale_type: str
    ):
        """Добавить движение китов"""
        
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
        
        msg = QueuedMessage(
            module=ModuleType.WHALE,
            priority=MessagePriority.HIGH,
            text=text.strip(),
            needs_ai=True,
            ai_type="whale",
            ai_data={
                "coin": coin,
                "amount": amount,
                "type": whale_type,
                "direction": direction
            }
        )
        
        self._add_to_queue(msg)
    
    async def queue_startup_module(self, module: ModuleType, text: str):
        """Добавить сообщение модуля при запуске"""
        msg = QueuedMessage(
            module=module,
            priority=MessagePriority.INFO,
            text=text.strip(),
            needs_ai=False
        )
        self._add_to_queue(msg)
    
    # ==========================================
    # 🔧 ВНУТРЕННИЕ МЕТОДЫ
    # ==========================================
    
    def _add_to_queue(self, msg: QueuedMessage):
        """Добавить сообщение в очередь"""
        self.queue.append(msg)
        # Сортируем по приоритету
        self.queue.sort()
    
    def _can_module_report(self, module: ModuleType) -> bool:
        """Может ли модуль сейчас отчитаться"""
        # При запуске — всем можно
        if self.context.is_startup_phase():
            return True
        
        interval = self.MODULE_INTERVALS.get(module, timedelta(minutes=10))
        time_since = self.context.time_since_module_report(module)
        
        return time_since >= interval
    
    def _clear_low_priority(self):
        """Очистить низкоприоритетные сообщения (когда пришёл сигнал)"""
        self.queue = [
            msg for msg in self.queue 
            if msg.priority.value >= MessagePriority.HIGH.value
        ]
    
    async def _process_queue(self):
        """Обработка очереди сообщений"""
        while self.enabled:
            try:
                await self._process_one()
                await asyncio.sleep(5)  # Проверяем каждые 5 сек
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
        
        # Добавляем AI объяснение если нужно
        final_text = msg.text
        
        if msg.needs_ai and msg.ai_type and msg.ai_data:
            try:
                explanation = await haiku_explainer.explain(
                    ExplainRequest(type=msg.ai_type, data=msg.ai_data)
                )
                if explanation:
                    # Красиво форматируем AI ответ
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
    
    async def send_startup_sequence(self, data: Dict):
        """Отправить последовательность при запуске"""
        
        btc_price = data.get('btc_price', 0)
        btc_rsi = data.get('btc_rsi', 50)
        fear_greed = data.get('fear_greed', 50)
        coins_count = data.get('coins_count', 7)
        minutes_to_funding = data.get('minutes_to_funding', 120)
        
        # Часы и минуты для funding
        hours = minutes_to_funding // 60
        mins = minutes_to_funding % 60
        if hours > 0:
            funding_time = f"{hours}ч {mins}мин"
        else:
            funding_time = f"{mins} мин"
        
        # Director (через 1.5 мин после запуска)
        await asyncio.sleep(90)
        await self.queue_startup_module(
            ModuleType.DIRECTOR,
            f"""
🎩 *ДИРЕКТОР*

- - - - -

👋 Привет! Начинаю анализ.

💰 BTC: *${btc_price:,.0f}*
📈 RSI: *{btc_rsi:.0f}*
😐 Настроение: *{fear_greed}*

- - - - -

🔍 Ищу точки входа...
🔔 Сообщу когда найду!
"""
        )
        
        # Grid (ещё через 1.5 мин)
        await asyncio.sleep(90)
        await self.queue_startup_module(
            ModuleType.GRID,
            f"""
📊 *СЕТКА*

- - - - -

🔧 Строю сетку для *{coins_count}* монет

📉 Ищу уровни покупки
📈 Ищу уровни продажи

- - - - -

⏳ Жду касания уровней...
"""
        )
        
        # Funding (ещё через 1.5 мин)
        await asyncio.sleep(90)
        await self.queue_startup_module(
            ModuleType.FUNDING,
            f"""
💰 *ФАНДИНГ*

- - - - -

⏰ До начисления: *{funding_time}*

🔍 Проверяю ставки...
💡 Сообщу если будет возможность

- - - - -

✅ Мониторинг активен
"""
        )
        
        # Listing (ещё через 1.5 мин)
        await asyncio.sleep(90)
        await self.queue_startup_module(
            ModuleType.LISTING,
            """
🆕 *ЛИСТИНГИ*

- - - - -

🔍 Слежу за анонсами:

• Binance
• Bybit
• OKX

- - - - -

🔔 Сообщу о новых монетах!
"""
        )
        
        # Whale (ещё через 1.5 мин)
        await asyncio.sleep(90)
        await self.queue_startup_module(
            ModuleType.WHALE,
            """
🐋 *КИТЫ*

- - - - -

👀 Слежу за крупными игроками

💰 Отслеживаю переводы
📊 Анализирую движения

- - - - -

⚠️ Предупрежу о важном!
"""
        )
        
        # Конец startup фазы
        self.context.is_startup = False
        
        logger.info("✅ Startup sequence completed")


# Синглтон
smart_notifications = SmartNotifications()
