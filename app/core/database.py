"""
Database - Redis и PostgreSQL клиенты
=====================================

Асинхронные клиенты для работы с БД.
"""

import redis.asyncio as redis
from typing import Optional
from app.core.config import settings
from app.core.logger import logger


class RedisClient:
    """Асинхронный Redis клиент"""
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Подключение к Redis"""
        try:
            self._client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self._client.ping()
            logger.info("✅ Redis connected")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}")
            self._client = None
    
    async def close(self):
        """Закрытие соединения"""
        if self._client:
            await self._client.close()
            logger.info("Redis disconnected")
    
    async def get(self, key: str) -> Optional[str]:
        """Получить значение"""
        if not self._client:
            return None
        return await self._client.get(key)
    
    async def set(self, key: str, value: str, ex: int = 300):
        """Установить значение с TTL"""
        if not self._client:
            return
        await self._client.set(key, value, ex=ex)
    
    async def delete(self, key: str):
        """Удалить ключ"""
        if not self._client:
            return
        await self._client.delete(key)


# Глобальный экземпляр
redis_client = RedisClient()
