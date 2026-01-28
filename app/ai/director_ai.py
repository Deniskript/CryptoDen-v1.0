"""
🎩 Director AI — Директор
Принимает стратегические решения на основе:
- Данных от Друга (Whale AI)
- Новостей (News AI)
- Состояния рынка

Управляет Работником (Tech AI)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum

from app.core.logger import logger
from app.core.config import settings


class TradingMode(Enum):
    """Режим торговли"""
    AUTO = "auto"           # Работник работает сам
    SUPERVISED = "supervised"  # Директор наблюдает внимательно
    MANUAL = "manual"       # Директор управляет вручную
    PAUSED = "paused"       # Торговля остановлена


class DirectorDecision(Enum):
    """Решения Директора"""
    CONTINUE = "continue"           # Работник продолжает
    CLOSE_ALL = "close_all"         # Закрыть все позиции
    CLOSE_LONGS = "close_longs"     # Закрыть только лонги
    CLOSE_SHORTS = "close_shorts"   # Закрыть только шорты
    PAUSE_NEW = "pause_new"         # Не открывать новые
    TAKE_CONTROL = "take_control"   # Директор берёт управление
    REDUCE_SIZE = "reduce_size"     # Уменьшить размер позиций
    AGGRESSIVE_LONG = "aggressive_long"   # Агрессивно лонг
    AGGRESSIVE_SHORT = "aggressive_short" # Агрессивно шорт


@dataclass
class DirectorCommand:
    """Команда от Директора"""
    decision: DirectorDecision
    mode: TradingMode
    reason: str
    details: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    valid_until: datetime = None
    
    def __post_init__(self):
        if self.valid_until is None:
            # Команда действует 30 минут по умолчанию
            self.valid_until = datetime.now() + timedelta(minutes=30)
    
    def is_valid(self) -> bool:
        return datetime.now() < self.valid_until


@dataclass 
class MarketSituation:
    """Полная картина рынка"""
    # От Друга (Whale AI)
    whale_alert_level: str = "calm"
    whale_message: str = ""
    funding_rate: float = 0
    long_ratio: float = 50
    short_ratio: float = 50
    fear_greed: int = 50
    oi_change_1h: float = 0
    oi_change_24h: float = 0
    
    # От News AI
    news_sentiment: str = "neutral"
    market_mode: str = "NORMAL"
    important_event_soon: bool = False
    event_name: str = ""
    
    # Текущие позиции
    open_positions: int = 0
    long_positions: int = 0
    short_positions: int = 0
    total_pnl: float = 0
    
    # Анализ
    risk_level: str = "normal"  # low, normal, elevated, high, extreme
    risk_score: int = 0
    recommended_action: str = ""
    
    timestamp: datetime = field(default_factory=datetime.now)


class DirectorAI:
    """
    🎩 Director AI — Главный
    
    Обязанности:
    1. Слушать Друга (Whale AI)
    2. Анализировать новости
    3. Принимать решения
    4. Управлять Работником
    5. В критические моменты — торговать сам
    """
    
    def __init__(self):
        self.current_mode = TradingMode.AUTO
        self.last_command: Optional[DirectorCommand] = None
        self.command_history: List[DirectorCommand] = []
        self.situation: Optional[MarketSituation] = None
        
        # Когда Директор берёт управление
        self.manual_control_until: Optional[datetime] = None
        
        # Флаги для торговли
        self.allow_new_longs = True
        self.allow_new_shorts = True
        self.size_multiplier = 1.0
        
        # Статистика
        self.decisions_made = 0
        self.interventions = 0
        self.successful_interventions = 0
        
        logger.info("🎩 Director AI инициализирован")
    
    async def consult_friend(self) -> Dict:
        """Консультация с Другом (Whale AI)"""
        
        try:
            from app.ai.whale_ai import whale_ai, check_whale_activity
            
            alert = await check_whale_activity("BTC")
            metrics = whale_ai.last_metrics
            
            return {
                "alert_level": alert.level.value,
                "message": alert.message,
                "recommendation": alert.recommendation,
                "funding_rate": metrics.funding_rate if metrics else 0,
                "long_ratio": metrics.long_ratio if metrics else 50,
                "short_ratio": metrics.short_ratio if metrics else 50,
                "fear_greed": metrics.fear_greed_index if metrics else 50,
                "oi_change_1h": metrics.oi_change_1h if metrics else 0,
                "oi_change_24h": metrics.oi_change_24h if metrics else 0,
            }
        
        except Exception as e:
            logger.error(f"Ошибка консультации с Другом: {e}")
            return {
                "alert_level": "calm", 
                "message": "Нет данных от Whale AI",
                "funding_rate": 0,
                "long_ratio": 50,
                "short_ratio": 50,
                "fear_greed": 50,
                "oi_change_1h": 0,
                "oi_change_24h": 0,
            }
    
    async def check_news(self) -> Dict:
        """Проверка новостей"""
        
        try:
            from app.intelligence.news_parser import news_parser
            
            context = await news_parser.get_market_context()
            
            mode = context.get("market_mode", "NORMAL")
            news = context.get("news", [])
            
            # Определяем sentiment
            sentiment = "neutral"
            important_event = False
            event_name = ""
            
            for item in news:
                s = item.get("sentiment", "").lower()
                if s in ["bearish", "negative"]:
                    sentiment = "bearish"
                elif s in ["bullish", "positive"] and sentiment != "bearish":
                    sentiment = "bullish"
                
                # Важные события
                imp = item.get("importance", "").upper()
                if imp in ["HIGH", "CRITICAL"]:
                    important_event = True
                    event_name = item.get("title", "")[:50]
            
            return {
                "mode": mode,
                "sentiment": sentiment,
                "important_event": important_event,
                "event_name": event_name,
                "news_count": len(news),
            }
        
        except Exception as e:
            logger.debug(f"Проверка новостей: {e}")
            return {
                "mode": "NORMAL", 
                "sentiment": "neutral", 
                "important_event": False,
                "event_name": "",
                "news_count": 0,
            }
    
    async def get_open_positions(self) -> Dict:
        """Получить открытые позиции из TradeManager"""
        
        try:
            from app.trading import trade_manager
            
            trades = trade_manager.get_active_trades()
            
            long_count = sum(1 for t in trades if t.direction == "LONG")
            short_count = sum(1 for t in trades if t.direction == "SHORT")
            total_pnl = sum(t.unrealized_pnl for t in trades)
            
            return {
                "count": len(trades),
                "long_count": long_count,
                "short_count": short_count,
                "total_pnl": total_pnl,
                "trades": trades
            }
        
        except Exception as e:
            logger.debug(f"Ошибка получения позиций: {e}")
            return {
                "count": 0, 
                "long_count": 0,
                "short_count": 0,
                "total_pnl": 0, 
                "trades": []
            }
    
    async def analyze_situation(self) -> MarketSituation:
        """Собрать полную картину рынка"""
        
        # Параллельно собираем данные
        whale_data, news_data, positions_data = await asyncio.gather(
            self.consult_friend(),
            self.check_news(),
            self.get_open_positions(),
            return_exceptions=True
        )
        
        # Обрабатываем ошибки
        if isinstance(whale_data, Exception):
            logger.error(f"Whale data error: {whale_data}")
            whale_data = {"alert_level": "calm", "funding_rate": 0, "long_ratio": 50, "fear_greed": 50}
        if isinstance(news_data, Exception):
            logger.error(f"News data error: {news_data}")
            news_data = {"mode": "NORMAL", "sentiment": "neutral"}
        if isinstance(positions_data, Exception):
            logger.error(f"Positions data error: {positions_data}")
            positions_data = {"count": 0, "total_pnl": 0}
        
        situation = MarketSituation(
            # Whale
            whale_alert_level=whale_data.get("alert_level", "calm"),
            whale_message=whale_data.get("message", ""),
            funding_rate=whale_data.get("funding_rate", 0),
            long_ratio=whale_data.get("long_ratio", 50),
            short_ratio=whale_data.get("short_ratio", 50),
            fear_greed=whale_data.get("fear_greed", 50),
            oi_change_1h=whale_data.get("oi_change_1h", 0),
            oi_change_24h=whale_data.get("oi_change_24h", 0),
            
            # News
            news_sentiment=news_data.get("sentiment", "neutral"),
            market_mode=news_data.get("mode", "NORMAL"),
            important_event_soon=news_data.get("important_event", False),
            event_name=news_data.get("event_name", ""),
            
            # Positions
            open_positions=positions_data.get("count", 0),
            long_positions=positions_data.get("long_count", 0),
            short_positions=positions_data.get("short_count", 0),
            total_pnl=positions_data.get("total_pnl", 0),
        )
        
        # Рассчитываем риск
        risk_score, risk_level = self._calculate_risk(situation)
        situation.risk_score = risk_score
        situation.risk_level = risk_level
        situation.recommended_action = self._get_recommendation(situation)
        
        self.situation = situation
        return situation
    
    def _calculate_risk(self, s: MarketSituation) -> tuple:
        """Рассчитать уровень риска (score 0-100)"""
        
        risk_score = 0
        reasons = []
        
        # 1. Whale alerts (0-40 points)
        if s.whale_alert_level == "critical":
            risk_score += 40
            reasons.append("Whale CRITICAL")
        elif s.whale_alert_level == "warning":
            risk_score += 25
            reasons.append("Whale WARNING")
        elif s.whale_alert_level == "attention":
            risk_score += 10
            reasons.append("Whale ATTENTION")
        
        # 2. Экстремальный Long/Short (0-20 points)
        if s.long_ratio > 75:
            risk_score += 20
            reasons.append(f"L/S {s.long_ratio:.0f}%")
        elif s.long_ratio > 70:
            risk_score += 15
        elif s.long_ratio < 25:
            risk_score += 20
            reasons.append(f"L/S {s.long_ratio:.0f}%")
        elif s.long_ratio < 30:
            risk_score += 15
        
        # 3. Fear & Greed экстремумы (0-15 points)
        if s.fear_greed < 15:
            risk_score += 15
            reasons.append(f"F&G: {s.fear_greed}")
        elif s.fear_greed < 25:
            risk_score += 8
        elif s.fear_greed > 85:
            risk_score += 15
            reasons.append(f"F&G: {s.fear_greed}")
        elif s.fear_greed > 75:
            risk_score += 8
        
        # 4. Важные новости/события (0-20 points)
        if s.important_event_soon:
            risk_score += 20
            reasons.append(f"Event: {s.event_name[:20]}")
        if s.market_mode == "WAIT_EVENT":
            risk_score += 15
        elif s.market_mode == "NEWS_ALERT":
            risk_score += 10
        
        # 5. Funding Rate экстремумы (0-15 points)
        if abs(s.funding_rate) > 0.15:
            risk_score += 15
            reasons.append(f"Funding: {s.funding_rate:+.3f}%")
        elif abs(s.funding_rate) > 0.1:
            risk_score += 10
        elif abs(s.funding_rate) > 0.05:
            risk_score += 5
        
        # 6. OI резкие изменения (0-10 points)
        if abs(s.oi_change_1h) > 5:
            risk_score += 10
            reasons.append(f"OI 1h: {s.oi_change_1h:+.1f}%")
        elif abs(s.oi_change_1h) > 3:
            risk_score += 5
        
        # Определяем уровень
        if risk_score >= 60:
            risk_level = "extreme"
        elif risk_score >= 45:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "elevated"
        else:
            risk_level = "normal"
        
        logger.debug(f"Risk: {risk_score} ({risk_level}) — {', '.join(reasons)}")
        
        return risk_score, risk_level
    
    def _get_recommendation(self, s: MarketSituation) -> str:
        """Получить рекомендацию"""
        
        if s.risk_level == "extreme":
            return "🚨 ЗАКРЫТЬ ВСЕ ПОЗИЦИИ! Директор берёт управление!"
        
        elif s.risk_level == "high":
            if s.long_ratio > 70:
                return "⚠️ Опасно для ЛОНГОВ! Толпа перегрета."
            elif s.long_ratio < 30:
                return "⚠️ Опасно для ШОРТОВ! Толпа перегрета."
            elif s.important_event_soon:
                return f"⚠️ Важное событие скоро! {s.event_name}"
            else:
                return "⚠️ Не открывать новые позиции. Ждать."
        
        elif s.risk_level == "elevated":
            return "👀 Уменьшить размер позиций. Быть осторожным."
        
        else:
            # Возможности для агрессивной торговли
            if s.fear_greed < 25 and s.long_ratio < 40:
                return "🟢 Экстремальный страх — хорошо для ЛОНГОВ!"
            elif s.fear_greed > 75 and s.long_ratio > 60:
                return "🔴 Экстремальная жадность — хорошо для ШОРТОВ!"
            else:
                return "✅ Работник продолжает по стратегиям."
    
    async def make_decision(self) -> DirectorCommand:
        """
        🧠 Главный метод — принятие решения
        """
        
        situation = await self.analyze_situation()
        
        decision = DirectorDecision.CONTINUE
        mode = TradingMode.AUTO
        reason = ""
        details = {}
        
        # === КРИТИЧЕСКАЯ СИТУАЦИЯ (risk >= 60) ===
        if situation.risk_level == "extreme":
            decision = DirectorDecision.CLOSE_ALL
            mode = TradingMode.MANUAL
            reason = "🚨 КРИТИЧЕСКАЯ СИТУАЦИЯ!\n"
            
            if situation.whale_alert_level == "critical":
                reason += "• Whale Alert: CRITICAL\n"
            if situation.important_event_soon:
                reason += f"• Событие: {situation.event_name}\n"
            if situation.long_ratio > 75:
                reason += f"• {situation.long_ratio:.0f}% в лонгах — ликвидации близко!\n"
            if situation.long_ratio < 25:
                reason += f"• {situation.short_ratio:.0f}% в шортах — шорт-сквиз близко!\n"
            if abs(situation.funding_rate) > 0.15:
                reason += f"• Funding: {situation.funding_rate:+.3f}%\n"
            
            reason += f"\n📊 Risk Score: {situation.risk_score}/100"
            
            # Директор берёт управление на 1 час
            self.manual_control_until = datetime.now() + timedelta(hours=1)
            self.current_mode = TradingMode.MANUAL
            self.allow_new_longs = False
            self.allow_new_shorts = False
            self.interventions += 1
        
        # === ВЫСОКИЙ РИСК (risk 45-59) ===
        elif situation.risk_level == "high":
            mode = TradingMode.SUPERVISED
            
            if situation.long_ratio > 70:
                decision = DirectorDecision.CLOSE_LONGS
                reason = f"⚠️ {situation.long_ratio:.0f}% толпы в лонгах!\n"
                reason += "Закрываю ЛОНГИ, блокирую новые."
                self.allow_new_longs = False
                self.allow_new_shorts = True
            
            elif situation.long_ratio < 30:
                decision = DirectorDecision.CLOSE_SHORTS
                reason = f"⚠️ {situation.short_ratio:.0f}% толпы в шортах!\n"
                reason += "Закрываю ШОРТЫ, блокирую новые."
                self.allow_new_longs = True
                self.allow_new_shorts = False
            
            elif situation.important_event_soon:
                decision = DirectorDecision.PAUSE_NEW
                reason = f"⚠️ Важное событие: {situation.event_name}\n"
                reason += "Не открываю новые позиции."
                self.allow_new_longs = False
                self.allow_new_shorts = False
            
            else:
                decision = DirectorDecision.PAUSE_NEW
                reason = "⚠️ Высокий риск. Пауза на новые позиции."
                self.allow_new_longs = False
                self.allow_new_shorts = False
            
            reason += f"\n📊 Risk Score: {situation.risk_score}/100"
            self.current_mode = TradingMode.SUPERVISED
            self.interventions += 1
        
        # === ПОВЫШЕННЫЙ РИСК (risk 25-44) ===
        elif situation.risk_level == "elevated":
            decision = DirectorDecision.REDUCE_SIZE
            mode = TradingMode.SUPERVISED
            reason = "👀 Повышенный риск. Уменьшаю размер позиций.\n"
            reason += f"📊 Risk Score: {situation.risk_score}/100"
            
            self.size_multiplier = 0.5
            self.allow_new_longs = True
            self.allow_new_shorts = True
            self.current_mode = TradingMode.SUPERVISED
        
        # === НОРМАЛЬНАЯ СИТУАЦИЯ (risk < 25) ===
        else:
            decision = DirectorDecision.CONTINUE
            mode = TradingMode.AUTO
            
            # Проверяем возможности
            if situation.fear_greed < 25 and situation.long_ratio < 40:
                decision = DirectorDecision.AGGRESSIVE_LONG
                reason = "🟢 Экстремальный страх + мало лонгов = ПОКУПАЙ!\n"
                self.size_multiplier = 1.5
            elif situation.fear_greed > 75 and situation.long_ratio > 60:
                decision = DirectorDecision.AGGRESSIVE_SHORT
                reason = "🔴 Экстремальная жадность + много лонгов = ШОРТИ!\n"
                self.size_multiplier = 1.5
            else:
                reason = "✅ Ситуация нормальная. Работник продолжает.\n"
                self.size_multiplier = 1.0
            
            reason += f"📊 Risk Score: {situation.risk_score}/100"
            
            self.allow_new_longs = True
            self.allow_new_shorts = True
            self.current_mode = TradingMode.AUTO
        
        # Создаём команду
        command = DirectorCommand(
            decision=decision,
            mode=mode,
            reason=reason,
            details={
                "size_multiplier": self.size_multiplier,
                "allow_longs": self.allow_new_longs,
                "allow_shorts": self.allow_new_shorts,
                "risk_score": situation.risk_score,
                "risk_level": situation.risk_level,
            }
        )
        
        # Сохраняем
        self.last_command = command
        self.command_history.append(command)
        if len(self.command_history) > 100:
            self.command_history = self.command_history[-100:]
        
        self.decisions_made += 1
        
        # Логируем важные решения
        if decision != DirectorDecision.CONTINUE:
            logger.warning(f"🎩 Director: {decision.value} — Risk {situation.risk_score}")
        
        return command
    
    def is_manual_control_active(self) -> bool:
        """Директор сейчас управляет?"""
        if self.manual_control_until:
            if datetime.now() < self.manual_control_until:
                return True
            else:
                # Время вышло — возвращаем AUTO
                self.manual_control_until = None
                self.current_mode = TradingMode.AUTO
        return False
    
    def can_open_trade(self, direction: str) -> tuple:
        """Можно ли открыть сделку?"""
        
        if self.is_manual_control_active():
            return False, "🎩 Директор управляет. Новые сделки запрещены."
        
        if direction == "LONG" and not self.allow_new_longs:
            return False, "🚫 ЛОНГИ заблокированы Директором"
        
        if direction == "SHORT" and not self.allow_new_shorts:
            return False, "🚫 ШОРТЫ заблокированы Директором"
        
        return True, "OK"
    
    def get_size_multiplier(self) -> float:
        """Множитель размера позиции"""
        return self.size_multiplier
    
    def get_status_text(self) -> str:
        """Статус для Telegram"""
        
        mode_emoji = {
            TradingMode.AUTO: "🤖",
            TradingMode.SUPERVISED: "👀",
            TradingMode.MANUAL: "🎩",
            TradingMode.PAUSED: "⏸️",
        }
        
        text = f"""🎩 *Director AI Status*

