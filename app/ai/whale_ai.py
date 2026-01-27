"""
🐋 Whale AI — Друг Директора
Следит за китами, ликвидациями, настроением рынка

Сигналит Директору когда что-то намечается!
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.core.logger import logger
from app.core.config import settings


class AlertLevel(Enum):
    """Уровень тревоги"""
    CALM = "calm"           # Всё спокойно
    ATTENTION = "attention" # Обрати внимание
    WARNING = "warning"     # Что-то намечается
    CRITICAL = "critical"   # СРОЧНО! Действуй!


@dataclass
class WhaleAlert:
    """Сигнал от Whale AI"""
    level: AlertLevel
    message: str
    metrics: Dict
    recommendation: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MarketMetrics:
    """Метрики рынка"""
    # Open Interest
    open_interest: float = 0
    oi_change_1h: float = 0  # % изменение за час
    oi_change_24h: float = 0  # % изменение за 24ч
    
    # Funding Rate
    funding_rate: float = 0
    funding_sentiment: str = "neutral"  # bullish/bearish/neutral
    
    # Long/Short Ratio
    long_ratio: float = 50
    short_ratio: float = 50
    ls_sentiment: str = "neutral"
    
    # Liquidations
    liquidations_1h: float = 0
    liq_long: float = 0
    liq_short: float = 0
    
    # Fear & Greed
    fear_greed_index: int = 50
    fear_greed_label: str = "Neutral"
    
    # Whale Activity
    whale_transactions: int = 0
    whale_sentiment: str = "neutral"
    
    timestamp: datetime = field(default_factory=datetime.now)


class WhaleAI:
    """
    🐋 Whale AI — Разведка рынка
    
    Отслеживает:
    1. Open Interest — сколько позиций открыто
    2. Funding Rate — кто платит за удержание (лонги или шорты)
    3. Long/Short Ratio — соотношение позиций
    4. Ликвидации — массовые закрытия
    5. Fear & Greed Index — настроение рынка
    6. Whale Alerts — крупные транзакции
    """
    
    BYBIT_URL = "https://api.bybit.com"
    
    def __init__(self):
        self.last_metrics: Optional[MarketMetrics] = None
        self.metrics_history: List[MarketMetrics] = []
        self.last_alert: Optional[WhaleAlert] = None
        self.alert_cooldown = timedelta(minutes=15)  # Не спамить алертами
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Пороговые значения для алертов
        self.thresholds = {
            "funding_extreme": 0.1,      # > 0.1% = перегрет
            "funding_negative": -0.05,   # < -0.05% = медведи платят
            "oi_spike": 5,               # > 5% за час = много новых позиций
            "oi_drop": -5,               # < -5% за час = массовое закрытие
            "ls_extreme_long": 70,       # > 70% лонгов = опасно
            "ls_extreme_short": 70,      # > 70% шортов = опасно
            "liquidation_spike": 50_000_000,  # $50M за час = большое движение
            "fear_extreme_fear": 20,     # < 20 = экстремальный страх
            "fear_extreme_greed": 80,    # > 80 = экстремальная жадность
        }
        
        logger.info("🐋 Whale AI инициализирован")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать сессию"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Закрыть сессию"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_market_metrics(self, symbol: str = "BTC") -> MarketMetrics:
        """Получить все метрики рынка"""
        
        metrics = MarketMetrics()
        
        # Собираем данные параллельно
        tasks = [
            self._get_open_interest(symbol),
            self._get_funding_rate(symbol),
            self._get_long_short_ratio(symbol),
            self._get_fear_greed(),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Open Interest
        if isinstance(results[0], dict):
            metrics.open_interest = results[0].get("oi", 0)
            metrics.oi_change_1h = results[0].get("change_1h", 0)
            metrics.oi_change_24h = results[0].get("change_24h", 0)
        
        # Funding Rate
        if isinstance(results[1], dict):
            metrics.funding_rate = results[1].get("rate", 0)
            metrics.funding_sentiment = results[1].get("sentiment", "neutral")
        
        # Long/Short Ratio
        if isinstance(results[2], dict):
            metrics.long_ratio = results[2].get("long", 50)
            metrics.short_ratio = results[2].get("short", 50)
            metrics.ls_sentiment = results[2].get("sentiment", "neutral")
        
        # Fear & Greed
        if isinstance(results[3], dict):
            metrics.fear_greed_index = results[3].get("value", 50)
            metrics.fear_greed_label = results[3].get("label", "Neutral")
        
        # Оценка ликвидаций на основе OI
        if metrics.oi_change_1h < -3:
            estimated = abs(metrics.oi_change_1h) * 10_000_000
            metrics.liquidations_1h = estimated
            metrics.liq_long = estimated * 0.6 if metrics.funding_rate > 0 else estimated * 0.4
            metrics.liq_short = estimated * 0.4 if metrics.funding_rate > 0 else estimated * 0.6
        
        # Сохраняем историю
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]
        
        self.last_metrics = metrics
        
        return metrics
    
    async def _get_open_interest(self, symbol: str) -> Dict:
        """Получить Open Interest с Bybit"""
        
        try:
            session = await self._get_session()
            url = f"{self.BYBIT_URL}/v5/market/open-interest"
            params = {
                "category": "linear",
                "symbol": f"{symbol}USDT",
                "intervalTime": "1h",
                "limit": "24"  # 24 часа
            }
            
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get("retCode") == 0:
                        oi_list = data.get("result", {}).get("list", [])
                        
                        if len(oi_list) >= 2:
                            current_oi = float(oi_list[0].get("openInterest", 0))
                            prev_oi_1h = float(oi_list[1].get("openInterest", 0))
                            prev_oi_24h = float(oi_list[-1].get("openInterest", 0)) if len(oi_list) >= 24 else prev_oi_1h
                            
                            change_1h = ((current_oi - prev_oi_1h) / prev_oi_1h * 100) if prev_oi_1h > 0 else 0
                            change_24h = ((current_oi - prev_oi_24h) / prev_oi_24h * 100) if prev_oi_24h > 0 else 0
                            
                            return {
                                "oi": current_oi,
                                "change_1h": round(change_1h, 2),
                                "change_24h": round(change_24h, 2)
                            }
        
        except Exception as e:
            logger.debug(f"OI error: {e}")
        
        return {"oi": 0, "change_1h": 0, "change_24h": 0}
    
    async def _get_funding_rate(self, symbol: str) -> Dict:
        """Получить Funding Rate с Bybit"""
        
        try:
            session = await self._get_session()
            url = f"{self.BYBIT_URL}/v5/market/tickers"
            params = {
                "category": "linear",
                "symbol": f"{symbol}USDT"
            }
            
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get("retCode") == 0:
                        tickers = data.get("result", {}).get("list", [])
                        
                        if tickers:
                            funding = float(tickers[0].get("fundingRate", 0)) * 100
                            
                            # Определяем sentiment
                            if funding > 0.1:
                                sentiment = "extreme_bullish"
                            elif funding > 0.05:
                                sentiment = "bullish"
                            elif funding < -0.05:
                                sentiment = "bearish"
                            elif funding < -0.1:
                                sentiment = "extreme_bearish"
                            else:
                                sentiment = "neutral"
                            
                            return {
                                "rate": round(funding, 4),
                                "sentiment": sentiment
                            }
        
        except Exception as e:
            logger.debug(f"Funding error: {e}")
        
        return {"rate": 0, "sentiment": "neutral"}
    
    async def _get_long_short_ratio(self, symbol: str) -> Dict:
        """Получить Long/Short Ratio с Bybit"""
        
        try:
            session = await self._get_session()
            url = f"{self.BYBIT_URL}/v5/market/account-ratio"
            params = {
                "category": "linear",
                "symbol": f"{symbol}USDT",
                "period": "1h",
                "limit": "1"
            }
            
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get("retCode") == 0:
                        ratio_list = data.get("result", {}).get("list", [])
                        
                        if ratio_list:
                            buy_ratio = float(ratio_list[0].get("buyRatio", 0.5)) * 100
                            sell_ratio = float(ratio_list[0].get("sellRatio", 0.5)) * 100
                            
                            # Sentiment
                            if buy_ratio > 70:
                                sentiment = "extreme_long"
                            elif buy_ratio > 60:
                                sentiment = "bullish"
                            elif sell_ratio > 70:
                                sentiment = "extreme_short"
                            elif sell_ratio > 60:
                                sentiment = "bearish"
                            else:
                                sentiment = "neutral"
                            
                            return {
                                "long": round(buy_ratio, 1),
                                "short": round(sell_ratio, 1),
                                "sentiment": sentiment
                            }
        
        except Exception as e:
            logger.debug(f"L/S ratio error: {e}")
        
        return {"long": 50, "short": 50, "sentiment": "neutral"}
    
    async def _get_fear_greed(self) -> Dict:
        """Получить Fear & Greed Index"""
        
        try:
            session = await self._get_session()
            url = "https://api.alternative.me/fng/?limit=1"
            
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("data"):
                        item = data["data"][0]
                        return {
                            "value": int(item.get("value", 50)),
                            "label": item.get("value_classification", "Neutral")
                        }
        
        except Exception as e:
            logger.debug(f"Fear & Greed error: {e}")
        
        return {"value": 50, "label": "Neutral"}
    
    async def analyze(self, symbol: str = "BTC") -> WhaleAlert:
        """
        🔍 Главный метод — анализ и генерация алерта
        
        Возвращает алерт для Директора
        """
        
        metrics = await self.get_market_metrics(symbol)
        
        alerts = []
        level = AlertLevel.CALM
        
        # 1. Проверяем Funding Rate
        if abs(metrics.funding_rate) > self.thresholds["funding_extreme"]:
            alerts.append(f"⚠️ Funding Rate экстремальный: {metrics.funding_rate:+.3f}%")
            if metrics.funding_rate > 0:
                alerts.append("   → Лонги перегреты, возможен дамп!")
            else:
                alerts.append("   → Шорты перегреты, возможен памп!")
            level = AlertLevel.WARNING
        
        # 2. Проверяем Open Interest
        if metrics.oi_change_1h > self.thresholds["oi_spike"]:
            alerts.append(f"📈 OI вырос на {metrics.oi_change_1h:+.1f}% за час!")
            alerts.append("   → Много новых позиций, жди движение!")
            if level.value < AlertLevel.ATTENTION.value:
                level = AlertLevel.ATTENTION
        
        elif metrics.oi_change_1h < self.thresholds["oi_drop"]:
            alerts.append(f"📉 OI упал на {metrics.oi_change_1h:.1f}% за час!")
            alerts.append("   → Массовое закрытие позиций!")
            level = AlertLevel.WARNING
        
        # 3. Проверяем Long/Short Ratio
        if metrics.long_ratio > self.thresholds["ls_extreme_long"]:
            alerts.append(f"🐂 {metrics.long_ratio:.0f}% в лонгах!")
            alerts.append("   → Толпа в лонгах = опасно для лонгов!")
            level = AlertLevel.WARNING
        
        elif metrics.short_ratio > self.thresholds["ls_extreme_short"]:
            alerts.append(f"🐻 {metrics.short_ratio:.0f}% в шортах!")
            alerts.append("   → Толпа в шортах = опасно для шортов!")
            level = AlertLevel.WARNING
        
        # 4. Проверяем Fear & Greed
        if metrics.fear_greed_index < self.thresholds["fear_extreme_fear"]:
            alerts.append(f"😱 Экстремальный страх: {metrics.fear_greed_index}")
            alerts.append("   → Возможен разворот вверх!")
            if level.value < AlertLevel.ATTENTION.value:
                level = AlertLevel.ATTENTION
        
        elif metrics.fear_greed_index > self.thresholds["fear_extreme_greed"]:
            alerts.append(f"🤑 Экстремальная жадность: {metrics.fear_greed_index}")
            alerts.append("   → Возможен разворот вниз!")
            if level.value < AlertLevel.ATTENTION.value:
                level = AlertLevel.ATTENTION
        
        # 5. Комбинированный анализ (КРИТИЧЕСКИЙ)
        critical_conditions = 0
        
        if metrics.funding_rate > 0.1 and metrics.long_ratio > 65:
            critical_conditions += 1
            alerts.append("🚨 Лонги перегреты + толпа в лонгах!")
        
        if metrics.funding_rate < -0.1 and metrics.short_ratio > 65:
            critical_conditions += 1
            alerts.append("🚨 Шорты перегреты + толпа в шортах!")
        
        if abs(metrics.oi_change_1h) > 5 and metrics.fear_greed_index > 75:
            critical_conditions += 1
            alerts.append("🚨 Резкий рост OI при жадности!")
        
        if critical_conditions >= 2:
            level = AlertLevel.CRITICAL
        
        # Формируем рекомендацию
        if level == AlertLevel.CRITICAL:
            recommendation = "🚨 ДИРЕКТОР! Бери управление! Закрывай позиции Работника!"
        elif level == AlertLevel.WARNING:
            recommendation = "⚠️ Директор, обрати внимание. Возможно скоро нужно действовать."
        elif level == AlertLevel.ATTENTION:
            recommendation = "👀 Интересная ситуация. Мониторь внимательнее."
        else:
            recommendation = "✅ Всё спокойно. Работник может продолжать."
        
        # Формируем сообщение
        if not alerts:
            message = "✅ Рынок спокоен, аномалий нет."
        else:
            message = "\n".join(alerts)
        
        alert = WhaleAlert(
            level=level,
            message=message,
            metrics={
                "funding_rate": metrics.funding_rate,
                "oi_change_1h": metrics.oi_change_1h,
                "oi_change_24h": metrics.oi_change_24h,
                "long_ratio": metrics.long_ratio,
                "short_ratio": metrics.short_ratio,
                "fear_greed": metrics.fear_greed_index,
            },
            recommendation=recommendation
        )
        
        self.last_alert = alert
        
        # Логируем если важно
        if level in [AlertLevel.WARNING, AlertLevel.CRITICAL]:
            logger.warning(f"🐋 Whale Alert [{level.value}]: {message[:100]}...")
        
        return alert
    
    def get_status_text(self) -> str:
        """Текст статуса для Telegram"""
        
        if not self.last_metrics:
            return "🐋 Whale AI: нет данных"
        
        m = self.last_metrics
        
        # Эмодзи для значений
        funding_emoji = "🔴" if m.funding_rate > 0.05 else "🟢" if m.funding_rate < -0.05 else "⚪"
        ls_emoji = "🐂" if m.long_ratio > 60 else "🐻" if m.short_ratio > 60 else "⚖️"
        fg_emoji = "😱" if m.fear_greed_index < 30 else "🤑" if m.fear_greed_index > 70 else "😐"
        oi_emoji = "📈" if m.oi_change_1h > 2 else "📉" if m.oi_change_1h < -2 else "➡️"
        
        text = f"""🐋 *Whale AI Report*

