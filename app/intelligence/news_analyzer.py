"""
News Analyzer - Анализ влияния новостей
=======================================

Определяет влияние новостей на рынок.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from app.core.logger import logger
from app.core.constants import CRITICAL_EVENTS
from app.intelligence.web_parser import NewsItem


class NewsImpact(Enum):
    CRITICAL_NEGATIVE = "critical_negative"  # Стоп торговли
    NEGATIVE = "negative"                     # Блок LONGs
    NEUTRAL = "neutral"                       # Без влияния
    POSITIVE = "positive"                     # Буст LONGs
    CRITICAL_POSITIVE = "critical_positive"   # Сильный буст


@dataclass
class NewsAnalysis:
    """Результат анализа новости"""
    news: NewsItem
    impact: NewsImpact
    confidence: float
    affected_coins: List[str]
    action: str  # "STOP", "BLOCK_LONGS", "BLOCK_SHORTS", "BOOST_LONGS", "NONE"
    reason: str


class NewsAnalyzer:
    """Анализатор новостей"""
    
    # Ключевые слова для негативных новостей
    NEGATIVE_KEYWORDS = [
        "hack", "exploit", "attack", "breach", "stolen",
        "crash", "dump", "plunge", "collapse",
        "sec", "lawsuit", "investigation", "ban", "crackdown",
        "bankruptcy", "insolvent", "fraud", "scam",
        "delist", "suspend", "halt",
    ]
    
    # Ключевые слова для позитивных новостей
    POSITIVE_KEYWORDS = [
        "etf", "approval", "approved", "adopt", "adoption",
        "partnership", "integration", "launch",
        "upgrade", "bullish", "rally", "surge", "soar",
        "institutional", "investment", "fund",
        "support", "backing",
    ]
    
    # Монеты упоминания
    COIN_KEYWORDS = {
        "BTC": ["bitcoin", "btc"],
        "ETH": ["ethereum", "eth"],
        "BNB": ["binance", "bnb"],
        "SOL": ["solana", "sol"],
        "XRP": ["ripple", "xrp"],
        "ADA": ["cardano", "ada"],
        "DOGE": ["dogecoin", "doge"],
        "MATIC": ["polygon", "matic"],
        "LINK": ["chainlink", "link"],
        "AVAX": ["avalanche", "avax"],
    }
    
    def analyze(self, news: NewsItem) -> NewsAnalysis:
        """Анализировать новость"""
        text = (news.title + " " + news.summary).lower()
        
        # Определяем затронутые монеты
        affected_coins = self._find_affected_coins(text)
        
        # Проверяем критические события
        if any(event.lower() in text for event in CRITICAL_EVENTS):
            return NewsAnalysis(
                news=news,
                impact=NewsImpact.CRITICAL_NEGATIVE,
                confidence=0.9,
                affected_coins=affected_coins or ["ALL"],
                action="STOP",
                reason=f"Critical event detected in: {news.title[:50]}"
            )
        
        # Считаем sentiment
        neg_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text)
        pos_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text)
        
        if neg_count > pos_count + 2:
            return NewsAnalysis(
                news=news,
                impact=NewsImpact.NEGATIVE,
                confidence=min(0.8, 0.4 + neg_count * 0.1),
                affected_coins=affected_coins,
                action="BLOCK_LONGS",
                reason=f"Negative news: {neg_count} negative keywords"
            )
        
        if pos_count > neg_count + 2:
            return NewsAnalysis(
                news=news,
                impact=NewsImpact.POSITIVE,
                confidence=min(0.8, 0.4 + pos_count * 0.1),
                affected_coins=affected_coins,
                action="BOOST_LONGS",
                reason=f"Positive news: {pos_count} positive keywords"
            )
        
        return NewsAnalysis(
            news=news,
            impact=NewsImpact.NEUTRAL,
            confidence=0.5,
            affected_coins=affected_coins,
            action="NONE",
            reason="Neutral news"
        )
    
    def _find_affected_coins(self, text: str) -> List[str]:
        """Найти упомянутые монеты"""
        affected = []
        for coin, keywords in self.COIN_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                affected.append(coin)
        return affected
    
    def analyze_batch(self, news_list: List[NewsItem]) -> List[NewsAnalysis]:
        """Анализировать список новостей"""
        return [self.analyze(news) for news in news_list]


# Глобальный экземпляр
news_analyzer = NewsAnalyzer()
