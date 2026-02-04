"""
🧠 Adaptive Brain v3.0 — Единый торговый мозг
Заменяет: Director AI + Director Brain + Worker
"""

import asyncio
import json
import aiohttp
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum

from app.core.config import settings
from app.core.logger import logger


class MarketRegime(Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    VOLATILE = "volatile"
    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"


class TradeAction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    WAIT = "WAIT"


@dataclass
class MarketData:
    symbol: str
    current_price: float = 0.0
    rsi_14: float = 50.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    macd_hist: float = 0.0
    atr: float = 0.0
    funding_rate: float = 0.0
    long_ratio: float = 50.0
    short_ratio: float = 50.0
    fear_greed: int = 50
    oi_change_1h: float = 0.0
    liq_long: float = 0.0
    liq_short: float = 0.0
    news_sentiment: str = "neutral"
    change_24h: float = 0.0


@dataclass
class BrainDecision:
    action: TradeAction
    symbol: str
    confidence: int = 0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    regime: MarketRegime = MarketRegime.RANGE
    reasoning: str = ""
    key_factors: List[str] = field(default_factory=list)
    restrictions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = "brain"


class AdaptiveBrain:
    
    COINS_TOP20 = [
        "BTC", "ETH", "SOL", "BNB", "XRP",
        "ADA", "DOGE", "LINK", "AVAX", "MATIC",
        "DOT", "UNI", "SHIB", "LTC", "ATOM",
        "APT", "ARB", "OP", "SUI", "NEAR"
    ]
    
    dynamic_coins: List[str] = []
    
    _cache: Dict[str, BrainDecision] = {}
    _cache_time: Dict[str, datetime] = {}
    _cache_ttl: int = 60
    
    MIN_CONFIDENCE = 65
    
    THRESHOLDS = {
        "long_ratio_max": 70,
        "short_ratio_max": 70,
        "funding_extreme": 0.1,
        "fear_extreme_low": 20,
        "fear_extreme_high": 80,
    }
    
    def __init__(self):
        self.model = "anthropic/claude-3.5-haiku"
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        logger.info("🧠 Adaptive Brain v3.0 initialized")
    
    async def analyze(self, symbol: str) -> BrainDecision:
        """Главный метод анализа"""
        try:
            if self._is_cached(symbol):
                return self._cache[symbol]
            
            market_data = await self._collect_market_data(symbol)
            
            # Проверка на отсутствие данных о цене
            if not market_data.current_price or market_data.current_price == 0:
                logger.warning(f"⚠️ No price data for {symbol}, skipping")
                return BrainDecision(
                    action=TradeAction.WAIT,
                    symbol=symbol,
                    confidence=0,
                    reasoning=f"No price data for {symbol}",
                    source="brain"
                )
            
            regime = self._detect_regime(market_data)
            restrictions = self._check_restrictions(market_data)
            
            if self._has_critical_restriction(restrictions, market_data):
                decision = BrainDecision(
                    action=TradeAction.WAIT,
                    symbol=symbol,
                    confidence=0,
                    regime=regime,
                    reasoning="Критические ограничения активны",
                    restrictions=restrictions,
                    source="brain"
                )
                self._save_to_cache(symbol, decision)
                return decision
            
            decision = await self._ai_analyze(market_data, regime, restrictions)
            self._save_to_cache(symbol, decision)
            return decision
            
        except Exception as e:
            logger.error(f"Brain analyze error for {symbol}: {e}")
            return BrainDecision(
                action=TradeAction.WAIT,
                symbol=symbol,
                confidence=0,
                reasoning=f"Error: {str(e)}",
                source="brain"
            )
    
    async def get_best_opportunity(self) -> Optional[BrainDecision]:
        """Найти лучшую возможность среди всех монет"""
        all_coins = list(set(self.COINS_TOP20 + self.dynamic_coins))
        decisions = []
        
        # Анализируем ВСЕ монеты (до 25 для скорости)
        coins_to_analyze = all_coins[:25]
        
        logger.info(f"🧠 Brain analyzing {len(coins_to_analyze)} coins...")
        
        for symbol in coins_to_analyze:
            try:
                decision = await self.analyze(symbol)
                if decision.action in [TradeAction.LONG, TradeAction.SHORT]:
                    if decision.confidence >= self.MIN_CONFIDENCE:
                        decisions.append(decision)
                        logger.debug(f"🧠 {symbol}: {decision.action.value} ({decision.confidence}%)")
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
                continue
        
        if not decisions:
            logger.debug("🧠 No actionable opportunities found")
            return None
        
        # Сортируем по confidence
        decisions.sort(key=lambda x: x.confidence, reverse=True)
        
        best = decisions[0]
        logger.info(f"🧠 Best opportunity: {best.action.value} {best.symbol} ({best.confidence}%)")
        
        return best
    
    def add_dynamic_coin(self, symbol: str):
        if symbol not in self.dynamic_coins and symbol not in self.COINS_TOP20:
            self.dynamic_coins.append(symbol)
            logger.info(f"🆕 Added {symbol} to dynamic pool")
    
    async def _collect_market_data(self, symbol: str) -> MarketData:
        """Собрать ВСЕ данные для анализа включая RSI и EMA"""
        try:
            from app.trading.bybit.client import bybit_client
            from app.ai.whale_ai import whale_ai
            from app.intelligence.news_parser import news_parser
            from app.backtesting.data_loader import BybitDataLoader
            
            pair = f"{symbol}USDT"
            data_loader = BybitDataLoader()
            
            # Параллельные запросы
            price_task = bybit_client.get_price(pair)
            ticker_task = bybit_client.get_ticker_24h(pair)
            whale_task = whale_ai.get_market_metrics(symbol)
            
            results = await asyncio.gather(
                price_task, ticker_task, whale_task,
                return_exceptions=True
            )
            
            current_price = results[0] if not isinstance(results[0], Exception) else 0
            ticker = results[1] if not isinstance(results[1], Exception) else {}
            whale_metrics = results[2] if not isinstance(results[2], Exception) else None
            
            # ═══════════════════════════════════════════════════════════
            # НОВОЕ: Рассчитать RSI и EMA из исторических данных
            # ═══════════════════════════════════════════════════════════
            rsi_14 = 50.0
            ema_21 = 0.0
            ema_50 = 0.0
            macd_hist = 0.0
            atr = 0.0
            
            try:
                # Загрузить свечи
                df = data_loader.load_from_cache(symbol, '5m')
                
                if df is not None and len(df) >= 50:
                    closes = df['close'].values
                    highs = df['high'].values
                    lows = df['low'].values
                    
                    # RSI 14
                    rsi_14 = self._calculate_rsi(closes, 14)
                    
                    # EMA 21 и 50
                    ema_21 = self._calculate_ema(closes, 21)
                    ema_50 = self._calculate_ema(closes, 50)
                    
                    # MACD Histogram
                    macd_hist = self._calculate_macd_histogram(closes)
                    
                    # ATR 14
                    atr = self._calculate_atr(highs, lows, closes, 14)
                    
                    logger.debug(f"📊 {symbol} indicators: RSI={rsi_14:.1f}, EMA21={ema_21:.2f}, EMA50={ema_50:.2f}")
            except Exception as e:
                logger.warning(f"Failed to calculate indicators for {symbol}: {e}")
            
            # ═══════════════════════════════════════════════════════════
            # Получить новости
            # ═══════════════════════════════════════════════════════════
            try:
                news_context = await news_parser.get_market_context()
                news_sentiment = news_context.get('sentiment', 'neutral') if news_context else 'neutral'
            except:
                news_sentiment = 'neutral'
            
            # ═══════════════════════════════════════════════════════════
            # Whale метрики
            # ═══════════════════════════════════════════════════════════
            if whale_metrics:
                funding_rate = getattr(whale_metrics, 'funding_rate', 0) or 0
                long_ratio = getattr(whale_metrics, 'long_ratio', 50) or 50
                short_ratio = getattr(whale_metrics, 'short_ratio', 50) or 50
                fear_greed = getattr(whale_metrics, 'fear_greed_index', 50) or 50
                oi_change = getattr(whale_metrics, 'oi_change_1h', 0) or 0
                liq_long = getattr(whale_metrics, 'liq_long', 0) or 0
                liq_short = getattr(whale_metrics, 'liq_short', 0) or 0
            else:
                funding_rate = 0
                long_ratio = 50
                short_ratio = 50
                fear_greed = 50
                oi_change = 0
                liq_long = 0
                liq_short = 0
            
            # 24h change
            change_24h = 0
            if ticker and isinstance(ticker, dict):
                change_24h = float(ticker.get('price24hPcnt', 0) or 0) * 100
            
            return MarketData(
                symbol=symbol,
                current_price=current_price,
                rsi_14=rsi_14,
                ema_21=ema_21,
                ema_50=ema_50,
                macd_hist=macd_hist,
                atr=atr,
                funding_rate=funding_rate,
                long_ratio=long_ratio,
                short_ratio=short_ratio,
                fear_greed=fear_greed,
                oi_change_1h=oi_change,
                liq_long=liq_long,
                liq_short=liq_short,
                news_sentiment=news_sentiment,
                change_24h=change_24h,
            )
        except Exception as e:
            logger.error(f"Collect market data error for {symbol}: {e}")
            return MarketData(symbol=symbol)
    
    # ═══════════════════════════════════════════════════════════
    # МЕТОДЫ РАСЧЁТА ИНДИКАТОРОВ
    # ═══════════════════════════════════════════════════════════
    
    def _calculate_rsi(self, closes: list, period: int = 14) -> float:
        """Рассчитать RSI"""
        if len(closes) < period + 1:
            return 50.0
        
        deltas = []
        for i in range(1, len(closes)):
            deltas.append(closes[i] - closes[i-1])
        
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def _calculate_ema(self, closes: list, period: int) -> float:
        """Рассчитать EMA"""
        if len(closes) < period:
            return closes[-1] if closes else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(closes[:period]) / period  # SMA для начала
        
        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema
        
        return round(ema, 4)
    
    def _calculate_macd_histogram(self, closes: list) -> float:
        """Рассчитать MACD Histogram"""
        if len(closes) < 26:
            return 0.0
        
        ema_12 = self._calculate_ema(closes, 12)
        ema_26 = self._calculate_ema(closes, 26)
        macd_line = ema_12 - ema_26
        
        # Signal line (EMA 9 от MACD)
        # Упрощённо: используем текущее значение
        signal = macd_line * 0.9  # Приблизительно
        
        histogram = macd_line - signal
        return round(histogram, 4)
    
    def _calculate_atr(self, highs: list, lows: list, closes: list, period: int = 14) -> float:
        """Рассчитать ATR"""
        if len(closes) < period + 1:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(closes)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            true_ranges.append(max(high_low, high_close, low_close))
        
        atr = sum(true_ranges[-period:]) / period
        return round(atr, 4)
    
    def _detect_regime(self, data: MarketData) -> MarketRegime:
        """Определить режим рынка"""
        if data.fear_greed < 30 and data.long_ratio < 40:
            return MarketRegime.ACCUMULATION
        if data.fear_greed > 70 and data.long_ratio > 60:
            return MarketRegime.DISTRIBUTION
        if data.change_24h > 5:
            return MarketRegime.TREND_UP
        if data.change_24h < -5:
            return MarketRegime.TREND_DOWN
        return MarketRegime.RANGE
    
    def _check_restrictions(self, data: MarketData) -> List[str]:
        """Проверить ограничения"""
        restrictions = []
        
        if data.long_ratio > self.THRESHOLDS["long_ratio_max"]:
            restrictions.append(f"NO_LONG: {data.long_ratio:.0f}% в лонгах")
        
        if data.short_ratio > self.THRESHOLDS["short_ratio_max"]:
            restrictions.append(f"NO_SHORT: {data.short_ratio:.0f}% в шортах")
        
        if abs(data.funding_rate) > self.THRESHOLDS["funding_extreme"]:
            if data.funding_rate > 0:
                restrictions.append(f"FUNDING_HIGH: лонги платят {data.funding_rate:.3f}%")
            else:
                restrictions.append(f"FUNDING_LOW: шорты платят {abs(data.funding_rate):.3f}%")
        
        if data.fear_greed < self.THRESHOLDS["fear_extreme_low"]:
            restrictions.append(f"EXTREME_FEAR: F&G={data.fear_greed}")
        
        if data.fear_greed > self.THRESHOLDS["fear_extreme_high"]:
            restrictions.append(f"EXTREME_GREED: F&G={data.fear_greed}")
        
        return restrictions
    
    def _has_critical_restriction(self, restrictions: List[str], data: MarketData) -> bool:
        if data.long_ratio > 75 and data.funding_rate > 0.1:
            return True
        if data.short_ratio > 75 and data.funding_rate < -0.1:
            return True
        return False
    
    def _is_long_allowed(self, restrictions: List[str]) -> bool:
        return not any("NO_LONG" in r for r in restrictions)
    
    def _is_short_allowed(self, restrictions: List[str]) -> bool:
        return not any("NO_SHORT" in r for r in restrictions)
    
    async def _ai_analyze(self, data: MarketData, regime: MarketRegime, restrictions: List[str]) -> BrainDecision:
        """AI анализ"""
        prompt = self._build_prompt(data, regime, restrictions)
        
        try:
            response = await self._call_ai(prompt)
            return self._parse_response(response, data, regime, restrictions)
        except Exception as e:
            logger.error(f"AI analyze error: {e}")
            return BrainDecision(
                action=TradeAction.WAIT,
                symbol=data.symbol,
                confidence=0,
                regime=regime,
                reasoning=f"AI Error: {str(e)}",
                restrictions=restrictions,
                source="brain"
            )
    
    def _build_prompt(self, data: MarketData, regime: MarketRegime, restrictions: List[str]) -> str:
        """Построить промпт для AI с ПОЛНЫМИ данными"""
        restrictions_text = "\n".join([f"  ⛔ {r}" for r in restrictions]) if restrictions else "  ✅ Нет ограничений"
        
        # Определяем тренд по EMA
        if data.ema_21 > 0 and data.ema_50 > 0:
            if data.ema_21 > data.ema_50:
                ema_trend = "📈 БЫЧИЙ (EMA21 > EMA50)"
            elif data.ema_21 < data.ema_50:
                ema_trend = "📉 МЕДВЕЖИЙ (EMA21 < EMA50)"
            else:
                ema_trend = "➡️ Нейтральный"
        else:
            ema_trend = "❓ Нет данных"
        
        # RSI интерпретация
        if data.rsi_14 < 30:
            rsi_signal = "🟢 ПЕРЕПРОДАН — потенциал роста!"
        elif data.rsi_14 > 70:
            rsi_signal = "🔴 ПЕРЕКУПЛЕН — риск падения!"
        elif data.rsi_14 < 40:
            rsi_signal = "🟡 Близко к перепроданности"
        elif data.rsi_14 > 60:
            rsi_signal = "🟡 Близко к перекупленности"
        else:
            rsi_signal = "⚪ Нейтральная зона"
        
        # MACD интерпретация
        if data.macd_hist > 0:
            macd_signal = "📈 Бычий импульс"
        elif data.macd_hist < 0:
            macd_signal = "📉 Медвежий импульс"
        else:
            macd_signal = "➡️ Нейтрально"
        
        return f"""Ты — профессиональный криптотрейдер. Проанализируй данные и прими решение.

## {data.symbol}USDT

═══════════════════════════════════════════════════════════
📊 ЦЕНА И ИЗМЕНЕНИЕ
═══════════════════════════════════════════════════════════
💰 Текущая цена: ${data.current_price:,.4f}
📈 Изменение 24ч: {data.change_24h:+.2f}%

═══════════════════════════════════════════════════════════
📉 ТЕХНИЧЕСКИЕ ИНДИКАТОРЫ
═══════════════════════════════════════════════════════════
• RSI (14): {data.rsi_14:.1f} — {rsi_signal}
• EMA (21): ${data.ema_21:,.4f}
• EMA (50): ${data.ema_50:,.4f}
• Тренд EMA: {ema_trend}
• MACD Histogram: {data.macd_hist:+.4f} — {macd_signal}
• ATR (14): ${data.atr:,.4f}

═══════════════════════════════════════════════════════════
🐋 WHALE / SMART MONEY ДАННЫЕ
═══════════════════════════════════════════════════════════
• Funding Rate: {data.funding_rate:+.4f}%
• Long/Short Ratio: {data.long_ratio:.0f}% / {data.short_ratio:.0f}%
• Fear & Greed Index: {data.fear_greed}
• Open Interest 1h: {data.oi_change_1h:+.2f}%
• Liquidations Long: ${data.liq_long:,.0f}
• Liquidations Short: ${data.liq_short:,.0f}

═══════════════════════════════════════════════════════════
📰 НОВОСТИ И СЕНТИМЕНТ
═══════════════════════════════════════════════════════════
• Новостной сентимент: {data.news_sentiment}

═══════════════════════════════════════════════════════════
🎯 РЕЖИМ РЫНКА: {regime.value.upper()}
═══════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════
⛔ ОГРАНИЧЕНИЯ
═══════════════════════════════════════════════════════════
{restrictions_text}

{"🚫 LONG ЗАПРЕЩЁН — не предлагай LONG!" if not self._is_long_allowed(restrictions) else ""}
{"🚫 SHORT ЗАПРЕЩЁН — не предлагай SHORT!" if not self._is_short_allowed(restrictions) else ""}

═══════════════════════════════════════════════════════════
📋 ПРАВИЛА ПРИНЯТИЯ РЕШЕНИЯ
═══════════════════════════════════════════════════════════
1. RSI < 30 + EMA21 > EMA50 = сильный LONG сигнал
2. RSI > 70 + EMA21 < EMA50 = сильный SHORT сигнал
3. Fear & Greed < 25 = хорошо для LONG (страх = возможность)
4. Fear & Greed > 75 = осторожно с LONG (жадность = риск)
5. Long Ratio > 70% = НЕ открывать LONG (толпа уже в лонгах)
6. Short Ratio > 70% = НЕ открывать SHORT (толпа уже в шортах)
7. ATR используй для расчёта SL/TP

═══════════════════════════════════════════════════════════
🎯 ТВОЁ РЕШЕНИЕ
═══════════════════════════════════════════════════════════
Ответь СТРОГО в формате JSON:

{{"action": "LONG" или "SHORT" или "WAIT", "confidence": число от 0 до 100, "entry_price": число, "stop_loss": число (используй ATR * 1.5 от entry), "take_profit": число (используй ATR * 3 от entry), "reasoning": "краткое объяснение на русском", "key_factors": ["фактор1", "фактор2", "фактор3"]}}

ВАЖНО:
- Если нет чёткого сигнала — выбирай WAIT
- Confidence < 65 = автоматически WAIT
- Не иди против ограничений!
"""
    
    async def _call_ai(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    raise Exception(f"AI API error: {resp.status}")
                result = await resp.json()
                return result['choices'][0]['message']['content']
    
    def _parse_response(self, response: str, data: MarketData, regime: MarketRegime, restrictions: List[str]) -> BrainDecision:
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                raise ValueError("No JSON found")
            
            result = json.loads(json_match.group())
            
            action_str = result.get('action', 'WAIT').upper()
            action = TradeAction[action_str] if action_str in TradeAction.__members__ else TradeAction.WAIT
            
            if action == TradeAction.LONG and not self._is_long_allowed(restrictions):
                action = TradeAction.WAIT
                result['reasoning'] = "LONG запрещён"
            
            if action == TradeAction.SHORT and not self._is_short_allowed(restrictions):
                action = TradeAction.WAIT
                result['reasoning'] = "SHORT запрещён"
            
            confidence = result.get('confidence', 0)
            if confidence < self.MIN_CONFIDENCE:
                action = TradeAction.WAIT
            
            return BrainDecision(
                action=action,
                symbol=data.symbol,
                confidence=confidence,
                entry_price=result.get('entry_price'),
                stop_loss=result.get('stop_loss'),
                take_profit=result.get('take_profit'),
                regime=regime,
                reasoning=result.get('reasoning', ''),
                key_factors=result.get('key_factors', []),
                restrictions=restrictions,
                source="brain"
            )
        except Exception as e:
            logger.error(f"Parse response error: {e}")
            return BrainDecision(
                action=TradeAction.WAIT,
                symbol=data.symbol,
                confidence=0,
                regime=regime,
                reasoning=f"Parse error: {str(e)}",
                restrictions=restrictions,
                source="brain"
            )
    
    def _is_cached(self, symbol: str) -> bool:
        if symbol not in self._cache or symbol not in self._cache_time:
            return False
        age = (datetime.utcnow() - self._cache_time[symbol]).total_seconds()
        return age < self._cache_ttl
    
    def _save_to_cache(self, symbol: str, decision: BrainDecision):
        self._cache[symbol] = decision
        self._cache_time[symbol] = datetime.utcnow()
    
    def clear_cache(self):
        self._cache.clear()
        self._cache_time.clear()
    
    def get_status(self) -> dict:
        """Статус для API"""
        return {
            "name": "Adaptive Brain v3.0",
            "model": self.model,
            "coins_top20": len(self.COINS_TOP20),
            "coins_dynamic": len(self.dynamic_coins),
            "cache_size": len(self._cache),
            "min_confidence": self.MIN_CONFIDENCE,
            "thresholds": self.THRESHOLDS
        }


adaptive_brain = AdaptiveBrain()
