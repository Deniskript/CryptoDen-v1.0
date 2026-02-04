"""
🧠 DirectorBrain — AI который видит рынок как профессиональный трейдер

Собирает ВСЕ данные с Bybit и отправляет в Claude для анализа.
Claude думает как кит-трейдер и принимает решения.
"""

import asyncio
import json
import httpx
import re
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum

from app.core.logger import logger
from app.core.config import settings


class MarketPhase(Enum):
    ACCUMULATION = "accumulation"      # Киты набирают
    DISTRIBUTION = "distribution"      # Киты сливают
    MARKUP = "markup"                  # Рост
    MARKDOWN = "markdown"              # Падение
    RANGING = "ranging"                # Боковик
    UNKNOWN = "unknown"


class ManipulationType(Enum):
    NONE = "none"
    FAKE_BREAKOUT = "fake_breakout"    # Ложный пробой
    STOP_HUNT = "stop_hunt"            # Охота за стопами
    LIQUIDITY_GRAB = "liquidity_grab"  # Сбор ликвидности
    PUMP_AND_DUMP = "pump_and_dump"    # Памп и дамп


@dataclass
class BrainDecision:
    """Решение DirectorBrain"""
    action: str  # "LONG", "SHORT", "WAIT", "CLOSE_LONG", "CLOSE_SHORT"
    symbol: str
    confidence: int  # 0-100
    
    # Параметры сделки
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size_percent: float = 15.0  # % от баланса
    
    # Анализ
    market_phase: MarketPhase = MarketPhase.UNKNOWN
    manipulation_detected: bool = False
    manipulation_type: ManipulationType = ManipulationType.NONE
    direction_1h: str = "sideways"  # up, down, sideways
    
    # AI объяснение
    reasoning: str = ""
    key_factors: List[str] = field(default_factory=list)
    
    # Мета
    timestamp: datetime = field(default_factory=datetime.now)
    raw_ai_response: Dict = field(default_factory=dict)


