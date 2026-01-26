"""
Web Parser - Парсинг новостей без API
=====================================

Парсит новости с сайтов через RSS и скрапинг.
"""

import asyncio
from datetime import datetime
from typing import List, Dict
from dataclasses import dataclass
import aiohttp
import feedparser

from app.core.logger import logger
from app.core.constants import NEWS_SOURCES


@dataclass
class NewsItem:
    """Новость"""
    title: str
    source: str
    url: str
    published: datetime
    summary: str = ""


class WebParser:
    """Парсер новостей"""
    
    def __init__(self):
        self._cache: List[NewsItem] = []
        self._last_update: datetime = None
    
    async def fetch_news(self, limit: int = 20) -> List[NewsItem]:
        """
        Получить последние новости
        
        Args:
            limit: Максимум новостей
        
        Returns:
            Список новостей
        """
        all_news = []
        
        async with aiohttp.ClientSession() as session:
            for source_url in NEWS_SOURCES:
                try:
                    news = await self._parse_rss(session, source_url)
                    all_news.extend(news)
                except Exception as e:
                    logger.warning(f"Failed to parse {source_url}: {e}")
        
        # Сортируем по дате
        all_news.sort(key=lambda x: x.published, reverse=True)
        
        # Кэшируем
        self._cache = all_news[:limit]
        self._last_update = datetime.utcnow()
        
        return self._cache
    
    async def _parse_rss(self, session: aiohttp.ClientSession, url: str) -> List[NewsItem]:
        """Парсить RSS feed"""
        async with session.get(url, timeout=10) as resp:
            content = await resp.text()
        
        feed = feedparser.parse(content)
        news = []
        
        for entry in feed.entries[:10]:
            try:
                published = datetime(*entry.published_parsed[:6]) if entry.get("published_parsed") else datetime.utcnow()
                
                news.append(NewsItem(
                    title=entry.get("title", ""),
                    source=feed.feed.get("title", url),
                    url=entry.get("link", ""),
                    published=published,
                    summary=entry.get("summary", "")[:200]
                ))
            except Exception as e:
                logger.debug(f"Failed to parse entry: {e}")
        
        return news
    
    def get_cached(self) -> List[NewsItem]:
        """Получить кэшированные новости"""
        return self._cache
    
    def search(self, keywords: List[str]) -> List[NewsItem]:
        """Поиск новостей по ключевым словам"""
        results = []
        
        for news in self._cache:
            text = (news.title + " " + news.summary).lower()
            if any(kw.lower() in text for kw in keywords):
                results.append(news)
        
        return results


# Глобальный экземпляр
web_parser = WebParser()
