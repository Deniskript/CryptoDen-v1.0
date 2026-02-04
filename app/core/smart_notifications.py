"""
Smart Notifications — Умная система уведомлений
БЕЗ СПАМА + счётчики сигналов
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from app.core.logger import logger


class ModuleType(Enum):
    """Типы модулей для уведомлений"""
    DIRECTOR = "director"
    WORKER = "worker"
    GRID = "grid"
    FUNDING = "funding"
    ARBITRAGE = "arbitrage"
    LISTING = "listing"
    MASTER = "master"


@dataclass
class GridBuffer:
    """Буфер для группировки Grid сигналов"""
    signals: list = field(default_factory=list)
    last_flush: datetime = field(default_factory=datetime.now)
    
    def add(self, symbol: str, direction: str, price: float, profit: float = 0):
        self.signals.append({
            "symbol": symbol,
            "direction": direction,
            "price": price,
            "profit": profit,
            "time": datetime.now()
        })
    
    def should_flush(self) -> bool:
        if not self.signals:
            return False
        has_profit = any(s.get("profit", 0) > 0 for s in self.signals)
        if has_profit:
            return True
        return datetime.now() - self.last_flush > timedelta(minutes=5)
    
    def flush(self) -> list:
        signals = self.signals.copy()
        self.signals = []
        self.last_flush = datetime.now()
        return signals


class SmartNotifications:
    """
    Умная система уведомлений с счётчиками
    """
    
    def __init__(self):
        self.enabled = False
        self._send_callback: Optional[Callable] = None
        self.grid_buffer = GridBuffer()
        self._buffer_task: Optional[asyncio.Task] = None
        
        # Защита от дублей
        self._sent_listings: set = set()
        self._last_worker_signal: Dict[str, datetime] = {}
        
        # ✅ СЧЁТЧИКИ СИГНАЛОВ
        self.stats = {
            "worker_signals": 0,
            "director_signals": 0,
            "grid_summaries": 0,
            "listing_signals": 0,
            "session_start": None,
        }
        
        # ✅ ИСТОРИЯ СИГНАЛОВ (последние 50)
        self.signal_history: List[dict] = []
        
        logger.info("📢 SmartNotifications initialized")
    
    def set_send_callback(self, callback: Callable):
        self._send_callback = callback
    
    async def start(self):
        """Запустить систему"""
        self.enabled = True
        
        # ✅ Сбросить счётчики при старте
        self.stats = {
            "worker_signals": 0,
            "director_signals": 0,
            "grid_summaries": 0,
            "listing_signals": 0,
            "session_start": datetime.now(),
        }
        self.signal_history = []
        self._sent_listings = set()
        
        self._buffer_task = asyncio.create_task(self._process_grid_buffer())
        logger.info("📢 SmartNotifications started")
    
    async def stop(self):
        """Остановить систему"""
        self.enabled = False
        if self._buffer_task:
            self._buffer_task.cancel()
        logger.info("📢 SmartNotifications stopped")
    
    # ==========================================
    # 📨 УНИВЕРСАЛЬНЫЕ МЕТОДЫ ОТПРАВКИ
    # ==========================================
    
    async def queue_message(
        self,
        text: str = None,
        module = None,
        priority: int = 2,
        need_ai: bool = False,
        **kwargs
    ):
        """
        Универсальный метод отправки сообщений
        Совместим со старым API (module, text, priority, need_ai)
        """
        # Если text передан как kwargs
        if text is None and 'text' in kwargs:
            text = kwargs['text']
        
        if not text:
            return
        
        # Просто отправляем текст
        await self._send(text)
        
        # Увеличиваем счётчик director если это от director
        if module and hasattr(module, 'value') and 'director' in str(module.value).lower():
            self.stats["director_signals"] += 1
        
        logger.debug(f"📨 queue_message sent (priority={priority})")
    
    async def queue_director_status(self, text: str):
        """Отправить статус Director (алиас)"""
        await self._send(text)
    
    async def send_simple_signal(
        self,
        title: str,
        symbol: str,
        direction: str,
        entry: float,
        confidence: int,
        reason: str = ""
    ):
        """Отправить простой сигнал (для DirectorBrain)"""
        dir_emoji = "🟢" if direction == "LONG" else "🔴"
        dir_text = "ПОКУПАЙ" if direction == "LONG" else "ПРОДАВАЙ"
        
        text = f"""
