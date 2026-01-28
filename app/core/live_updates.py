"""
Live Updates — Живые обновления в чат
Бот постоянно рассказывает что делает
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum

from app.core.logger import logger


class UpdateType(Enum):
    """Типы обновлений"""
    MARKET_SCAN = "market_scan"          # Скан рынка (каждые 15 мин)
    DIRECTOR_THINKING = "director"        # Мысли директора
    GRID_LEVELS = "grid_levels"          # Уровни Grid
    FUNDING_INFO = "funding_info"        # Funding rates
    WHALE_ACTIVITY = "whale"             # Движение китов
    NEWS_IMPACT = "news"                 # Новость + влияние
    HOURLY_REPORT = "hourly"             # Часовой отчёт
    SIGNAL = "signal"                    # Сигнал (приоритет!)
    LISTING = "listing"                  # Листинг


@dataclass
class LiveUpdate:
    """Одно обновление для отправки"""
    type: UpdateType
    text: str
    priority: int = 5  # 1-10, где 10 = самый важный
    timestamp: datetime = field(default_factory=datetime.now)


class LiveUpdatesManager:
    """
    Менеджер живых обновлений
    
    Управляет очередью сообщений и частотой отправки
    """
    
    def __init__(self):
        self.enabled: bool = False
        self.queue: List[LiveUpdate] = []
        
        # Таймеры последних отправок
        self.last_sent: Dict[str, datetime] = {}
        
        # Минимальные интервалы между сообщениями одного типа
        self.intervals = {
            UpdateType.MARKET_SCAN: timedelta(minutes=15),
            UpdateType.DIRECTOR_THINKING: timedelta(minutes=10),
            UpdateType.GRID_LEVELS: timedelta(minutes=30),
            UpdateType.FUNDING_INFO: timedelta(minutes=30),
            UpdateType.WHALE_ACTIVITY: timedelta(minutes=5),
            UpdateType.NEWS_IMPACT: timedelta(minutes=2),
            UpdateType.HOURLY_REPORT: timedelta(hours=1),
            UpdateType.SIGNAL: timedelta(minutes=1),  # Сигналы почти без лимита
            UpdateType.LISTING: timedelta(minutes=5),
        }
        
        # Счётчики для статистики
        self.stats = {
            "cycles": 0,
            "signals_found": 0,
            "signals_skipped": 0,
            "news_processed": 0,
            "hour_start": datetime.now(),
        }
        
        # Последние данные рынка (для отчётов)
        self.market_data: Dict = {}
        
        logger.info("📢 LiveUpdatesManager initialized")
    
    def can_send(self, update_type: UpdateType) -> bool:
        """Можно ли отправить сообщение этого типа (проверка интервала)"""
        key = update_type.value
        
        if key not in self.last_sent:
            return True
        
        interval = self.intervals.get(update_type, timedelta(minutes=5))
        elapsed = datetime.now() - self.last_sent[key]
        
        return elapsed >= interval
    
    def mark_sent(self, update_type: UpdateType):
        """Отметить что сообщение отправлено"""
        self.last_sent[update_type.value] = datetime.now()
    
    async def send_update(self, update: LiveUpdate):
        """Отправить обновление в Telegram"""
        if not self.enabled:
            return
        
        # Проверяем интервал (кроме сигналов — они всегда важны)
        if update.type != UpdateType.SIGNAL and not self.can_send(update.type):
            return
        
        try:
            from app.notifications.telegram_bot import telegram_bot
            await telegram_bot.send_message(update.text)
            self.mark_sent(update.type)
            logger.debug(f"📢 Sent update: {update.type.value}")
        except Exception as e:
            logger.error(f"Send update error: {e}")
    
    # ==========================================
    # 📊 ГЕНЕРАТОРЫ ОБНОВЛЕНИЙ
    # ==========================================
    
    async def generate_market_scan(self, prices: Dict, indicators: Dict) -> Optional[LiveUpdate]:
        """Генерировать скан рынка (каждые 15 мин)"""
        if not self.can_send(UpdateType.MARKET_SCAN):
            return None
        
        # Топ-3 монеты
        lines = []
        for symbol in ["BTC", "ETH", "SOL"]:
            price = prices.get(symbol, 0)
            rsi = indicators.get(f"{symbol}_rsi", 50)
            
            # Определяем состояние
            if rsi < 30:
                state = "🟢 перепродан"
            elif rsi > 70:
                state = "🔴 перекуплен"
            else:
                state = "⚪ нейтрально"
            
            lines.append(f"{symbol} ${price:,.0f} • RSI {rsi:.0f} ({state})")
        
        text = f"""
👀 *СКАНИРУЮ РЫНОК*

{chr(10).join(lines)}

