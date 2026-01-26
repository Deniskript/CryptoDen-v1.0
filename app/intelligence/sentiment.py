"""
Sentiment - Sentiment анализ
============================

Простой sentiment анализ на основе ключевых слов.
"""

from typing import Dict, List
from dataclasses import dataclass
from enum import Enum


class Sentiment(Enum):
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


@dataclass
class SentimentResult:
    """Результат sentiment анализа"""
    sentiment: Sentiment
    score: float  # -1 to +1
    confidence: float
    keywords_found: List[str]


class SentimentAnalyzer:
    """Анализатор sentiment"""
    
    BULLISH_WORDS = [
        "bullish", "buy", "long", "moon", "pump", "surge", "rally",
        "breakout", "support", "accumulation", "institutional",
        "adoption", "growth", "profit", "gain", "up", "rise",
        "positive", "optimistic", "strong", "healthy"
    ]
    
    BEARISH_WORDS = [
        "bearish", "sell", "short", "dump", "crash", "plunge", "drop",
        "breakdown", "resistance", "distribution", "whale",
        "fear", "loss", "down", "fall", "decline",
        "negative", "pessimistic", "weak", "concern"
    ]
    
    def analyze(self, text: str) -> SentimentResult:
        """Анализировать текст"""
        text_lower = text.lower()
        
        bullish_found = [w for w in self.BULLISH_WORDS if w in text_lower]
        bearish_found = [w for w in self.BEARISH_WORDS if w in text_lower]
        
        bull_score = len(bullish_found)
        bear_score = len(bearish_found)
        total = bull_score + bear_score
        
        if total == 0:
            return SentimentResult(
                sentiment=Sentiment.NEUTRAL,
                score=0,
                confidence=0.5,
                keywords_found=[]
            )
        
        # Score от -1 до +1
        score = (bull_score - bear_score) / total
        
        # Определяем sentiment
        if score > 0.5:
            sentiment = Sentiment.VERY_BULLISH
        elif score > 0.2:
            sentiment = Sentiment.BULLISH
        elif score < -0.5:
            sentiment = Sentiment.VERY_BEARISH
        elif score < -0.2:
            sentiment = Sentiment.BEARISH
        else:
            sentiment = Sentiment.NEUTRAL
        
        confidence = min(0.9, 0.3 + total * 0.1)
        
        return SentimentResult(
            sentiment=sentiment,
            score=score,
            confidence=confidence,
            keywords_found=bullish_found + bearish_found
        )
    
    def analyze_batch(self, texts: List[str]) -> SentimentResult:
        """Анализировать несколько текстов"""
        all_results = [self.analyze(text) for text in texts]
        
        if not all_results:
            return SentimentResult(
                sentiment=Sentiment.NEUTRAL,
                score=0,
                confidence=0.5,
                keywords_found=[]
            )
        
        avg_score = sum(r.score for r in all_results) / len(all_results)
        all_keywords = []
        for r in all_results:
            all_keywords.extend(r.keywords_found)
        
        # Определяем общий sentiment
        if avg_score > 0.5:
            sentiment = Sentiment.VERY_BULLISH
        elif avg_score > 0.2:
            sentiment = Sentiment.BULLISH
        elif avg_score < -0.5:
            sentiment = Sentiment.VERY_BEARISH
        elif avg_score < -0.2:
            sentiment = Sentiment.BEARISH
        else:
            sentiment = Sentiment.NEUTRAL
        
        return SentimentResult(
            sentiment=sentiment,
            score=avg_score,
            confidence=min(0.9, 0.4 + len(all_keywords) * 0.05),
            keywords_found=list(set(all_keywords))
        )


# Глобальный экземпляр
sentiment_analyzer = SentimentAnalyzer()