🧠 *{title}*

{dir_emoji} *{dir_text} {symbol}*

💰 Цена: *${entry:,.2f}*
🎯 Уверенность: *{confidence}%*

{f"💡 {reason}" if reason else ""}

⏰ {datetime.now().strftime('%H:%M')}
"""
        
        await self._send(text.strip())
        self.stats["director_signals"] += 1
        self._add_to_history("director", symbol, direction, entry)
        logger.info(f"📤 Simple signal sent: {direction} {symbol}")
    
    def get_session_stats(self) -> dict:
        """Получить статистику сессии"""
        uptime = ""
        if self.stats["session_start"]:
            delta = datetime.now() - self.stats["session_start"]
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            if delta.days > 0:
                uptime = f"{delta.days}д {hours}ч {minutes}мин"
            elif hours > 0:
                uptime = f"{hours}ч {minutes}мин"
            else:
                uptime = f"{minutes}мин"
        
        return {
            "uptime": uptime,
            "worker_signals": self.stats["worker_signals"],
            "director_signals": self.stats["director_signals"],
            "grid_summaries": self.stats["grid_summaries"],
            "listing_signals": self.stats["listing_signals"],
            "total_signals": (
                self.stats["worker_signals"] + 
                self.stats["director_signals"] + 
                self.stats["listing_signals"]
            ),
            "signal_history": self.signal_history[-10:],  # Последние 10
        }
    
    def _add_to_history(self, signal_type: str, symbol: str, direction: str, price: float):
        """Добавить сигнал в историю"""
        self.signal_history.append({
            "type": signal_type,
            "symbol": symbol,
            "direction": direction,
            "price": price,
            "time": datetime.now(),
        })
        # Ограничиваем размер
        if len(self.signal_history) > 50:
            self.signal_history = self.signal_history[-50:]
    
    async def _send(self, text: str):
        """Отправить сообщение"""
        if not self._send_callback or not self.enabled:
            return
        try:
            await self._send_callback(text)
        except Exception as e:
            logger.error(f"Send error: {e}")
    
    async def _process_grid_buffer(self):
        """Обработка буфера Grid"""
        while self.enabled:
            try:
                if self.grid_buffer.should_flush():
                    signals = self.grid_buffer.flush()
                    if signals:
                        text = self._format_grid_summary(signals)
                        await self._send(text)
                        self.stats["grid_summaries"] += 1
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Grid buffer error: {e}")
                await asyncio.sleep(30)
    
    # ==========================================
    # 🔔 WORKER SIGNAL
    # ==========================================
    
    async def send_worker_signal(
        self,
        symbol: str,
        direction: str,
        entry: float,
        tp: float,
        sl: float,
        rsi: float,
        ema_trend: str,
        macd_signal: str,
        win_rate: float,
        ai_analysis: str = None
    ):
        """Worker сигнал с полным объяснением"""
        
        # Защита от дублей
        last = self._last_worker_signal.get(symbol)
        if last and datetime.now() - last < timedelta(minutes=5):
            return
        self._last_worker_signal[symbol] = datetime.now()
        
        # ✅ Увеличиваем счётчик
        self.stats["worker_signals"] += 1
        self._add_to_history("worker", symbol, direction, entry)
        
        dir_emoji = "🟢" if direction == "LONG" else "🔴"
        dir_text = "ПОКУПАЙ" if direction == "LONG" else "ПРОДАВАЙ"
        
        tp_pct = abs((tp - entry) / entry * 100)
        sl_pct = abs((sl - entry) / entry * 100)
        
        if rsi < 30:
            rsi_status = "перепродан ✅"
        elif rsi > 70:
            rsi_status = "перекуплен ✅"
        else:
            rsi_status = "нейтрально"
        
        text = f"""
🔔 *СИГНАЛ*

{dir_emoji} *{dir_text} {symbol}*

- - - - - - - -