*Режим:* {mode_emoji.get(self.current_mode, '❓')} {self.current_mode.value.upper()}
*Решений:* {self.decisions_made} (вмешательств: {self.interventions})
"""
        
        if self.situation:
            s = self.situation
            risk_emoji = {"normal": "🟢", "elevated": "🟡", "high": "🟠", "extreme": "🔴"}
            
            text += f"""
*Риск:* {risk_emoji.get(s.risk_level, '⚪')} {s.risk_level.upper()} ({s.risk_score}/100)

*Метрики:*
• Whale: {s.whale_alert_level}
• L/S Ratio: {s.long_ratio:.0f}% / {s.short_ratio:.0f}%
• F&G: {s.fear_greed}
• Funding: {s.funding_rate:+.4f}%

*Позиции:* {s.open_positions} (L:{s.long_positions} S:{s.short_positions})
*PnL:* ${s.total_pnl:+.2f}
"""
        
        text += f"""
*Разрешения:*
• LONG: {'✅' if self.allow_new_longs else '🚫'}
• SHORT: {'✅' if self.allow_new_shorts else '🚫'}
• Size: x{self.size_multiplier:.1f}
"""
        
        if self.last_command:
            text += f"\n*Решение:*\n{self.last_command.reason[:200]}"
        
        if self.is_manual_control_active():
            remaining = (self.manual_control_until - datetime.now()).seconds // 60
            text += f"\n\n🎩 *Директор у руля ещё {remaining} мин!*"
        
        return text


# Singleton
director_ai = DirectorAI()


async def get_director_decision() -> DirectorCommand:
    """Публичная функция для получения решения"""
    return await director_ai.make_decision()


# ==========================================
# 🎩 DIRECTOR TRADER — АКТИВНАЯ ТОРГОВЛЯ
# ==========================================

@dataclass
class DirectorTrade:
    """Сделка открытая Директором лично"""
    id: str
    symbol: str
    direction: str  # "LONG" | "SHORT"
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    size_usd: float
    reason: str
    opened_at: datetime
    
    # Динамическое управление
    initial_sl: float = 0.0
    initial_tp: float = 0.0
    trailing_activated: bool = False
    highest_price: float = 0.0  # Для LONG
    lowest_price: float = float('inf')  # Для SHORT
    adjustments_count: int = 0
    
    # Статус
    status: str = "OPEN"  # OPEN, CLOSED, CANCELLED
    close_reason: str = ""
    pnl_percent: float = 0.0
    pnl_usd: float = 0.0
    
    def __post_init__(self):
        self.initial_sl = self.stop_loss
        self.initial_tp = self.take_profit
        self.highest_price = self.entry_price
        self.lowest_price = self.entry_price


class DirectorTrader:
    """
    🎩 Director как активный трейдер
    
    Может:
    - Открывать позиции БЕЗ стратегий Работника
    - Управлять позициями в реалтайме
    - Двигать SL/TP
    - Закрывать по своему решению
    """
    
    def __init__(self):
        self.active_trades: Dict[str, DirectorTrade] = {}
        self.trade_history: list = []
        self.is_controlling: bool = False
        self.control_reason: str = ""
        self._management_tasks: Dict[str, asyncio.Task] = {}
        
        # История режимов
        self.mode_history: list = []
        
        # Настройки агрессивности
        self.config = {
            "check_interval_seconds": 10,  # Проверка каждые 10 сек
            "trailing_activation_percent": 0.5,  # Активация трейлинга после +0.5%
            "trailing_distance_percent": 0.3,  # Дистанция трейлинга 0.3%
            "max_position_time_hours": 24,  # Максимум 24 часа в позиции
            "aggressive_tp_multiplier": 2.0,  # TP в 2 раза больше SL
            "news_check_interval": 60,  # Проверка новостей каждые 60 сек
        }
        
        # Статистика
        self.stats = {
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl_percent": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_hold_time_minutes": 0.0,
        }
        
        logger.info("🎩 DirectorTrader инициализирован")
    
    async def _notify_take_control(self, direction: str, reason: str):
        """🔔 Уведомление: CryptoDen берёт управление"""
        from app.notifications.telegram_bot import telegram_bot
        
        # Причина на русском
        reason_ru = self._translate_reason(reason)
        direction_emoji = "📈" if direction == "LONG" else "📉"
        direction_text = "ПОКУПКА" if direction == "LONG" else "ПРОДАЖА"
        
        text = (
            f"⚡ *CryptoDen взял управление!*\n\n"
            f"{direction_emoji} Направление: *{direction_text}*\n"
            f"📊 Причина: _{reason_ru}_\n\n"
            f"🤖 Автоматическое управление позицией\n"
            f"🔄 Проверка каждые 10 сек"
        )
        
        await telegram_bot.send_message(text)
        
        # Сохраняем в историю
        self.mode_history.append({
            "time": datetime.now().isoformat(),
            "event": "TAKE_CONTROL",
            "direction": direction,
            "reason": reason_ru,
        })
        
        # Ограничиваем историю
        if len(self.mode_history) > 50:
            self.mode_history = self.mode_history[-50:]
    
    async def _notify_release_control(self, pnl_percent: float, close_reason: str):
        """🔔 Уведомление: CryptoDen отдаёт управление"""
        from app.notifications.telegram_bot import telegram_bot
        
        pnl_emoji = "✅" if pnl_percent > 0 else "❌"
        reason_ru = self._translate_close_reason(close_reason)
        
        text = (
            f"🔓 *Управление передано Работнику*\n\n"
            f"{pnl_emoji} Результат: *{pnl_percent:+.2f}%*\n"
            f"📝 Причина выхода: _{reason_ru}_\n\n"
            f"👷 Работник продолжает по стратегиям"
        )
        
        await telegram_bot.send_message(text)
        
        # Сохраняем в историю
        self.mode_history.append({
            "time": datetime.now().isoformat(),
            "event": "RELEASE_CONTROL",
            "pnl_percent": pnl_percent,
            "reason": reason_ru,
        })
    
    def _translate_reason(self, reason: str) -> str:
        """Перевод причины TAKE_CONTROL на русский"""
        translations = {
            "Extreme fear + bullish news = STRONG BUY": "Экстремальный страх + позитивные новости",
            "Extreme greed + bearish news = STRONG SELL": "Экстремальная жадность + негативные новости",
            "Mass long liquidations = potential reversal": "Массовые ликвидации лонгов → разворот",
            "Mass short liquidations = potential reversal": "Массовые ликвидации шортов → разворот",
            "Extreme funding rate = longs overextended": "Экстремальный funding — лонги перегреты",
            "Negative funding = shorts overextended": "Отрицательный funding — шорты перегреты",
            "Extreme fear + low long ratio = BUY opportunity": "Сильный страх + мало покупателей",
            "Extreme greed + high long ratio = SELL opportunity": "Сильная жадность + много покупателей",
        }
        return translations.get(reason, reason[:50])
    
    def _translate_close_reason(self, reason: str) -> str:
        """Перевод причины закрытия на русский"""
        if "TAKE_PROFIT" in reason:
            return "Достигнут Take Profit 🎯"
        elif "STOP_LOSS" in reason:
            return "Сработал Stop Loss 🛑"
        elif "TRAILING" in reason:
            return "Trailing Stop защитил прибыль 📈"
        elif "NEWS" in reason:
            return "Изменились новости 📰"
        elif "WHALE" in reason:
            return "Изменились метрики китов 🐋"
        elif "MAX_TIME" in reason:
            return "Достигнут лимит времени ⏰"
        else:
            return reason[:30]
    
    async def should_take_control(
        self, 
        whale_metrics: Dict,
        news_context: Dict,
        market_data: Dict
    ) -> tuple:
        """
        🎩 Решить нужно ли брать TAKE_CONTROL
        
        Returns:
            (should_take, direction, reason)
        """
        
        fear_greed = whale_metrics.get("fear_greed", 50)
        long_ratio = whale_metrics.get("long_ratio", 50)
        funding_rate = whale_metrics.get("funding_rate", 0)
        oi_change = whale_metrics.get("oi_change_24h", 0)
        
        news_sentiment = news_context.get("sentiment", "neutral")
        critical_count = news_context.get("critical_count", 0)
        
        # === СЦЕНАРИЙ 1: Экстремальный страх + бычьи новости ===
        if fear_greed < 20 and news_sentiment == "bullish" and critical_count > 0:
            logger.warning("🎩 TAKE_CONTROL: Экстремальный страх + бычьи новости!")
            return True, "LONG", "Extreme fear + bullish news = STRONG BUY"
        
        # === СЦЕНАРИЙ 2: Экстремальная жадность + медвежьи новости ===
        if fear_greed > 80 and news_sentiment == "bearish" and critical_count > 0:
            logger.warning("🎩 TAKE_CONTROL: Экстремальная жадность + медвежьи новости!")
            return True, "SHORT", "Extreme greed + bearish news = STRONG SELL"
        
        # === СЦЕНАРИЙ 3: Массовые ликвидации лонгов (потенциальный разворот) ===
        liq_long = whale_metrics.get("liq_long", 0)
        if liq_long > 50_000_000 and fear_greed < 25:  # $50M+ ликвидаций
            logger.warning("🎩 TAKE_CONTROL: Массовые ликвидации лонгов!")
            return True, "LONG", "Mass long liquidations = potential reversal"
        
        # === СЦЕНАРИЙ 4: Массовые ликвидации шортов ===
        liq_short = whale_metrics.get("liq_short", 0)
        if liq_short > 50_000_000 and fear_greed > 75:
            logger.warning("🎩 TAKE_CONTROL: Массовые ликвидации шортов!")
            return True, "SHORT", "Mass short liquidations = potential reversal"
        
        # === СЦЕНАРИЙ 5: Funding экстремальный ===
        if funding_rate > 0.1 and long_ratio > 70:  # Лонги сильно переплачивают
            logger.warning("🎩 TAKE_CONTROL: Экстремальный funding!")
            return True, "SHORT", "Extreme funding rate = longs overextended"
        
        if funding_rate < -0.1 and long_ratio < 30:  # Шорты переплачивают
            logger.warning("🎩 TAKE_CONTROL: Отрицательный funding!")
            return True, "LONG", "Negative funding = shorts overextended"
        
        # === СЦЕНАРИЙ 6: Extreme Fear + мало лонгов ===
        if fear_greed < 15 and long_ratio < 35:
            logger.warning("🎩 TAKE_CONTROL: Extreme Fear + мало лонгов!")
            return True, "LONG", "Extreme fear + low long ratio = BUY opportunity"
        
        # === СЦЕНАРИЙ 7: Extreme Greed + много лонгов ===
        if fear_greed > 85 and long_ratio > 65:
            logger.warning("🎩 TAKE_CONTROL: Extreme Greed + много лонгов!")
            return True, "SHORT", "Extreme greed + high long ratio = SELL opportunity"
        
        return False, "", ""
    
    async def execute_trade(
        self,
        symbol: str,
        direction: str,
        reason: str,
        size_usd: Optional[float] = None
    ) -> Optional[DirectorTrade]:
        """
        🎩 Director открывает СВОЮ позицию
        """
        
        import uuid
        
        try:
            # Проверка лимитов
            if symbol in self.active_trades:
                logger.warning(f"🎩 Уже есть активная сделка Director по {symbol}")
                return None
            
            if len(self.active_trades) >= 3:  # Макс 3 сделки Director
                logger.warning("🎩 Достигнут лимит сделок Director (3)")
                return None
            
            # Получить цену
            from app.trading.bybit.client import BybitClient
            async with BybitClient(testnet=False) as client:
                current_price = await client.get_price(symbol)
            
            if not current_price:
                logger.error(f"🎩 Не удалось получить цену {symbol}")
                return None
            
            # Получить баланс
            from app.core.monitor import market_monitor
            
            # Размер позиции (20% от баланса для Director - агрессивно!)
            if size_usd is None:
                size_usd = market_monitor.current_balance * 0.20
            
            # Минимум $50
            if size_usd < 50:
                logger.warning(f"🎩 Размер слишком мал: ${size_usd:.2f}")
                return None
            
            # Рассчитать SL/TP
            if direction == "LONG":
                stop_loss = current_price * 0.98  # -2%
                take_profit = current_price * 1.04  # +4% (2:1 ratio)
            else:
                stop_loss = current_price * 1.02  # +2%
                take_profit = current_price * 0.96  # -4%
            
            # Создать сделку
            trade = DirectorTrade(
                id=f"DIR_{uuid.uuid4().hex[:8]}",
                symbol=symbol,
                direction=direction,
                entry_price=current_price,
                current_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                size_usd=size_usd,
                reason=reason,
                opened_at=datetime.now(),
            )
            
            # Выполнить на бирже (если не paper mode)
            if not market_monitor.paper_trading:
                async with BybitClient(testnet=False) as client:
                    if direction == "LONG":
                        order = await client.market_buy(f"{symbol}USDT", size_usd)
                        if order.get('retCode') != 0:
                            logger.error(f"🎩 Ошибка ордера: {order}")
                            return None
                    else:
                        # SHORT на споте - только если есть баланс
                        logger.warning(f"🎩 SHORT на споте не поддерживается для {symbol}")
            
            # Сохранить
            self.active_trades[symbol] = trade
            self.is_controlling = True
            self.control_reason = reason
            
            # Запустить управление позицией
            task = asyncio.create_task(self._manage_trade(trade))
            self._management_tasks[symbol] = task
            
            # 🔔 Уведомление о взятии управления
            await self._notify_take_control(direction, reason)
            
            # Уведомление о сделке
            from app.notifications.telegram_bot import telegram_bot
            direction_emoji = "📈" if direction == "LONG" else "📉"
            await telegram_bot.send_message(
                f"{direction_emoji} *Открыта позиция*\n\n"
                f"🪙 *{symbol}* | {direction}\n"
                f"💰 ${size_usd:.0f} | Вход: ${current_price:,.2f}\n"
                f"🛑 SL: ${stop_loss:,.2f} | 🎯 TP: ${take_profit:,.2f}"
            )
            
            logger.info(f"🎩 DIRECTOR OPENED: {symbol} {direction} @ ${current_price:,.2f}")
            
            self.stats["total_trades"] += 1
            
            return trade
            
        except Exception as e:
            logger.error(f"🎩 Ошибка открытия Director trade: {e}")
            return None
    
    async def _manage_trade(self, trade: DirectorTrade):
        """
        🎩 Цикл управления позицией Director
        Проверяет каждые 10 секунд!
        """
        
        logger.info(f"🎩 Начинаю управление {trade.symbol} {trade.direction}")
        
        last_news_check = datetime.now()
        
        while trade.status == "OPEN":
            try:
                # Получить текущую цену
                from app.trading.bybit.client import BybitClient
                async with BybitClient(testnet=False) as client:
                    current_price = await client.get_price(trade.symbol)
                
                if not current_price:
                    await asyncio.sleep(self.config["check_interval_seconds"])
                    continue
                
                trade.current_price = current_price
                
                # Обновить PnL
                if trade.direction == "LONG":
                    trade.pnl_percent = ((current_price - trade.entry_price) / trade.entry_price) * 100
                else:
                    trade.pnl_percent = ((trade.entry_price - current_price) / trade.entry_price) * 100
                
                trade.pnl_usd = trade.size_usd * (trade.pnl_percent / 100)
                
                # === ПРОВЕРКА STOP LOSS ===
                if trade.direction == "LONG" and current_price <= trade.stop_loss:
                    await self._close_trade(trade, "STOP_LOSS")
                    break
                    
                if trade.direction == "SHORT" and current_price >= trade.stop_loss:
                    await self._close_trade(trade, "STOP_LOSS")
                    break
                
                # === ПРОВЕРКА TAKE PROFIT ===
                if trade.direction == "LONG" and current_price >= trade.take_profit:
                    await self._close_trade(trade, "TAKE_PROFIT")
                    break
                    
                if trade.direction == "SHORT" and current_price <= trade.take_profit:
                    await self._close_trade(trade, "TAKE_PROFIT")
                    break
                
                # === TRAILING STOP ===
                await self._update_trailing_stop(trade, current_price)
                
                # === ПРОВЕРКА НОВОСТЕЙ (каждые 60 сек) ===
                if (datetime.now() - last_news_check).seconds >= self.config["news_check_interval"]:
                    should_close, close_reason = await self._check_news_exit(trade)
                    if should_close:
                        await self._close_trade(trade, f"NEWS: {close_reason}")
                        break
                    last_news_check = datetime.now()
                
                # === ПРОВЕРКА WHALE МЕТРИК ===
                whale_exit = await self._check_whale_exit(trade)
                if whale_exit:
                    await self._close_trade(trade, f"WHALE: {whale_exit}")
                    break
                
                # === ПРОВЕРКА ВРЕМЕНИ ===
                hours_open = (datetime.now() - trade.opened_at).seconds / 3600
                if hours_open >= self.config["max_position_time_hours"]:
                    await self._close_trade(trade, "MAX_TIME")
                    break
                
                # Логирование каждые 5 минут
                minutes_open = (datetime.now() - trade.opened_at).seconds / 60
                if int(minutes_open) % 5 == 0 and int(minutes_open) > 0:
                    logger.debug(
                        f"🎩 {trade.symbol}: PnL {trade.pnl_percent:+.2f}% "
                        f"| Price: ${current_price:,.2f} | SL: ${trade.stop_loss:,.2f}"
                    )
                
                await asyncio.sleep(self.config["check_interval_seconds"])
                
            except asyncio.CancelledError:
                logger.info(f"🎩 Управление {trade.symbol} отменено")
                break
            except Exception as e:
                logger.error(f"🎩 Ошибка управления {trade.symbol}: {e}")
                await asyncio.sleep(self.config["check_interval_seconds"])
        
        logger.info(f"🎩 Завершено управление {trade.symbol}")
    
    async def _update_trailing_stop(self, trade: DirectorTrade, current_price: float):
        """Обновить trailing stop"""
        
        activation_pct = self.config["trailing_activation_percent"]
        distance_pct = self.config["trailing_distance_percent"]
        
        if trade.direction == "LONG":
            # Обновляем максимум
            if current_price > trade.highest_price:
                trade.highest_price = current_price
            
            # Проверяем активацию трейлинга
            profit_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
            
            if profit_pct >= activation_pct and not trade.trailing_activated:
                trade.trailing_activated = True
                logger.info(f"🎩 Trailing активирован для {trade.symbol} @ +{profit_pct:.2f}%")
            
            # Двигаем SL
            if trade.trailing_activated:
                new_sl = trade.highest_price * (1 - distance_pct / 100)
                
                if new_sl > trade.stop_loss:
                    old_sl = trade.stop_loss
                    trade.stop_loss = new_sl
                    trade.adjustments_count += 1
                    
                    logger.info(
                        f"🎩 Trailing SL: {trade.symbol} "
                        f"${old_sl:,.2f} → ${new_sl:,.2f}"
                    )
                    
                    # Уведомление о значительном движении
                    if trade.adjustments_count % 5 == 0:
                        from app.notifications.telegram_bot import telegram_bot
                        await telegram_bot.send_message(
                            f"🎩 *TRAILING UPDATE* {trade.symbol}\n"
                            f"📈 Новый SL: ${new_sl:,.2f}\n"
                            f"💰 PnL: {trade.pnl_percent:+.2f}%"
                        )
        
        else:  # SHORT
            if current_price < trade.lowest_price:
                trade.lowest_price = current_price
            
            profit_pct = ((trade.entry_price - current_price) / trade.entry_price) * 100
            
            if profit_pct >= activation_pct and not trade.trailing_activated:
                trade.trailing_activated = True
                logger.info(f"🎩 Trailing активирован для SHORT {trade.symbol}")
            
            if trade.trailing_activated:
                new_sl = trade.lowest_price * (1 + distance_pct / 100)
                
                if new_sl < trade.stop_loss:
                    old_sl = trade.stop_loss
                    trade.stop_loss = new_sl
                    trade.adjustments_count += 1
                    
                    logger.info(f"🎩 Trailing SL SHORT: ${old_sl:,.2f} → ${new_sl:,.2f}")
    
    async def _check_news_exit(self, trade: DirectorTrade) -> tuple:
        """Проверить нужно ли выходить по новостям"""
        
        try:
            from app.intelligence.news_parser import news_parser
            
            context = await news_parser.get_market_context()
            news = context.get("news", [])
            
            if not news:
                return False, ""
            
            # Ищем критические новости против позиции
            for item in news[:5]:  # Последние 5 новостей
                sentiment = item.get("sentiment", 0)
                importance = item.get("importance", "LOW")
                
                if importance != "HIGH":
                    continue
                
                # LONG позиция + bearish новость
                if trade.direction == "LONG" and sentiment < -0.3:
                    return True, f"Bearish news: {item.get('title', '')[:50]}"
                
                # SHORT позиция + bullish новость
                if trade.direction == "SHORT" and sentiment > 0.3:
                    return True, f"Bullish news: {item.get('title', '')[:50]}"
            
            return False, ""
            
        except Exception:
            return False, ""
    
    async def _check_whale_exit(self, trade: DirectorTrade) -> Optional[str]:
        """Проверить нужно ли выходить по Whale метрикам"""
        
        try:
            from app.ai.whale_ai import whale_ai
            
            metrics = whale_ai.last_metrics
            
            if not metrics:
                return None
            
            # Резкое изменение Long/Short Ratio против позиции
            long_ratio = metrics.long_ratio
            
            if trade.direction == "LONG" and long_ratio > 75:
                return "Long ratio too high (>75%)"
            
            if trade.direction == "SHORT" and long_ratio < 25:
                return "Short ratio too high (Long <25%)"
            
            # Резкое изменение OI
            oi_change = metrics.oi_change_1h
            
            if abs(oi_change) > 10:  # >10% за час
                return f"Extreme OI change: {oi_change:+.1f}%"
            
            return None
            
        except Exception:
            return None
    
    async def _close_trade(self, trade: DirectorTrade, reason: str):
        """Закрыть сделку Director"""
        
        try:
            trade.status = "CLOSED"
            trade.close_reason = reason
            
            # Закрыть на бирже
            from app.core.monitor import market_monitor
            
            if not market_monitor.paper_trading:
                from app.trading.bybit.client import BybitClient
                async with BybitClient(testnet=False) as client:
                    if trade.direction == "LONG":
                        # Продаём
                        balance = await client.get_balance(trade.symbol)
                        if balance and balance > 0:
                            await client.market_sell(f"{trade.symbol}USDT", balance)
            
            # Обновить баланс
            await market_monitor.update_balance_after_close(trade.pnl_usd)
            
            # Статистика
            if trade.pnl_percent > 0:
                self.stats["winning_trades"] += 1
            
            self.stats["total_pnl_percent"] += trade.pnl_percent
            
            if trade.pnl_percent > self.stats["best_trade"]:
                self.stats["best_trade"] = trade.pnl_percent
            if trade.pnl_percent < self.stats["worst_trade"]:
                self.stats["worst_trade"] = trade.pnl_percent
            
            # Время в позиции
            hold_minutes = (datetime.now() - trade.opened_at).seconds / 60
            
            # Перенести в историю
            self.trade_history.append(trade)
            if trade.symbol in self.active_trades:
                del self.active_trades[trade.symbol]
            
            # Отменить таск управления
            if trade.symbol in self._management_tasks:
                self._management_tasks[trade.symbol].cancel()
                del self._management_tasks[trade.symbol]
            
            # Проверить нужно ли отпустить контроль
            was_controlling = self.is_controlling
            if not self.active_trades:
                self.is_controlling = False
                self.control_reason = ""
            
            # Уведомление о закрытии сделки
            from app.notifications.telegram_bot import telegram_bot
            pnl_emoji = "🟢" if trade.pnl_percent > 0 else "🔴"
            
            await telegram_bot.send_message(
                f"📊 *Позиция закрыта*\n\n"
                f"🪙 *{trade.symbol}* | {trade.direction}\n"
                f"📍 ${trade.entry_price:,.2f} → ${trade.current_price:,.2f}\n"
                f"{pnl_emoji} *{trade.pnl_percent:+.2f}%* (${trade.pnl_usd:+.2f})\n"
                f"⏱ {hold_minutes:.0f} мин | 🔄 {trade.adjustments_count} корр."
            )
            
            # 🔔 Уведомление о передаче управления
            if was_controlling and not self.is_controlling:
                await self._notify_release_control(trade.pnl_percent, reason)
            
            logger.info(
                f"🎩 DIRECTOR CLOSED: {trade.symbol} {trade.direction} "
                f"PnL: {trade.pnl_percent:+.2f}% | Reason: {reason}"
            )
            
        except Exception as e:
            logger.error(f"🎩 Ошибка закрытия Director trade: {e}")
    
    async def close_all_director_trades(self, reason: str = "Manual close"):
        """Закрыть все сделки Director"""
        
        for symbol in list(self.active_trades.keys()):
            trade = self.active_trades[symbol]
            await self._close_trade(trade, reason)
    
    def get_status(self) -> Dict:
        """Получить статус Director Trader"""
        
        active = []
        for trade in self.active_trades.values():
            active.append({
                "symbol": trade.symbol,
                "direction": trade.direction,
                "entry": trade.entry_price,
                "current": trade.current_price,
                "pnl_percent": trade.pnl_percent,
                "sl": trade.stop_loss,
                "tp": trade.take_profit,
                "trailing": trade.trailing_activated,
                "adjustments": trade.adjustments_count,
            })
        
        return {
            "is_controlling": self.is_controlling,
            "control_reason": self.control_reason,
            "active_trades": active,
            "active_count": len(active),
            "stats": self.stats,
            "mode_history": self.mode_history[-10:],  # Последние 10 событий
        }
    
    def get_status_text(self) -> str:
        """Статус для Telegram"""
        
        status = self.get_status()
        
        text = "🎩 *DIRECTOR TRADER STATUS*\n\n"
        
        if status["is_controlling"]:
            text += f"⚡ *РЕЖИМ: TAKE\\_CONTROL*\n"
            text += f"📝 Причина: {status['control_reason'][:50]}\n\n"
        else:
            text += "😴 Режим: Обычный (Работник ищет сигналы)\n\n"
        
        if status["active_trades"]:
            text += f"📊 *Активные сделки ({status['active_count']}):*\n"
            for t in status["active_trades"]:
                emoji = "📈" if t["direction"] == "LONG" else "📉"
                pnl_emoji = "🟢" if t["pnl_percent"] > 0 else "🔴"
                text += f"\n{emoji} *{t['symbol']} {t['direction']}*\n"
                text += f"   📍 Вход: ${t['entry']:,.2f}\n"
                text += f"   💰 Сейчас: ${t['current']:,.2f}\n"
                text += f"   {pnl_emoji} PnL: {t['pnl_percent']:+.2f}%\n"
                text += f"   🛑 SL: ${t['sl']:,.2f}\n"
                text += f"   📈 Trailing: {'✅' if t['trailing'] else '❌'}\n"
        else:
            text += "📭 Нет активных сделок Director\n"
        
        text += f"\n📊 *Статистика:*\n"
        text += f"   Всего сделок: {status['stats']['total_trades']}\n"
        text += f"   Выигрышных: {status['stats']['winning_trades']}\n"
        text += f"   Общий PnL: {status['stats']['total_pnl_percent']:+.2f}%\n"
        
        if status['stats']['total_trades'] > 0:
            text += f"   Лучшая: {status['stats']['best_trade']:+.2f}%\n"
            text += f"   Худшая: {status['stats']['worst_trade']:+.2f}%\n"
        
        # История режимов
        if status.get('mode_history'):
            text += f"\n📜 *Последние события:*\n"
            for event in status['mode_history'][-5:]:
                time_str = event['time'][11:16]  # HH:MM
                if event['event'] == 'TAKE_CONTROL':
                    text += f"   ⚡ {time_str} Взял управление\n"
                else:
                    pnl = event.get('pnl_percent', 0)
                    emoji = "✅" if pnl > 0 else "❌"
                    text += f"   {emoji} {time_str} Передал ({pnl:+.1f}%)\n"
        
        return text


# Singleton
director_trader = DirectorTrader()