{funding_emoji} *Funding Rate:* {m.funding_rate:+.4f}%
{oi_emoji} *Open Interest:* {m.oi_change_1h:+.1f}% (1h) / {m.oi_change_24h:+.1f}% (24h)
{ls_emoji} *Long/Short:* {m.long_ratio:.0f}% / {m.short_ratio:.0f}%
{fg_emoji} *Fear & Greed:* {m.fear_greed_index} ({m.fear_greed_label})
"""
        
        if self.last_alert:
            level_emoji = {
                AlertLevel.CALM: "✅",
                AlertLevel.ATTENTION: "👀",
                AlertLevel.WARNING: "⚠️",
                AlertLevel.CRITICAL: "🚨",
            }
            text += f"\n*Статус:* {level_emoji.get(self.last_alert.level, '❓')} {self.last_alert.level.value.upper()}"
        
        return text
    
    def get_trading_bias(self) -> str:
        """Получить рекомендацию для торговли"""
        
        if not self.last_metrics:
            return "NEUTRAL"
        
        m = self.last_metrics
        
        bullish_signals = 0
        bearish_signals = 0
        
        # Funding Rate
        if m.funding_rate < -0.05:
            bullish_signals += 1  # Шорты платят = бычий сигнал
        elif m.funding_rate > 0.05:
            bearish_signals += 1  # Лонги платят = медвежий сигнал
        
        # Long/Short Ratio (контртрендовый)
        if m.long_ratio > 65:
            bearish_signals += 1  # Толпа в лонгах = опасно для лонгов
        elif m.short_ratio > 65:
            bullish_signals += 1  # Толпа в шортах = опасно для шортов
        
        # Fear & Greed (контртрендовый)
        if m.fear_greed_index < 25:
            bullish_signals += 1  # Страх = время покупать
        elif m.fear_greed_index > 75:
            bearish_signals += 1  # Жадность = время продавать
        
        if bullish_signals > bearish_signals:
            return "BULLISH"
        elif bearish_signals > bullish_signals:
            return "BEARISH"
        else:
            return "NEUTRAL"


# Singleton
whale_ai = WhaleAI()


async def check_whale_activity(symbol: str = "BTC") -> WhaleAlert:
    """Публичная функция для проверки активности китов"""
    return await whale_ai.analyze(symbol)
