"""
Intelligence Module - AI + Новости
===================================

Анализ новостей и sentiment без платных API.

Компоненты:
- web_parser: Парсинг новостных сайтов
- news_analyzer: Анализ влияния новостей
- sentiment: Sentiment анализ
- market_state: Состояние рынка
- calendar: Календарь событий (FOMC, CPI)
"""

from app.intelligence.market_state import market_state, MarketState

__all__ = ["market_state", "MarketState"]