🎩 Director: Анализирую ситуацию...
"""
        return LiveUpdate(
            type=UpdateType.MARKET_SCAN,
            text=text.strip(),
            priority=3
        )
    
    async def generate_director_thinking(
        self, 
        prices: Dict, 
        rsi: float, 
        fear_greed: int,
        reason: str
    ) -> Optional[LiveUpdate]:
        """Директор объясняет почему НЕ входит"""
        if not self.can_send(UpdateType.DIRECTOR_THINKING):
            return None
        
        btc_price = prices.get("BTC", 0)
        
        text = f"""
🎩 *DIRECTOR*

Пока НЕ вхожу в сделку.

📊 Причина:
{reason}

Текущие показатели:
• BTC: ${btc_price:,.0f}
• RSI: {rsi:.0f}
• Fear & Greed: {fear_greed}

⏳ Жду лучшую точку входа...
"""
        return LiveUpdate(
            type=UpdateType.DIRECTOR_THINKING,
            text=text.strip(),
            priority=4
        )
    
    async def generate_grid_levels(
        self, 
        symbol: str, 
        price: float, 
        support: float, 
        resistance: float
    ) -> Optional[LiveUpdate]:
        """Уровни Grid Bot"""
        if not self.can_send(UpdateType.GRID_LEVELS):
            return None
        
        text = f"""
📊 *GRID BOT*

{symbol} ${price:,.0f}

Вижу уровни:
💚 Покупка: ${support:,.0f} (поддержка)
❤️ Продажа: ${resistance:,.0f} (сопротивление)

Сетка готова. Жду касания.
"""
        return LiveUpdate(
            type=UpdateType.GRID_LEVELS,
            text=text.strip(),
            priority=4
        )
    
    async def generate_funding_info(
        self, 
        rates: Dict[str, float], 
        minutes_to_funding: int
    ) -> Optional[LiveUpdate]:
        """Информация о Funding Rate"""
        if not self.can_send(UpdateType.FUNDING_INFO):
            return None
        
        lines = []
        alert_coin = None
        
        for symbol, rate in sorted(rates.items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
            rate_pct = rate * 100
            
            if abs(rate_pct) >= 0.05:
                emoji = "⚠️"
                if not alert_coin:
                    alert_coin = (symbol, rate_pct)
            else:
                emoji = "✅"
            
            lines.append(f"{symbol}: {rate_pct:+.3f}% {emoji}")
        
        alert_text = ""
        if alert_coin:
            symbol, rate = alert_coin
            direction = "SHORT" if rate > 0 else "LONG"
            alert_text = f"\n👀 Слежу за {symbol}. Возможен {direction}."
        
        text = f"""
💰 *FUNDING RATES*

До начисления: {minutes_to_funding} мин

{chr(10).join(lines)}
{alert_text}
"""
        return LiveUpdate(
            type=UpdateType.FUNDING_INFO,
            text=text.strip(),
            priority=4
        )
    
    async def generate_whale_activity(
        self, 
        activity_type: str, 
        amount: float, 
        symbol: str = "BTC"
    ) -> Optional[LiveUpdate]:
        """Активность китов"""
        if not self.can_send(UpdateType.WHALE_ACTIVITY):
            return None
        
        if activity_type == "exchange_inflow":
            emoji = "🔴"
            action = "переведено НА биржу"
            impact = "Возможна продажа. Осторожно с LONG."
        elif activity_type == "exchange_outflow":
            emoji = "🟢"
            action = "выведено С биржи"
            impact = "Накопление. Бычий сигнал."
        else:
            emoji = "🐋"
            action = "крупное движение"
            impact = "Наблюдаю..."
        
        text = f"""
🐋 *КИТЫ*

{emoji} {amount:,.0f} {symbol} {action}

💡 {impact}
"""
        return LiveUpdate(
            type=UpdateType.WHALE_ACTIVITY,
            text=text.strip(),
            priority=6
        )
    
    async def generate_news_impact(
        self, 
        title: str, 
        impact: str, 
        sentiment: str
    ) -> Optional[LiveUpdate]:
        """Новость с объяснением влияния"""
        if not self.can_send(UpdateType.NEWS_IMPACT):
            return None
        
        sentiment_emoji = {
            "bullish": "🟢",
            "bearish": "🔴",
            "neutral": "⚪"
        }.get(sentiment, "⚪")
        
        text = f"""
📰 *НОВОСТЬ*

"{title[:80]}{'...' if len(title) > 80 else ''}"

