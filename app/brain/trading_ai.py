"""
Trading AI — Мозг системы (Sonnet 4.5)

Функции:
- Анализирует новости + график + стратегию
- Принимает решения: OPEN/CLOSE/ADJUST/WAIT
- Динамически двигает SL/TP
- Ловит тренды по новостям
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from enum import Enum
import json
import re

import aiohttp

from app.core.config import settings
from app.core.logger import logger


class AIAction(Enum):
    WAIT = "wait"           # Ждать
    OPEN_LONG = "open_long" # Открыть лонг
    OPEN_SHORT = "open_short" # Открыть шорт
    CLOSE = "close"         # Закрыть позицию
    ADJUST_SL = "adjust_sl" # Подвинуть стоп-лосс
    ADJUST_TP = "adjust_tp" # Подвинуть тейк-профит
    HOLD = "hold"           # Держать позицию


@dataclass
class AIDecision:
    """Решение AI"""
    action: AIAction
    symbol: str
    confidence: float  # 0-100
    
    # Для открытия
    direction: Optional[str] = None  # LONG/SHORT
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    size_multiplier: float = 1.0  # 0.5x, 1x, 1.5x
    
    # Для корректировки
    new_sl: Optional[float] = None
    new_tp: Optional[float] = None
    
    # Причина
    reason: str = ""
    news_influence: str = ""  # Какая новость повлияла
    
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "symbol": self.symbol,
            "confidence": self.confidence,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "size_multiplier": self.size_multiplier,
            "new_sl": self.new_sl,
            "new_tp": self.new_tp,
            "reason": self.reason,
            "news_influence": self.news_influence,
            "timestamp": self.timestamp.isoformat()
        }


class TradingAI:
    """
    Trading AI на Sonnet 4.5
    
    Логика:
    1. Получает: новости + календарь + стратегию + график + позицию
    2. Анализирует ВСЁ вместе
    3. Выдаёт решение с SL/TP
    4. Каждые 30 сек пересматривает открытые позиции
    """
    
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "anthropic/claude-sonnet-4"  # Sonnet 4.5
    
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.model = settings.ai_model  # Берём из настроек
        self.decisions_history: List[AIDecision] = []
        self.session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"TradingAI initialized (model: {self.model})")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def analyze(
        self,
        symbol: str,
        market_context: dict,      # От NewsParser
        strategy_signal: dict,      # От StrategyChecker (или None)
        current_position: dict,     # Текущая позиция (или None)
        price_data: dict,           # OHLCV последние свечи
        current_price: float
    ) -> AIDecision:
        """
        Главный метод — анализ и решение
        """
        
        if not self.api_key:
            logger.warning("OpenRouter API key not configured")
            return AIDecision(
                action=AIAction.WAIT,
                symbol=symbol,
                confidence=0,
                reason="API key not configured"
            )
        
        prompt = self._build_prompt(
            symbol=symbol,
            market_context=market_context,
            strategy_signal=strategy_signal,
            current_position=current_position,
            price_data=price_data,
            current_price=current_price
        )
        
        response = await self._call_ai(prompt)
        decision = self._parse_response(response, symbol, current_price)
        
        self.decisions_history.append(decision)
        
        # Ограничиваем историю
        if len(self.decisions_history) > 100:
            self.decisions_history = self.decisions_history[-50:]
        
        logger.info(f"🧠 AI Decision for {symbol}: {decision.action.value}")
        logger.info(f"   Confidence: {decision.confidence}%")
        logger.info(f"   Reason: {decision.reason}")
        
        return decision
    
    def _build_prompt(
        self,
        symbol: str,
        market_context: dict,
        strategy_signal: dict,
        current_position: dict,
        price_data: dict,
        current_price: float
    ) -> str:
        """Построить промпт для AI"""
        
        # Новости
        news_text = ""
        for n in market_context.get("news", [])[:5]:
            sentiment = "🟢" if n.get("sentiment", 0) > 0 else "🔴" if n.get("sentiment", 0) < 0 else "⚪"
            news_text += f"{sentiment} {n.get('title', '')} (importance: {n.get('importance', 'LOW')})\n"
        
        # Календарь
        calendar_text = ""
        for e in market_context.get("calendar", []):
            calendar_text += f"⏰ {e.get('event', '')} at {e.get('time', '')} ({e.get('importance', '')})\n"
        
        # Стратегия
        if strategy_signal:
            strategy_text = (
                f"Signal: {strategy_signal.get('direction', 'NONE')}\n"
                f"Strategy: {strategy_signal.get('strategy_name', '')}\n"
                f"Win Rate: {strategy_signal.get('win_rate', 0)}%\n"
                f"Entry: ${strategy_signal.get('entry_price', 0)}\n"
                f"SL: ${strategy_signal.get('stop_loss', 0)}\n"
                f"TP: ${strategy_signal.get('take_profit', 0)}"
            )
        else:
            strategy_text = "No signal"
        
        # Позиция
        if current_position:
            position_text = (
                f"Direction: {current_position.get('direction', '')}\n"
                f"Entry: ${current_position.get('entry_price', 0)}\n"
                f"Current P&L: {current_position.get('pnl_percent', 0):+.2f}%\n"
                f"Current SL: ${current_position.get('stop_loss', 0)}\n"
                f"Current TP: ${current_position.get('take_profit', 0)}"
            )
        else:
            position_text = "No position"
        
        # Ценовые данные
        candles_text = ""
        recent_candles = price_data.get('recent_candles', [])[-5:]
        if recent_candles:
            candles_text = json.dumps(recent_candles, indent=2)
        
        prompt = f"""You are a professional crypto trader AI. Analyze the market and make a trading decision.

