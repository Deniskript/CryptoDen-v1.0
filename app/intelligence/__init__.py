"""
Intelligence Module — AI анализ новостей и рынка
"""

from app.intelligence.ai_client import AIClient, ai_client
from app.intelligence.news_parser import (
    NewsParser,
    NewsItem,
    CalendarEvent,
    news_parser,
)

__all__ = [
    'AIClient',
    'ai_client',
    'NewsParser',
    'NewsItem',
    'CalendarEvent',
    'news_parser',
]