{sentiment_emoji} *Влияние:* {impact}
"""
        return LiveUpdate(
            type=UpdateType.NEWS_IMPACT,
            text=text.strip(),
            priority=5
        )
    
    async def generate_hourly_report(
        self, 
        prices: Dict, 
        price_changes: Dict
    ) -> Optional[LiveUpdate]:
        """Часовой отчёт"""
        if not self.can_send(UpdateType.HOURLY_REPORT):
            return None
        
        # Изменения цен
        changes = []
        for symbol in ["BTC", "ETH", "SOL"]:
            change = price_changes.get(symbol, 0)
            emoji = "📈" if change >= 0 else "📉"
            changes.append(f"{symbol}: {change:+.1f}%")
        
        text = f"""
⏰ *ОТЧЁТ ЗА ЧАС*

📊 Проанализировано: {self.stats['cycles']} циклов
🔍 Сигналов: {self.stats['signals_found']}
⏭ Пропущено: {self.stats['signals_skipped']}
📰 Новостей: {self.stats['news_processed']}

{' │ '.join(changes)}

Продолжаю мониторинг...
"""
        # Сбрасываем счётчики
        self.stats['cycles'] = 0
        self.stats['signals_found'] = 0
        self.stats['signals_skipped'] = 0
        self.stats['news_processed'] = 0
        self.stats['hour_start'] = datetime.now()
        
        return LiveUpdate(
            type=UpdateType.HOURLY_REPORT,
            text=text.strip(),
            priority=3
        )
    
    async def generate_signal(
        self,
        symbol: str,
        direction: str,
        entry: float,
        tp: float,
        sl: float,
        reason: str,
        win_rate: float = 0,
        module: str = "Director"
    ) -> LiveUpdate:
        """Сигнал на вход — ВСЕГДА отправляется"""
        
        dir_emoji = "🟢" if direction == "LONG" else "🔴"
        
        tp_pct = abs((tp - entry) / entry * 100)
        sl_pct = abs((sl - entry) / entry * 100)
        
        win_rate_text = f"🎯 Win Rate: {win_rate:.0f}%" if win_rate > 0 else ""
        
        text = f"""
🔔 *СИГНАЛ*

{dir_emoji} *{direction} {symbol}*

💰 Вход: ${entry:,.2f}
🎯 Цель: ${tp:,.2f} (+{tp_pct:.1f}%)
🛑 Стоп: ${sl:,.2f} (-{sl_pct:.1f}%)

📈 *Почему:* {reason}

{win_rate_text}

📢 Откройте позицию вручную.
"""
        self.stats['signals_found'] += 1
        
        return LiveUpdate(
            type=UpdateType.SIGNAL,
            text=text.strip(),
            priority=10
        )
    
    async def generate_listing(
        self,
        name: str,
        symbol: str,
        exchange: str,
        is_tradeable: bool,
        risk_score: int,
        potential: str
    ) -> Optional[LiveUpdate]:
        """Информация о листинге"""
        if not self.can_send(UpdateType.LISTING):
            return None
        
        # Оценка звёздами
        stars = "⭐" * min(risk_score, 5)
        
        if is_tradeable:
            status = "✅ Можно торговать!"
            action = "Рекомендую скальпинг: вход сейчас, TP +20%, SL -5%"
        else:
            status = "⏳ Ожидается листинг"
            action = "Слежу. Сообщу когда начнутся торги."
        
        text = f"""
🆕 *ЛИСТИНГ*

🔥 *{name}* ({symbol})
🏦 {exchange}

{status}

📊 Оценка: {stars} ({risk_score}/5)
💰 Потенциал: {potential}

💡 {action}
"""
        return LiveUpdate(
            type=UpdateType.LISTING,
            text=text.strip(),
            priority=7
        )
    
    async def generate_startup_message(self, coins_count: int, mode: str) -> LiveUpdate:
        """Сообщение при запуске"""
        text = f"""
🚀 *БОТ ЗАПУЩЕН*

📊 Монет: {coins_count}
📢 Режим: {mode}
🧠 AI: Активен

✅ Начинаю анализ рынка...

Буду сообщать о всех действиях.
"""
        return LiveUpdate(
            type=UpdateType.MARKET_SCAN,
            text=text.strip(),
            priority=10
        )
    
    async def generate_no_signal_reason(
        self,
        symbol: str,
        rsi: float,
        condition_needed: str,
        current_value: str
    ) -> Optional[LiveUpdate]:
        """Почему нет сигнала (объяснение)"""
        if not self.can_send(UpdateType.DIRECTOR_THINKING):
            return None
        
        text = f"""
🔍 *{symbol}*

Сигнала пока нет.

Нужно: {condition_needed}
Сейчас: {current_value}

⏳ Продолжаю следить...
"""
        return LiveUpdate(
            type=UpdateType.DIRECTOR_THINKING,
            text=text.strip(),
            priority=2
        )


# Синглтон
live_updates = LiveUpdatesManager()
