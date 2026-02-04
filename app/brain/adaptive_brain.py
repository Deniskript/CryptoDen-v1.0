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
        self.model = "anthropic/claude-3-haiku-20240307"
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        logger.info("🧠 Adaptive Brain v3.0 initialized")
    
    async def analyze(self, symbol: str) -> BrainDecision:
        """Главный метод анализа"""
        try:
            if self._is_cached(symbol):
                return self._cache[symbol]
            
            market_data = await self._collect_market_data(symbol)
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
        """Найти лучшую возможность"""
        all_coins = self.COINS_TOP20 + self.dynamic_coins
        decisions = []
        
        for symbol in all_coins[:10]:  # Топ-10 для скорости
            try:
                decision = await self.analyze(symbol)
                if decision.action in [TradeAction.LONG, TradeAction.SHORT]:
                    if decision.confidence >= self.MIN_CONFIDENCE:
                        decisions.append(decision)
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
                continue
        
        if not decisions:
            return None
        
        decisions.sort(key=lambda x: x.confidence, reverse=True)
        return decisions[0]
    
    def add_dynamic_coin(self, symbol: str):
        if symbol not in self.dynamic_coins and symbol not in self.COINS_TOP20:
            self.dynamic_coins.append(symbol)
            logger.info(f"🆕 Added {symbol} to dynamic pool")
    
    async def _collect_market_data(self, symbol: str) -> MarketData:
        """Собрать данные для анализа"""
        try:
            from app.trading.bybit.client import bybit_client
            from app.ai.whale_ai import whale_ai
            from app.intelligence.news_parser import news_parser
            
            pair = f"{symbol}USDT"
            
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
            
            # Получить новости
            try:
                news_context = await news_parser.get_market_context()
                news_sentiment = news_context.get('sentiment', 'neutral') if news_context else 'neutral'
            except:
                news_sentiment = 'neutral'
            
            # Whale метрики - ИСПРАВЛЕНО!
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
            
            change_24h = 0
            if ticker and isinstance(ticker, dict):
                change_24h = float(ticker.get('price24hPcnt', 0) or 0) * 100
            
            return MarketData(
                symbol=symbol,
                current_price=current_price,
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
            logger.error(f"Collect market data error: {e}")
            return MarketData(symbol=symbol)
    
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
        restrictions_text = "\n".join([f"  ⛔ {r}" for r in restrictions]) if restrictions else "  ✅ Нет ограничений"
        
        return f"""Ты — криптотрейдер. Проанализируй и прими решение.

## {data.symbol}USDT

💰 Цена: ${data.current_price:,.2f} ({data.change_24h:+.2f}% 24h)

🐋 Whale метрики:
• Funding: {data.funding_rate:+.4f}%
• Long/Short: {data.long_ratio:.0f}% / {data.short_ratio:.0f}%
• Fear & Greed: {data.fear_greed}
• OI Change 1h: {data.oi_change_1h:+.2f}%

📰 Новости: {data.news_sentiment}
🎯 Режим рынка: {regime.value}

⛔ Ограничения:
{restrictions_text}

{"⚠️ LONG ЗАПРЕЩЁН!" if not self._is_long_allowed(restrictions) else ""}
{"⚠️ SHORT ЗАПРЕЩЁН!" if not self._is_short_allowed(restrictions) else ""}

Ответь JSON:
{{"action": "LONG/SHORT/WAIT", "confidence": 0-100, "entry_price": число, "stop_loss": число, "take_profit": число, "reasoning": "причина", "key_factors": ["фактор1", "фактор2"]}}
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