📊 *Как заходить:*

💰 Вход: *${entry:,.2f}*
🎯 Цель: *${tp:,.2f}* (+{tp_pct:.1f}%)
🛑 Стоп: *${sl:,.2f}* (-{sl_pct:.1f}%)

- - - - - - - -

📈 *Почему сейчас:*

• RSI: *{rsi:.0f}* — {rsi_status}
• Тренд: *{ema_trend}* ✅
• MACD: *{macd_signal}* ✅

- - - - - - - -

🧠 *Анализ:*

"""
        if ai_analysis:
            lines = ai_analysis.split(". ")
            for line in lines[:4]:
                if line.strip():
                    text += f"• *{line.strip()}*\n"
        else:
            text += f"• *RSI в зоне {'перепроданности' if rsi < 30 else 'перекупленности' if rsi > 70 else 'нейтральной'}*\n"
            text += f"• *Тренд подтверждён EMA*\n"
            text += f"• *MACD даёт сигнал*\n"
        
        text += f"""
- - - - - - - -

🎯 Win Rate: *{win_rate:.1f}%*
📏 Размер: 3-5% депозита

⏰ {datetime.now().strftime('%H:%M')}
"""
        
        await self._send(text.strip())
        logger.info(f"📤 Worker signal #{self.stats['worker_signals']}: {direction} {symbol}")
    
    # ==========================================
    # 🎩 DIRECTOR SIGNAL
    # ==========================================
    
    async def send_director_signal(
        self,
        symbol: str,
        direction: str,
        entry: float,
        tp: float,
        sl: float,
        size_percent: int,
        fear_greed: int,
        long_ratio: float,
        liquidations: float,
        news_summary: str,
        risk_score: int,
        scenario: str,
        ai_analysis: str = None
    ):
        """Director TAKE_CONTROL сигнал"""
        
        # ✅ Увеличиваем счётчик
        self.stats["director_signals"] += 1
        self._add_to_history("director", symbol, direction, entry)
        
        dir_emoji = "🟢" if direction == "LONG" else "🔴"
        dir_text = "ПОКУПАЙ" if direction == "LONG" else "ПРОДАВАЙ"
        
        tp_pct = abs((tp - entry) / entry * 100)
        sl_pct = abs((sl - entry) / entry * 100)
        
        if fear_greed < 25:
            fg_emoji, fg_text = "😱", "экстремальный страх"
        elif fear_greed < 45:
            fg_emoji, fg_text = "😨", "страх"
        elif fear_greed < 55:
            fg_emoji, fg_text = "😐", "нейтрально"
        elif fear_greed < 75:
            fg_emoji, fg_text = "😊", "жадность"
        else:
            fg_emoji, fg_text = "🤑", "экстремальная жадность"
        
        if risk_score < 25:
            risk_text = "низкий"
        elif risk_score < 50:
            risk_text = "средний"
        else:
            risk_text = "высокий"
        
        text = f"""
🎩 *DIRECTOR*

{dir_emoji} *{dir_text} {symbol}*

- - - - - - - -

📊 *Как заходить:*

💰 Вход: *${entry:,.2f}*
🎯 Цель: *${tp:,.2f}* (+{tp_pct:.1f}%)
🛑 Стоп: *${sl:,.2f}* (-{sl_pct:.1f}%)
📏 Размер: *{size_percent}%* {'(агрессивно!)' if size_percent > 15 else ''}

- - - - - - - -

🐋 *Что видит Director:*

• {fg_emoji} Fear: *{fear_greed}* — {fg_text}
• 📊 Лонги: *{long_ratio:.0f}%*
• 🔥 Ликвидации: *${liquidations/1e6:.1f}M*
• 📰 *{news_summary[:50]}*

- - - - - - - -

🧠 *Почему сейчас:*

"""
        if ai_analysis:
            lines = ai_analysis.split(". ")
            for line in lines[:4]:
                if line.strip():
                    text += f"• *{line.strip()}*\n"
        else:
            text += f"• *Сценарий: {scenario}*\n"
            if fear_greed < 25:
                text += f"• *Толпа в панике — продаёт*\n"
            if long_ratio < 40:
                text += f"• *Мало лонгов = безопасно*\n"
            if liquidations > 50_000_000:
                text += f"• *Массовые ликвидации = разворот*\n"
        
        text += f"""
