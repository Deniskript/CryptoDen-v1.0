"""
AI Client — Клиент для дешёвых AI моделей через OpenRouter
"""
import aiohttp
from typing import Optional, Dict, Any
import json

from app.core.config import settings
from app.core.logger import logger


class AIClient:
    """
    OpenRouter AI клиент для парсинга
    
    Дешёвые модели:
    - google/gemini-flash-1.5-8b: $0.0000375/1K input, $0.00015/1K output
    - meta-llama/llama-3.1-8b-instruct:free: БЕСПЛАТНО
    - mistralai/mistral-7b-instruct:free: БЕСПЛАТНО
    """
    
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    # Дешёвые модели в порядке приоритета
    CHEAP_MODELS = [
        "google/gemini-flash-1.5-8b",       # ~$0.00004/1K - очень дешёвая
        "meta-llama/llama-3.1-8b-instruct:free",  # Бесплатная
        "mistralai/mistral-7b-instruct:free",     # Бесплатная
    ]
    
    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.model = settings.parsing_ai_model
        self.session: Optional[aiohttp.ClientSession] = None
        
        if not self.api_key:
            logger.warning("OpenRouter API key not configured")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def parse_json(self, prompt: str, system_prompt: str = None) -> Optional[Dict]:
        """
        Отправить запрос AI и получить JSON ответ
        
        Args:
            prompt: Основной запрос
            system_prompt: Системный промпт (опционально)
        
        Returns:
            Распарсенный JSON или None
        """
        
        if not self.api_key:
            logger.warning("AI Client: No API key")
            return None
        
        if self.session is None:
            self.session = aiohttp.ClientSession()
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cryptoden.ru",
            "X-Title": "CryptoDen Trading Bot"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,  # Низкая температура для консистентности
            "max_tokens": 1000,
            "response_format": {"type": "json_object"}
        }
        
        try:
            async with self.session.post(
                self.BASE_URL,
                headers=headers,
                json=payload
            ) as resp:
                
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"AI API error {resp.status}: {error_text}")
                    return None
                
                data = await resp.json()
                
                # Извлекаем контент
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # Логируем использование токенов
                usage = data.get("usage", {})
                logger.debug(f"AI tokens: {usage.get('total_tokens', 0)}")
                
                # Парсим JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Пробуем извлечь JSON из текста
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                    logger.error(f"Failed to parse JSON: {content[:200]}")
                    return None
                    
        except Exception as e:
            logger.error(f"AI request error: {e}")
            return None
    
    async def analyze_text(self, text: str, task: str = "sentiment") -> Optional[Dict]:
        """
        Анализ текста (sentiment, важность, монеты)
        
        Args:
            text: Текст для анализа
            task: Тип задачи (sentiment, importance, extract_coins)
        """
        
        if task == "sentiment":
            system = "You are a crypto news analyst. Respond ONLY in JSON format."
            prompt = f"""Analyze this crypto news and return JSON:

News: {text}

Return JSON:
{{
    "sentiment": <-1 to 1, where -1=very negative, 0=neutral, 1=very positive>,
    "importance": "<LOW|MEDIUM|HIGH|CRITICAL>",
    "coins_affected": ["<coin symbols like BTC, ETH>"],
    "summary": "<one sentence summary>"
}}"""
        
        elif task == "calendar":
            system = "You are an economic calendar analyst. Respond ONLY in JSON format."
            prompt = f"""Analyze this economic event and return JSON:

Event: {text}

Return JSON:
{{
    "importance": "<LOW|MEDIUM|HIGH|CRITICAL>",
    "expected_impact": "<NONE|LOW_VOLATILITY|MEDIUM_VOLATILITY|HIGH_VOLATILITY>",
    "affected_assets": ["<BTC, ETH, etc>"],
    "recommendation": "<TRADE|WAIT|REDUCE_POSITION>"
}}"""
        
        else:
            return None
        
        return await self.parse_json(prompt, system)


# Глобальный экземпляр
ai_client = AIClient()