class DirectorBrain:
    """
    🧠 DirectorBrain — AI который видит рынок как кит
    
    Каждые N минут:
    1. Собирает ВСЕ данные с Bybit
    2. Форматирует для Claude
    3. Claude анализирует как профи-трейдер
    4. Возвращает решение с объяснением
    """
    
    MODEL = "anthropic/claude-haiku-4"  # Haiku 4 для экономии
    
    def __init__(self):
        self.last_analysis: Dict[str, BrainDecision] = {}
        self.analysis_interval = 300  # 5 минут между анализами
        self.last_analysis_time: Dict[str, datetime] = {}
        
        # Статистика
        self.total_analyses = 0
        self.successful_trades = 0
        self.failed_trades = 0
        
        # Настройки
        self.min_confidence_to_trade = 65  # Минимум 65% уверенности
        self.symbols = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK"]
        
        # API key
        self.api_key = settings.openrouter_api_key
        
        logger.info("🧠 DirectorBrain initialized")
    
    async def analyze_symbol(self, symbol: str, force: bool = False) -> BrainDecision:
        """
        Полный анализ одного символа
        
        Args:
            symbol: BTC, ETH, etc.
            force: Игнорировать интервал между анализами
        
        Returns:
            BrainDecision с решением AI
        """
        # Проверяем интервал
        if not force:
            last_time = self.last_analysis_time.get(symbol)
            if last_time and (datetime.now() - last_time).seconds < self.analysis_interval:
                logger.debug(f"Skipping {symbol} analysis, too soon")
                return self.last_analysis.get(symbol, self._empty_decision(symbol))
        
        logger.info(f"🧠 Analyzing {symbol}...")
        
        try:
            # 1. Собираем ВСЕ данные
            market_data = await self._collect_market_data(symbol)
            
            # 2. Форматируем для AI
            prompt = self._build_analysis_prompt(symbol, market_data)
            
            # 3. Отправляем в Claude
            ai_response = await self._call_claude(prompt)
            
            # 4. Парсим ответ
            decision = self._parse_ai_response(symbol, ai_response, market_data)
            
            # 5. Сохраняем
            self.last_analysis[symbol] = decision
            self.last_analysis_time[symbol] = datetime.now()
            self.total_analyses += 1
            
            logger.info(f"🧠 {symbol} analysis: {decision.action} (confidence: {decision.confidence}%)")
            
            return decision
            
        except Exception as e:
            logger.error(f"Brain analysis failed for {symbol}: {e}")
            return self._empty_decision(symbol)
    
    async def analyze_all_symbols(self) -> Dict[str, BrainDecision]:
        """Анализ всех отслеживаемых символов"""
        results = {}
        
        for symbol in self.symbols:
            try:
                decision = await self.analyze_symbol(symbol)
                results[symbol] = decision
                await asyncio.sleep(1)  # Пауза между запросами
            except Exception as e:
                logger.error(f"Failed to analyze {symbol}: {e}")
                results[symbol] = self._empty_decision(symbol)
        
        return results
    
    async def get_best_opportunity(self) -> Optional[BrainDecision]:
        """Найти лучшую возможность для торговли"""
        decisions = await self.analyze_all_symbols()
        
        # Фильтруем только торговые сигналы с высокой уверенностью
        tradeable = [
            d for d in decisions.values()
            if d.action in ["LONG", "SHORT"] and d.confidence >= self.min_confidence_to_trade
        ]
        
        if not tradeable:
            return None
        
        # Возвращаем с максимальной уверенностью
        return max(tradeable, key=lambda x: x.confidence)
    
    async def _collect_market_data(self, symbol: str) -> Dict[str, Any]:
        """Собираем ВСЕ данные с Bybit и других источников"""
        from app.trading.bybit.client import bybit_client
        
        data = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
        }
        
        # 1. Свечи с разных таймфреймов
        try:
            data["candles"] = await bybit_client.get_klines_multi_timeframe(symbol)
        except Exception as e:
            logger.warning(f"Failed to get candles: {e}")
            data["candles"] = {}
        
        # 2. Текущая цена и 24h статистика
        try:
            ticker = await bybit_client.get_ticker_24h(symbol)
            data["current_price"] = ticker.get("price", 0)
            data["change_24h"] = ticker.get("change_24h", 0)
            data["high_24h"] = ticker.get("high_24h", 0)
            data["low_24h"] = ticker.get("low_24h", 0)
            data["volume_24h"] = ticker.get("volume_24h", 0)
        except Exception as e:
            logger.warning(f"Failed to get ticker: {e}")
            data["current_price"] = 0
        
        # 3. Order Book (стакан)
        try:
            data["orderbook"] = await bybit_client.get_orderbook(symbol, limit=25)
        except Exception as e:
            logger.warning(f"Failed to get orderbook: {e}")
            data["orderbook"] = {"bids": [], "asks": []}
        
        # 4. Последние сделки
        try:
            data["recent_trades"] = await bybit_client.get_recent_trades(symbol, limit=50)
        except Exception as e:
            logger.warning(f"Failed to get recent trades: {e}")
            data["recent_trades"] = []
        
        # 5. Whale AI метрики
        try:
            from app.ai.whale_ai import whale_ai
            metrics = whale_ai.last_metrics
            data["whale_metrics"] = {
                "funding_rate": metrics.funding_rate if metrics else 0,
                "long_ratio": metrics.long_ratio if metrics else 50,
                "short_ratio": metrics.short_ratio if metrics else 50,
                "fear_greed": metrics.fear_greed_index if metrics else 50,
                "oi_change_1h": metrics.oi_change_1h if metrics else 0,
                "oi_change_24h": metrics.oi_change_24h if metrics else 0,
                "liquidations_24h_long": metrics.liq_long if metrics else 0,
                "liquidations_24h_short": metrics.liq_short if metrics else 0,
            }
        except Exception as e:
            logger.warning(f"Failed to get whale metrics: {e}")
            data["whale_metrics"] = {
                "funding_rate": 0, "long_ratio": 50, "short_ratio": 50,
                "fear_greed": 50, "oi_change_1h": 0, "oi_change_24h": 0,
                "liquidations_24h_long": 0, "liquidations_24h_short": 0
            }
        
        # 6. Новости
        try:
            from app.intelligence.news_parser import news_parser
            news_context = await news_parser.get_market_context()
            data["news"] = {
                "market_mode": news_context.get("market_mode", "NORMAL"),
                "sentiment": news_context.get("overall_sentiment", "neutral"),
                "important_news": news_context.get("news", [])[:5]
            }
        except Exception as e:
            logger.warning(f"Failed to get news: {e}")
            data["news"] = {"market_mode": "NORMAL", "sentiment": "neutral", "important_news": []}
        
        return data
    
    def _build_analysis_prompt(self, symbol: str, data: Dict) -> str:
        """Строим промпт для Claude"""
        
        # Форматируем свечи
        candles_text = self._format_candles(data.get("candles", {}))
        
        # Форматируем стакан
        orderbook_text = self._format_orderbook(data.get("orderbook", {}))
        
        # Форматируем сделки
        trades_text = self._format_trades(data.get("recent_trades", []))
        
        # Whale метрики
        whale = data.get("whale_metrics", {})
        
        # Новости
        news = data.get("news", {})
        
        prompt = f"""Ты — профессиональный трейдер-кит с 20-летним опытом на крипторынке.
Ты умеешь видеть манипуляции маркет-мейкеров, понимаешь психологию толпы, и знаешь как киты двигают рынок.

Твоя задача — проанализировать текущую ситуацию на {symbol} и принять решение.

═══════════════════════════════════════════════════════════════
📊 ТЕКУЩАЯ ЦЕНА: ${data.get('current_price', 0):,.2f}
📈 Изменение 24h: {data.get('change_24h', 0):+.2f}%
🔼 High 24h: ${data.get('high_24h', 0):,.2f}
🔽 Low 24h: ${data.get('low_24h', 0):,.2f}
📊 Volume 24h: ${data.get('volume_24h', 0):,.0f}
═══════════════════════════════════════════════════════════════

📈 СВЕЧИ (мультитаймфрейм):
{candles_text}

═══════════════════════════════════════════════════════════════

📋 ORDER BOOK (стакан):
{orderbook_text}

═══════════════════════════════════════════════════════════════

💹 ПОСЛЕДНИЕ КРУПНЫЕ СДЕЛКИ:
{trades_text}

═══════════════════════════════════════════════════════════════

🐋 WHALE МЕТРИКИ:
• Funding Rate: {whale.get('funding_rate', 0):.4f}% {'(лонги платят)' if whale.get('funding_rate', 0) > 0 else '(шорты платят)' if whale.get('funding_rate', 0) < 0 else ''}
• Long/Short Ratio: {whale.get('long_ratio', 50):.1f}% / {whale.get('short_ratio', 50):.1f}%
• Fear & Greed Index: {whale.get('fear_greed', 50)} {'(страх)' if whale.get('fear_greed', 50) < 40 else '(жадность)' if whale.get('fear_greed', 50) > 60 else '(нейтрально)'}
• OI Change 1h: {whale.get('oi_change_1h', 0):+.2f}%
• OI Change 24h: {whale.get('oi_change_24h', 0):+.2f}%
• Ликвидации 24h: Long ${whale.get('liquidations_24h_long', 0)/1e6:.1f}M | Short ${whale.get('liquidations_24h_short', 0)/1e6:.1f}M

═══════════════════════════════════════════════════════════════

📰 НОВОСТИ И НАСТРОЕНИЕ:
• Режим рынка: {news.get('market_mode', 'NORMAL')}
• Общий sentiment: {news.get('sentiment', 'neutral')}

═══════════════════════════════════════════════════════════════

🎯 ТВОИ ЗАДАЧИ:

1. ОПРЕДЕЛИ фазу рынка:
   - accumulation (киты набирают позицию)
   - distribution (киты сливают)
   - markup (активный рост)
   - markdown (активное падение)
   - ranging (боковик)

2. ОПРЕДЕЛИ есть ли манипуляция:
   - fake_breakout (ложный пробой)
   - stop_hunt (охота за стопами)
   - liquidity_grab (сбор ликвидности)
   - none (нет манипуляции)

3. ОПРЕДЕЛИ кто контролирует рынок:
   - buyers (покупатели давят)
   - sellers (продавцы давят)
   - neutral (равновесие)

4. ПРИМИ РЕШЕНИЕ:
   - LONG (открыть длинную позицию)
   - SHORT (открыть короткую позицию)
   - WAIT (ждать лучший момент)

5. Если решение LONG или SHORT, укажи:
   - entry_price (цена входа)
   - stop_loss (где ставить стоп)
   - take_profit (где забирать прибыль)
   - confidence (уверенность 0-100%)

═══════════════════════════════════════════════════════════════

⚠️ ВАЖНЫЕ ПРАВИЛА:
- Не торгуй против сильного тренда
- Ищи точки где толпа будет ликвидирована
- Входи после манипуляций, не во время
- Уверенность < 60% = WAIT
- Long/Short ratio > 65% = осторожно с лонгами (толпа уже там)
- Long/Short ratio < 35% = осторожно с шортами (толпа уже там)
- После сбора ликвидности обычно разворот

═══════════════════════════════════════════════════════════════

Ответь СТРОГО в формате JSON:
```json
{{
    "market_phase": "accumulation|distribution|markup|markdown|ranging",
    "manipulation_detected": true|false,
    "manipulation_type": "fake_breakout|stop_hunt|liquidity_grab|none",
    "market_control": "buyers|sellers|neutral",
    "direction_1h": "up|down|sideways",
    "action": "LONG|SHORT|WAIT",
    "confidence": 0-100,
    "entry_price": число или null,
    "stop_loss": число или null,
    "take_profit": число или null,
    "reasoning": "Подробное объяснение на русском почему принял это решение",
    "key_factors": ["фактор1", "фактор2", "фактор3"]
}}
```

Думай как кит. Где боль толпы — там твоя прибыль."""

        return prompt

    def _format_candles(self, candles: Dict) -> str:
        """Форматируем свечи для промпта"""
        result = []
        
        for tf, data in candles.items():
            if not data:
                continue
            
            result.append(f"\n{tf.upper()}:")
            
            # Последние 10 свечей
            recent = data[-10:] if len(data) > 10 else data
            
            for candle in recent:
                if isinstance(candle, dict):
                    o = candle.get('open', 0)
                    h = candle.get('high', 0)
                    l = candle.get('low', 0)
                    c = candle.get('close', 0)
                    vol = candle.get('volume', 0)
                elif isinstance(candle, (list, tuple)) and len(candle) >= 5:
                    o, h, l, c = float(candle[1]), float(candle[2]), float(candle[3]), float(candle[4])
                    vol = float(candle[5]) if len(candle) > 5 else 0
                else:
                    continue
                
                change = ((c - o) / o * 100) if o > 0 else 0
                direction = "🟢" if c >= o else "🔴"
                result.append(f"  {direction} O:{o:.0f} H:{h:.0f} L:{l:.0f} C:{c:.0f} ({change:+.2f}%) Vol:{vol:.0f}")
        
        return "\n".join(result) if result else "Нет данных"

    def _format_orderbook(self, orderbook: Dict) -> str:
        """Форматируем стакан для промпта"""
        result = []
        
        bids = orderbook.get("bids", [])[:10]
        asks = orderbook.get("asks", [])[:10]
        
        # Считаем суммарный объём
        total_bids = sum(b[1] for b in bids) if bids else 0
        total_asks = sum(a[1] for a in asks) if asks else 0
        
        result.append(f"Суммарно BUY: {total_bids:,.4f} | SELL: {total_asks:,.4f}")
        
        imbalance = (total_bids / (total_bids + total_asks) * 100) if (total_bids + total_asks) > 0 else 50
        result.append(f"Дисбаланс: {imbalance:.0f}% в сторону {'покупателей' if imbalance > 50 else 'продавцов'}")
        
        # Большие стены
        if bids:
            avg_bid = total_bids / len(bids)
            big_bids = [b for b in bids if b[1] > avg_bid * 2]
            if big_bids:
                result.append(f"🟢 Большие BUY стены: {', '.join([f'${b[0]:,.0f} ({b[1]:,.4f})' for b in big_bids[:3]])}")
        
        if asks:
            avg_ask = total_asks / len(asks)
            big_asks = [a for a in asks if a[1] > avg_ask * 2]
            if big_asks:
                result.append(f"🔴 Большие SELL стены: {', '.join([f'${a[0]:,.0f} ({a[1]:,.4f})' for a in big_asks[:3]])}")
        
        return "\n".join(result) if result else "Нет данных"

    def _format_trades(self, trades: List[Dict]) -> str:
        """Форматируем последние сделки"""
        if not trades:
            return "Нет данных"
        
        buys = [t for t in trades if t.get("side") == "Buy"]
        sells = [t for t in trades if t.get("side") == "Sell"]
        
        buy_volume = sum(t.get("qty", 0) * t.get("price", 0) for t in buys)
        sell_volume = sum(t.get("qty", 0) * t.get("price", 0) for t in sells)
        
        big_trades = [t for t in trades if t.get("qty", 0) * t.get("price", 0) > 10000]
        
        result = [
            f"Всего: {len(buys)} покупок (${buy_volume:,.0f}) | {len(sells)} продаж (${sell_volume:,.0f})",
        ]
        
        if buy_volume + sell_volume > 0:
            aggression = "покупатели" if buy_volume > sell_volume else "продавцы"
            diff_pct = abs(buy_volume - sell_volume) / max(buy_volume, sell_volume, 1) * 100
            result.append(f"Агрессия: {aggression} ({diff_pct:.0f}% перевес)")
        
        if big_trades:
            result.append(f"Крупные сделки (>$10k): {len(big_trades)}")
        
        return "\n".join(result)

    async def _call_claude(self, prompt: str) -> Dict:
        """Отправляем в Claude и получаем ответ"""
        
        if not self.api_key:
            logger.error("🧠 DirectorBrain: No OpenRouter API key!")
            return {}
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://cryptoden.ru",
                        "X-Title": "CryptoDen Trading Bot"
                    },
                    json={
                        "model": self.MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,  # Низкая температура для стабильности
                        "max_tokens": 2000,
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    # Логируем токены
                    usage = result.get("usage", {})
                    logger.debug(f"🧠 Brain tokens used: {usage.get('total_tokens', 0)}")
                    
                    # Извлекаем JSON из ответа
                    json_match = re.search(r'\{[\s\S]*\}', content)
                    if json_match:
                        return json.loads(json_match.group())
                    else:
                        logger.warning(f"No JSON found in AI response: {content[:200]}")
                        return {}
                else:
                    error_text = response.text
                    logger.error(f"🧠 Claude API error {response.status_code}: {error_text[:200]}")
                    return {}
                    
        except Exception as e:
            logger.error(f"🧠 Claude API error: {e}")
            return {}

    def _parse_ai_response(self, symbol: str, ai_response: Dict, market_data: Dict) -> BrainDecision:
        """Парсим ответ AI в BrainDecision"""
        
        if not ai_response:
            return self._empty_decision(symbol)
        
        try:
            # Парсим market_phase
            try:
                market_phase = MarketPhase(ai_response.get("market_phase", "unknown"))
            except ValueError:
                market_phase = MarketPhase.UNKNOWN
            
            # Парсим manipulation_type
            try:
                manipulation_type = ManipulationType(ai_response.get("manipulation_type", "none"))
            except ValueError:
                manipulation_type = ManipulationType.NONE
            
            return BrainDecision(
                action=ai_response.get("action", "WAIT"),
                symbol=symbol,
                confidence=int(ai_response.get("confidence", 0)),
                entry_price=ai_response.get("entry_price"),
                stop_loss=ai_response.get("stop_loss"),
                take_profit=ai_response.get("take_profit"),
                market_phase=market_phase,
                manipulation_detected=ai_response.get("manipulation_detected", False),
                manipulation_type=manipulation_type,
                direction_1h=ai_response.get("direction_1h", "sideways"),
                reasoning=ai_response.get("reasoning", ""),
                key_factors=ai_response.get("key_factors", []),
                raw_ai_response=ai_response
            )
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            return self._empty_decision(symbol)

    def _empty_decision(self, symbol: str) -> BrainDecision:
        """Пустое решение (WAIT)"""
        return BrainDecision(
            action="WAIT",
            symbol=symbol,
            confidence=0,
            reasoning="Недостаточно данных для анализа"
        )

    def get_status(self) -> Dict:
        """Статус DirectorBrain для API"""
        return {
            "total_analyses": self.total_analyses,
            "symbols": self.symbols,
            "min_confidence": self.min_confidence_to_trade,
            "model": self.MODEL,
            "last_analyses": {
                symbol: {
                    "action": d.action,
                    "confidence": d.confidence,
                    "market_phase": d.market_phase.value,
                    "reasoning": d.reasoning[:100] + "..." if len(d.reasoning) > 100 else d.reasoning
                }
                for symbol, d in self.last_analysis.items()
            }
        }

    def get_status_text(self) -> str:
        """Текст статуса для Telegram"""
        lines = [
            "🧠 *DirectorBrain Status*",
            f"📊 Всего анализов: {self.total_analyses}",
            f"🎯 Мин. уверенность: {self.min_confidence_to_trade}%",
            f"📈 Отслеживаю: {', '.join(self.symbols)}",
            f"🤖 Модель: `{self.MODEL}`",
            ""
        ]
        
        if self.last_analysis:
            lines.append("*Последние анализы:*")
            for symbol, decision in self.last_analysis.items():
                emoji = "🟢" if decision.action == "LONG" else "🔴" if decision.action == "SHORT" else "⏸"
                lines.append(f"{emoji} {symbol}: {decision.action} ({decision.confidence}%)")
                if decision.market_phase != MarketPhase.UNKNOWN:
                    lines.append(f"   └ Фаза: {decision.market_phase.value}")
        else:
            lines.append("_Ещё нет анализов_")
        
        return "\n".join(lines)

    def format_decision_notification(self, decision: BrainDecision) -> str:
        """Форматировать уведомление о решении для Telegram"""
        if decision.action == "WAIT":
            return ""
        
        emoji = "🟢" if decision.action == "LONG" else "🔴"
        manip_text = f"⚠️ {decision.manipulation_type.value}" if decision.manipulation_detected else "❌ Нет"
        
        lines = [
            f"🧠 *DirectorBrain Signal*",
            "",
            f"{emoji} *{decision.action} {decision.symbol}*",
            f"📊 Уверенность: {decision.confidence}%",
            "",
            f"💰 Entry: ${decision.entry_price:,.2f}" if decision.entry_price else "",
            f"🛑 Stop Loss: ${decision.stop_loss:,.2f}" if decision.stop_loss else "",
            f"🎯 Take Profit: ${decision.take_profit:,.2f}" if decision.take_profit else "",
            "",
            f"*Фаза рынка:* {decision.market_phase.value}",
            f"*Направление 1h:* {decision.direction_1h}",
            f"*Манипуляция:* {manip_text}",
            "",
            f"*Анализ AI:*",
            f"_{decision.reasoning[:300]}{'...' if len(decision.reasoning) > 300 else ''}_",
            "",
            "*Ключевые факторы:*",
        ]
        
        for factor in decision.key_factors[:5]:
            lines.append(f"• {factor}")
        
        return "\n".join([l for l in lines if l is not None])


# Синглтон
director_brain = DirectorBrain()