- - - - - - - -

⚠️ Risk: *{risk_score}/100* — {risk_text}

💡 Редкая возможность!

⏰ {datetime.now().strftime('%H:%M')}
"""
        
        await self._send(text.strip())
        logger.info(f"📤 Director signal #{self.stats['director_signals']}: {direction} {symbol}")
    
    # ==========================================
    # 📊 GRID
    # ==========================================
    
    def add_grid_signal(self, symbol: str, direction: str, price: float, profit: float = 0):
        """Добавить Grid сигнал в буфер"""
        self.grid_buffer.add(symbol, direction, price, profit)
    
    def _format_grid_summary(self, signals: list) -> str:
        """Форматировать сводку Grid"""
        
        by_symbol = {}
        total_profit = 0
        
        for s in signals:
            sym = s["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = {"buys": [], "sells": [], "profit": 0}
            
            if s["direction"] == "BUY":
                by_symbol[sym]["buys"].append(s["price"])
            else:
                by_symbol[sym]["sells"].append(s["price"])
            
            by_symbol[sym]["profit"] += s.get("profit", 0)
            total_profit += s.get("profit", 0)
        
        text = "📊 *СЕТКА*\n\n"
        
        if total_profit > 0:
            text += f"✅ *Профит: +${total_profit:.2f}*\n\n"
        
        text += "- - - - - - - -\n\n"
        text += "📈 *Активность:*\n\n"
        
        for sym, data in by_symbol.items():
            buys = len(data["buys"])
            sells = len(data["sells"])
            profit = data["profit"]
            
            if buys > 0:
                avg_buy = sum(data["buys"]) / buys
                text += f"🟢 *{sym}*: {buys} покупок @ ${avg_buy:,.4f}\n"
            if sells > 0:
                avg_sell = sum(data["sells"]) / sells
                text += f"🔴 *{sym}*: {sells} продаж @ ${avg_sell:,.4f}\n"
            if profit > 0:
                text += f"   💰 +${profit:.2f}\n"
        
        text += "\n- - - - - - - -\n\n"
        text += "🧠 *Как работает:*\n\n"
        text += "• *Сетка ловит колебания*\n"
        text += "• *Покупает внизу, продаёт вверху*\n"
        
        text += f"\n⏰ {datetime.now().strftime('%H:%M')}"
        
        return text.strip()
    
    # ==========================================
    # 🆕 LISTING
    # ==========================================
    
    async def send_listing_signal(
        self,
        symbol: str,
        name: str,
        exchange: str,
        listing_type: str,
        price: float = None,
        volume: float = None,
        ai_description: str = None,
        ai_analysis: str = None,
        url: str = None,
        listing_date: str = None
    ):
        """Сигнал о листинге (только SPOT!) — улучшенный формат"""
        
        key = f"{symbol}_{exchange}"
        if key in self._sent_listings:
            return
        self._sent_listings.add(key)
        
        # ✅ Увеличиваем счётчик
        self.stats["listing_signals"] += 1
        self._add_to_history("listing", symbol, "BUY", price or 0)
        
        # Определяем тип и эмодзи
        if listing_type == "listing_scalp":
            type_emoji = "⚡"
            type_text = "ТОРГИ НАЧАЛИСЬ"
            action_text = "Можно торговать прямо сейчас!"
        elif listing_type == "pre_listing":
            type_emoji = "📋"
            type_text = "СКОРО ЛИСТИНГ"
            action_text = "Готовьтесь к листингу"
        elif listing_type == "launchpad":
            type_emoji = "🚀"
            type_text = "LAUNCHPAD"
            action_text = "Возможность получить токены"
        else:
            type_emoji = "🆕"
            type_text = "НОВЫЙ ЛИСТИНГ"
            action_text = "Следите за монетой"
        
        # Форматируем цену
        if price and price > 0:
            if price >= 1:
                price_text = f"${price:,.2f}"
            elif price >= 0.01:
                price_text = f"${price:,.4f}"
            else:
                price_text = f"${price:,.8f}".rstrip('0').rstrip('.')
        else:
            price_text = "TBA"
        
        # Основной текст
        text = f"""🆕 *ЛИСТИНГ*