## CURRENT SITUATION

**Symbol:** {symbol}
**Current Price:** ${current_price:,.2f}
**Market Mode:** {market_context.get('market_mode', 'NORMAL')}

## RECENT NEWS (last hour)
{news_text if news_text else "No significant news"}

## ECONOMIC CALENDAR
{calendar_text if calendar_text else "No upcoming events"}

## TECHNICAL STRATEGY SIGNAL
{strategy_text}

## CURRENT POSITION
{position_text}

## YOUR TASK

Analyze ALL inputs and decide:

1. **If NO position open:**
   - Should I OPEN a trade? (consider news + strategy + calendar)
   - If news is moving the market NOW — catch the trend!
   - If important event in < 1 hour — be careful
   - If strategy + news align — stronger signal

2. **If position IS open:**
   - Should I HOLD, CLOSE, or ADJUST SL/TP?
   - Move SL to lock profits if price moved in my favor
   - Move TP if trend is strong (let profits run)
   - Close if news changed sentiment against my position

## RESPONSE FORMAT (JSON only!)

Return ONLY a JSON object with these fields:
{{
    "action": "wait|open_long|open_short|close|adjust_sl|adjust_tp|hold",
    "confidence": 0-100,
    "direction": "LONG|SHORT|null",
    "stop_loss": price_or_null,
    "take_profit": price_or_null,
    "new_sl": price_or_null,
    "new_tp": price_or_null,
    "size_multiplier": 0.5|1.0|1.5,
    "reason": "Brief explanation",
    "news_influence": "Which news affected decision or 'none'"
}}

IMPORTANT:
- Be decisive, not hesitant
- News that moves price = opportunity to catch trend
- Protect profits by moving SL
- size_multiplier: 1.5 if strategy + news align, 0.5 if uncertain, 1.0 normal
- Respond with JSON only, no other text!"""

        return prompt
    
    async def _call_ai(self, prompt: str) -> dict:
        """Вызов OpenRouter API"""
        
        await self._ensure_session()
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cryptoden.ru",
            "X-Title": "CryptoDen Trading Bot"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,  # Более детерминированные ответы
            "max_tokens": 500
        }
        
        try:
            async with self.session.post(
                self.OPENROUTER_URL,
                headers=headers,
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Логируем использование токенов
                    usage = data.get("usage", {})
                    logger.debug(f"AI tokens: {usage.get('total_tokens', 0)}")
                    
                    # Парсим JSON из ответа
                    json_match = re.search(r'\{[\s\S]*\}', content)
                    if json_match:
                        return json.loads(json_match.group())
                    
                    logger.error(f"No JSON in response: {content[:200]}")
                    return {}
                else:
                    error = await resp.text()
                    logger.error(f"OpenRouter error {resp.status}: {error[:200]}")
                    return {}
                    
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {}
        except Exception as e:
            logger.error(f"AI call error: {e}")
            return {}
    
    def _parse_response(
        self,
        response: dict,
        symbol: str,
        current_price: float
    ) -> AIDecision:
        """Парсинг ответа AI в AIDecision"""
        
        if not response:
            return AIDecision(
                action=AIAction.WAIT,
                symbol=symbol,
                confidence=0,
                reason="AI call failed"
            )
        
        action_map = {
            "wait": AIAction.WAIT,
            "open_long": AIAction.OPEN_LONG,
            "open_short": AIAction.OPEN_SHORT,
            "close": AIAction.CLOSE,
            "adjust_sl": AIAction.ADJUST_SL,
            "adjust_tp": AIAction.ADJUST_TP,
            "hold": AIAction.HOLD,
        }
        
        action_str = response.get("action", "wait").lower()
        action = action_map.get(action_str, AIAction.WAIT)
        
        return AIDecision(
            action=action,
            symbol=symbol,
            confidence=response.get("confidence", 0),
            direction=response.get("direction"),
            entry_price=current_price if action in [AIAction.OPEN_LONG, AIAction.OPEN_SHORT] else None,
            stop_loss=response.get("stop_loss"),
            take_profit=response.get("take_profit"),
            size_multiplier=response.get("size_multiplier", 1.0),
            new_sl=response.get("new_sl"),
            new_tp=response.get("new_tp"),
            reason=response.get("reason", ""),
            news_influence=response.get("news_influence", "")
        )
    
    async def should_adjust_position(
        self,
        symbol: str,
        position: dict,
        market_context: dict,
        current_price: float
    ) -> AIDecision:
        """
        Проверка открытой позиции — нужно ли двигать SL/TP?
        Вызывается каждые 30 сек для активных позиций
        """
        
        return await self.analyze(
            symbol=symbol,
            market_context=market_context,
            strategy_signal=None,  # Нет нового сигнала
            current_position=position,
            price_data={"recent_candles": []},
            current_price=current_price
        )
    
    def get_recent_decisions(self, limit: int = 10) -> List[dict]:
        """Получить последние решения"""
        return [d.to_dict() for d in self.decisions_history[-limit:]]


# Глобальный экземпляр
trading_ai = TradingAI()
