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
━━━━━━━━━━━━━━━━━━━━━━
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
━━━━━━━━━━━━━━━━━━━━━━
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