{type_emoji} *{type_text}*

━━━━━━━━━━━━━━━━━━

🔥 *{name}* ({symbol})
🏦 Биржа: *{exchange}*
💰 Цена: *{price_text}*
"""
        
        if listing_date:
            text += f"📅 Дата: *{listing_date}*\n"
        
        if volume and volume > 0:
            if volume >= 1_000_000:
                vol_text = f"${volume/1e6:.1f}M"
            else:
                vol_text = f"${volume:,.0f}"
            text += f"📊 Объём: *{vol_text}*\n"
        
        text += f"""
━━━━━━━━━━━━━━━━━━

📈 *{action_text}*

💡 *Рекомендации:*
• Вход: по рынку после листинга
• Цель: +30-50%
• Стоп: -15-20%
• Размер: 1-2% депо (риск!)

━━━━━━━━━━━━━━━━━━

⚠️ *DYOR!* Высокая волатильность!
Скальп 15-30 минут максимум.
"""
        
        if url:
            text += f"\n🔗 [Подробнее]({url})"
        
        text += f"\n\n⏰ {datetime.now().strftime('%H:%M')}"
        
        await self._send(text.strip())
        logger.info(f"📤 Listing signal #{self.stats['listing_signals']}: {symbol} on {exchange}")
    
    # ==========================================
    # 📊 СТАТУС СЕССИИ
    # ==========================================
    
    def format_session_stop_message(
        self,
        cycles: int,
        active_trades: int,
        max_trades: int,
        total_trades: int,
        win_rate: float,
        total_pnl: float,
        grid_cycles: int,
        listings_found: int,
        modules_enabled: list
    ) -> str:
        """Форматировать сообщение при остановке"""
        
        stats = self.get_session_stats()
        
        # Иконки модулей
        module_icons = {
            'director': '🎩', 'grid': '📊', 'funding': '💰',
            'listing': '🆕', 'worker': '👷', 'arbitrage': '🔄'
        }
        modules_text = " ".join([module_icons.get(m, '📦') for m in modules_enabled])
        
        # История сигналов
        history_text = ""
        for sig in stats["signal_history"][-5:]:
            emoji = "🟢" if sig["direction"] == "LONG" else "🔴"
            time_str = sig["time"].strftime("%H:%M")
            if sig["type"] == "worker":
                history_text += f"   • {emoji} {sig['symbol']} @ ${sig['price']:,.0f} ({time_str})\n"
            elif sig["type"] == "director":
                history_text += f"   • 🎩 {sig['symbol']} @ ${sig['price']:,.0f} ({time_str})\n"
            elif sig["type"] == "listing":
                history_text += f"   • 🆕 {sig['symbol']} ({time_str})\n"
        
        if not history_text:
            history_text = "   _Нет сигналов за сессию_\n"
        
        text = f"""
🔴 *БОТ ОСТАНОВЛЕН*

- - - - - - - -

⏱ *Сессия:*

• Работал: *{stats['uptime'] or 'N/A'}*
• Циклов: *{cycles}*

- - - - - - - -

🔔 *Сигналы:*

• 🔔 Worker: *{stats['worker_signals']}*
• 🎩 Director: *{stats['director_signals']}*
• 📊 Grid: *{grid_cycles} циклов*
• 🆕 Листинги: *{listings_found}*

- - - - - - - -

📋 *Последние сигналы:*

{history_text}
- - - - - - - -

📈 *Итоги:*

• Открыто: *{active_trades}/{max_trades}*
• Всего сделок: *{total_trades}*
• Win Rate: *{win_rate:.1f}%*
• P&L: *${total_pnl:+,.2f}*

- - - - - - - -

🔔 *Модули:* {modules_text}

💡 История сохранена.

⏰ {datetime.now().strftime('%H:%M')}
"""
        return text.strip()


# Синглтон
smart_notifications = SmartNotifications()
