"""
Haiku Explainer — AI объяснения для живых уведомлений
Использует Claude 3 Haiku через OpenRouter (~$1/месяц)
"""
import asyncio
import aiohttp
from typing import Optional, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.core.config import settings
from app.core.logger import logger


@dataclass
class ExplainRequest:
    """Запрос на объяснение"""
    type: str  # news, signal, no_signal, listing, whale
    data: Dict
    timestamp: datetime = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now()


class HaikuExplainer:
    """
    AI объяснения через Claude 3 Haiku
    
    Дешёвая модель для постоянных объяснений в чате
    """
    
    MODEL = "anthropic/claude-3.5-haiku"  # OpenRouter формат
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    # Системные промпты для разных типов (ВСЁ НА РУССКОМ)
    PROMPTS = {
        "news": """Ты крипто-аналитик. Объясни новость кратко (3-4 предложения):
1. Что произошло простыми словами
2. Как это повлияет на Биткоин и крипторынок
3. Что делать трейдеру сейчас

Пиши на русском языке. Просто и понятно. Без сложных терминов.""",

        "signal": """Ты крипто-аналитик. Объясни почему появился сигнал (3-4 предложения):
1. Почему сейчас хорошая точка входа
2. Какие риски нужно учитывать
3. Насколько уверен в сигнале (в процентах)

Пиши на русском языке. Просто и понятно.""",

        "no_signal": """Ты крипто-аналитик. Объясни почему сейчас НЕТ точки входа (3-4 предложения):
1. Что сейчас происходит на рынке
2. Чего ждём для хорошего входа
3. Примерно когда может появиться сигнал

Пиши на русском языке. Кратко и по делу.""",

        "listing": """Ты крипто-аналитик. Оцени новый листинг монеты (3-4 предложения):
1. Что это за проект если знаешь
2. Стоит ли покупать и почему
3. Какие риски у этой монеты

Пиши на русском языке. Честно предупреди о рисках.""",

        "whale": """Ты крипто-аналитик. Объясни движение крупных игроков (2-3 предложения):
1. Что означает это движение
2. Как может повлиять на цену
3. Что делать трейдеру

Пиши на русском языке. Кратко.""",

        "market_status": """Ты крипто-аналитик. Дай краткий обзор рынка (3-4 предложения):
1. Общее настроение рынка сейчас
2. На что обратить внимание
3. Что ожидать в ближайшие часы

Пиши на русском языке. Просто и без воды.""",

        "funding": """Ты крипто-аналитик. Объясни ситуацию со ставками финансирования (2-3 предложения):
1. Что означает текущая ставка
2. Как на этом можно заработать
3. Какие риски есть

Пиши на русском языке. Понятно для новичка.""",
    }
    
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.enabled = bool(self.api_key)
        
        # Кэш ответов (не спрашивать дважды похожее)
        self.cache: Dict[str, tuple] = {}  # key -> (response, timestamp)
        self.cache_ttl = timedelta(hours=1)
        
        # Rate limiting
        self.requests_this_hour = 0
        self.hour_start = datetime.now()
        self.max_requests_per_hour = 60  # ~$0.02/час максимум
        
        # Статистика
        self.total_requests = 0
        self.total_tokens = 0
        
        if self.enabled:
            logger.info("🧠 HaikuExplainer initialized")
        else:
            logger.warning("⚠️ HaikuExplainer disabled (no API key)")
    
    def _get_cache_key(self, type: str, data: Dict) -> str:
        """Создать ключ кэша"""
        # Для новостей — по заголовку
        if type == "news":
            return f"news:{data.get('title', '')[:50]}"
        # Для сигналов — по символу и направлению
        elif type == "signal":
            return f"signal:{data.get('symbol')}:{data.get('direction')}"
        # Для no_signal — по символу и RSI (округлённо)
        elif type == "no_signal":
            rsi = int(data.get('rsi', 50) / 5) * 5  # Округляем до 5
            return f"no_signal:{data.get('symbol')}:{rsi}"
        else:
            return f"{type}:{hash(str(data)) % 10000}"
    
    def _check_cache(self, key: str) -> Optional[str]:
        """Проверить кэш"""
        if key in self.cache:
            response, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.cache_ttl:
                logger.debug(f"🧠 Cache hit: {key}")
                return response
            else:
                del self.cache[key]
        return None
    
    def _check_rate_limit(self) -> bool:
        """Проверить лимит запросов"""
        now = datetime.now()
        
        # Сбросить счётчик каждый час
        if now - self.hour_start > timedelta(hours=1):
            self.requests_this_hour = 0
            self.hour_start = now
        
        return self.requests_this_hour < self.max_requests_per_hour
    
    async def explain(self, request: ExplainRequest) -> Optional[str]:
        """
        Получить AI объяснение
        
        Returns:
            str: Объяснение или None если ошибка/лимит
        """
        if not self.enabled:
            return None
        
        # Проверяем кэш
        cache_key = self._get_cache_key(request.type, request.data)
        cached = self._check_cache(cache_key)
        if cached:
            return cached
        
        # Проверяем лимит
        if not self._check_rate_limit():
            logger.warning("🧠 Haiku rate limit reached")
            return None
        
        # Получаем промпт
        system_prompt = self.PROMPTS.get(request.type)
        if not system_prompt:
            logger.error(f"Unknown explain type: {request.type}")
            return None
        
        # Формируем user prompt
        user_prompt = self._format_user_prompt(request)
        
        try:
            response = await self._call_api(system_prompt, user_prompt)
            
            if response:
                # Сохраняем в кэш
                self.cache[cache_key] = (response, datetime.now())
                self.requests_this_hour += 1
                self.total_requests += 1
                
            return response
            
        except Exception as e:
            logger.error(f"Haiku explain error: {e}")
            return None
    
    def _format_user_prompt(self, request: ExplainRequest) -> str:
        """Форматировать user prompt"""
        data = request.data
        
        if request.type == "news":
            return f"""Новость: "{data.get('title', '')}"
Источник: {data.get('source', 'Unknown')}
Sentiment: {data.get('sentiment', 0):.2f}"""
        
        elif request.type == "signal":
            return f"""Сигнал: {data.get('direction')} {data.get('symbol')}
Цена входа: ${data.get('entry', 0):,.2f}
RSI: {data.get('rsi', 50):.0f}
Стратегия: {data.get('strategy', 'Unknown')}
Win Rate: {data.get('win_rate', 0):.0f}%"""
        
        elif request.type == "no_signal":
            return f"""Монета: {data.get('symbol')}
Текущая цена: ${data.get('price', 0):,.2f}
RSI: {data.get('rsi', 50):.0f}
Fear & Greed: {data.get('fear_greed', 50)}
Тренд: {data.get('trend', 'неопределён')}"""
        
        elif request.type == "listing":
            return f"""Новый листинг: {data.get('name')} ({data.get('symbol')})
Биржа: {data.get('exchange')}
Тип: {data.get('type', 'Unknown')}"""
        
        elif request.type == "whale":
            return f"""Движение: {data.get('amount', 0):,.0f} {data.get('coin', 'BTC')}
Тип: {data.get('type', 'transfer')}
Направление: {data.get('direction', 'unknown')}"""
        
        elif request.type == "market_status":
            return f"""BTC: ${data.get('btc_price', 0):,.0f} (RSI {data.get('btc_rsi', 50):.0f})
ETH: ${data.get('eth_price', 0):,.0f} (RSI {data.get('eth_rsi', 50):.0f})
Fear & Greed: {data.get('fear_greed', 50)}
Доминация BTC: {data.get('btc_dominance', 50):.1f}%"""
        
        elif request.type == "funding":
            rates = data.get('rates', {})
            rates_str = "\n".join([f"{k}: {v*100:+.3f}%" for k, v in rates.items()])
            return f"""Funding rates:
{rates_str}
До начисления: {data.get('minutes', 60)} мин"""
        
        return str(data)
    
    async def _call_api(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Вызов OpenRouter API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cryptoden.app",
            "X-Title": "CryptoDen Bot"
        }
        
        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 150,  # Короткие ответы
            "temperature": 0.7
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.BASE_URL, 
                headers=headers, 
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    logger.error(f"Haiku API error: {resp.status} - {error}")
                    return None
                
                data = await resp.json()
                
                # Считаем токены
                usage = data.get('usage', {})
                self.total_tokens += usage.get('total_tokens', 0)
                
                # Извлекаем ответ
                content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                return content.strip() if content else None
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return {
            "enabled": self.enabled,
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "requests_this_hour": self.requests_this_hour,
            "cache_size": len(self.cache),
            "estimated_cost": f"${self.total_tokens * 0.00000125:.4f}"  # Примерная стоимость
        }


# Синглтон
haiku_explainer = HaikuExplainer()
