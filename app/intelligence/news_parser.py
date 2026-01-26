"""
News Parser — Парсинг новостей + AI анализ
Использует CryptoCompare и CoinGecko APIs
"""
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logger import logger
from app.intelligence.ai_client import ai_client


@dataclass
class NewsItem:
    """Новость с анализом"""
    id: str
    title: str
    source: str
    url: str
    published_at: datetime
    
    # AI анализ
    sentiment: float = 0.0  # -1 to 1
    importance: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    coins_affected: List[str] = field(default_factory=list)
    summary: str = ""
    
    # Оригинальные данные
    raw_text: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "sentiment": self.sentiment,
            "importance": self.importance,
            "coins_affected": self.coins_affected,
            "summary": self.summary
        }


@dataclass
class CalendarEvent:
    """Экономическое событие"""
    id: str
    event: str
    time: datetime
    importance: str = "MEDIUM"
    expected_impact: str = "MEDIUM_VOLATILITY"
    affected_assets: List[str] = field(default_factory=list)
    recommendation: str = "TRADE"
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "event": self.event,
            "time": self.time.isoformat(),
            "importance": self.importance,
            "expected_impact": self.expected_impact,
            "affected_assets": self.affected_assets,
            "recommendation": self.recommendation,
            "time_until": str(self.time - datetime.now(timezone.utc))
        }


class NewsParser:
    """
    Парсер новостей и календаря
    
    Источники:
    - CryptoCompare News API
    - CoinGecko (trending/status)
    - Hardcoded календарь важных событий
    
    AI анализ:
    - Sentiment (-1 to +1)
    - Importance (LOW/MEDIUM/HIGH/CRITICAL)
    - Affected coins
    """
    
    CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/v2/news/"
    COINGECKO_URL = "https://api.coingecko.com/api/v3"
    
    # Важные экономические события (хардкод для надёжности)
    IMPORTANT_EVENTS = [
        {"event": "FOMC Meeting", "day": "wednesday", "importance": "CRITICAL"},
        {"event": "US CPI Release", "day": "monthly", "importance": "CRITICAL"},
        {"event": "US Jobs Report", "day": "first_friday", "importance": "HIGH"},
        {"event": "ECB Rate Decision", "day": "monthly", "importance": "HIGH"},
    ]
    
    def __init__(self):
        self.cryptocompare_key = settings.cryptocompare_api_key
        self.coingecko_key = settings.coingecko_api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, Any] = {}
        self.cache_time: Optional[datetime] = None
        self.cache_ttl = timedelta(minutes=5)
        
        logger.info("NewsParser initialized")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def fetch_cryptocompare_news(self, limit: int = 20) -> List[NewsItem]:
        """Получить новости из CryptoCompare"""
        
        await self._ensure_session()
        
        params = {
            "lang": "EN",
            "sortOrder": "latest"
        }
        
        try:
            # Сначала пробуем без API ключа (бесплатный лимит)
            async with self.session.get(
                self.CRYPTOCOMPARE_URL,
                params=params
            ) as resp:
                
                if resp.status != 200:
                    logger.warning(f"CryptoCompare API error: {resp.status}")
                    return []
                
                data = await resp.json()
                
                # Проверяем на ошибку
                if data.get("Response") == "Error":
                    logger.warning(f"CryptoCompare: {data.get('Message', 'Unknown error')}")
                    return []
                
                all_news = data.get("Data", [])
                
                # Data может быть списком или словарём
                if isinstance(all_news, dict):
                    logger.warning("CryptoCompare returned dict instead of list")
                    return []
                
                news_data = all_news[:limit] if all_news else []
                
                news_items = []
                for item in news_data:
                    news = NewsItem(
                        id=str(item.get("id", "")),
                        title=item.get("title", ""),
                        source=item.get("source", ""),
                        url=item.get("url", ""),
                        published_at=datetime.fromtimestamp(
                            item.get("published_on", 0),
                            tz=timezone.utc
                        ),
                        raw_text=item.get("body", "")[:500]
                    )
                    news_items.append(news)
                
                logger.info(f"Fetched {len(news_items)} news from CryptoCompare")
                return news_items
                
        except Exception as e:
            logger.error(f"CryptoCompare fetch error: {e}")
            return []
    
    async def fetch_coingecko_trending(self) -> List[str]:
        """Получить trending монеты из CoinGecko"""
        
        await self._ensure_session()
        
        try:
            url = f"{self.COINGECKO_URL}/search/trending"
            headers = {}
            
            if self.coingecko_key:
                headers["x-cg-demo-api-key"] = self.coingecko_key
            
            async with self.session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return []
                
                data = await resp.json()
                coins = data.get("coins", [])
                
                trending = [
                    coin.get("item", {}).get("symbol", "").upper()
                    for coin in coins[:5]
                ]
                
                logger.debug(f"Trending coins: {trending}")
                return trending
                
        except Exception as e:
            logger.error(f"CoinGecko fetch error: {e}")
            return []
    
    async def analyze_news_with_ai(self, news: NewsItem) -> NewsItem:
        """AI анализ одной новости"""
        
        text = f"{news.title}. {news.raw_text[:300]}"
        
        async with ai_client:
            result = await ai_client.analyze_text(text, task="sentiment")
        
        if result:
            news.sentiment = float(result.get("sentiment", 0))
            news.importance = result.get("importance", "LOW")
            news.coins_affected = result.get("coins_affected", [])
            news.summary = result.get("summary", "")
        
        return news
    
    async def fetch_news(self, with_ai: bool = True, limit: int = 10) -> List[NewsItem]:
        """
        Получить и проанализировать новости
        
        Args:
            with_ai: Использовать AI для анализа
            limit: Количество новостей
        """
        
        # Проверяем кэш
        if self.cache_time and datetime.now(timezone.utc) - self.cache_time < self.cache_ttl:
            cached = self.cache.get("news", [])
            if cached:
                logger.debug("Returning cached news")
                return cached
        
        # Получаем новости
        news_items = await self.fetch_cryptocompare_news(limit)
        
        if not news_items:
            logger.warning("No news fetched")
            return []
        
        # AI анализ (если включён и есть API ключ)
        if with_ai and settings.openrouter_api_key:
            # Анализируем только топ-5 для экономии токенов
            analyzed = []
            for news in news_items[:5]:
                try:
                    analyzed_news = await self.analyze_news_with_ai(news)
                    analyzed.append(analyzed_news)
                    await asyncio.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.error(f"AI analysis error: {e}")
                    analyzed.append(news)
            
            # Добавляем остальные без анализа
            news_items = analyzed + news_items[5:]
        
        # Сохраняем в кэш
        self.cache["news"] = news_items
        self.cache_time = datetime.now(timezone.utc)
        
        return news_items
    
    async def fetch_calendar(self) -> List[CalendarEvent]:
        """
        Получить календарь важных событий
        
        Returns:
            Список событий на ближайшие 7 дней
        """
        
        now = datetime.now(timezone.utc)
        events = []
        
        # Хардкод важных событий (более надёжно чем парсинг)
        # FOMC meetings 2025-2026
        fomc_dates = [
            "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
            "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17",
            "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17",
        ]
        
        for date_str in fomc_dates:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                hour=19, minute=0, tzinfo=timezone.utc
            )
            
            # Только ближайшие 7 дней
            if now <= event_date <= now + timedelta(days=7):
                events.append(CalendarEvent(
                    id=f"fomc_{date_str}",
                    event="FOMC Interest Rate Decision",
                    time=event_date,
                    importance="CRITICAL",
                    expected_impact="HIGH_VOLATILITY",
                    affected_assets=["BTC", "ETH", "ALL"],
                    recommendation="WAIT" if event_date - now < timedelta(hours=4) else "REDUCE_POSITION"
                ))
        
        # CPI releases (примерно 10-13 число каждого месяца)
        cpi_dates = [
            "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10",
            "2026-01-14", "2026-02-11",
        ]
        
        for date_str in cpi_dates:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
                hour=13, minute=30, tzinfo=timezone.utc
            )
            
            if now <= event_date <= now + timedelta(days=7):
                events.append(CalendarEvent(
                    id=f"cpi_{date_str}",
                    event="US CPI Inflation Data",
                    time=event_date,
                    importance="CRITICAL",
                    expected_impact="HIGH_VOLATILITY",
                    affected_assets=["BTC", "ETH", "ALL"],
                    recommendation="WAIT" if event_date - now < timedelta(hours=2) else "TRADE"
                ))
        
        # Jobs Report (первая пятница месяца)
        # Добавляем ближайшую первую пятницу
        first_day = now.replace(day=1)
        days_until_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_until_friday)
        
        if first_friday < now:
            # Следующий месяц
            next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
            days_until_friday = (4 - next_month.weekday()) % 7
            first_friday = next_month + timedelta(days=days_until_friday)
        
        first_friday = first_friday.replace(hour=13, minute=30, tzinfo=timezone.utc)
        
        if now <= first_friday <= now + timedelta(days=7):
            events.append(CalendarEvent(
                id=f"jobs_{first_friday.strftime('%Y%m%d')}",
                event="US Non-Farm Payrolls",
                time=first_friday,
                importance="HIGH",
                expected_impact="MEDIUM_VOLATILITY",
                affected_assets=["BTC", "ETH"],
                recommendation="TRADE"
            ))
        
        logger.info(f"Calendar: {len(events)} events in next 7 days")
        return events
    
    def determine_market_mode(
        self,
        news: List[NewsItem],
        calendar: List[CalendarEvent]
    ) -> str:
        """
        Определить режим рынка на основе новостей и календаря
        
        Returns:
            NORMAL - обычная торговля
            NEWS_ALERT - важная новость, осторожно
            WAIT_EVENT - скоро важное событие, лучше подождать
        """
        
        now = datetime.now(timezone.utc)
        
        # Проверяем календарь - есть ли событие в ближайшие 4 часа
        for event in calendar:
            time_until = event.time - now
            
            if timedelta(0) <= time_until <= timedelta(hours=4):
                if event.importance in ["CRITICAL", "HIGH"]:
                    logger.warning(f"⚠️ Market mode: WAIT_EVENT ({event.event} in {time_until})")
                    return "WAIT_EVENT"
        
        # Проверяем новости - есть ли критически важные
        critical_news = [
            n for n in news
            if n.importance == "CRITICAL" and n.sentiment < -0.5
        ]
        
        if critical_news:
            logger.warning(f"⚠️ Market mode: NEWS_ALERT ({len(critical_news)} critical news)")
            return "NEWS_ALERT"
        
        # Проверяем сильно негативные новости
        very_negative = [n for n in news if n.sentiment < -0.7]
        if len(very_negative) >= 3:
            logger.warning(f"⚠️ Market mode: NEWS_ALERT (multiple negative news)")
            return "NEWS_ALERT"
        
        return "NORMAL"
    
    async def get_market_context(self) -> Dict[str, Any]:
        """
        Получить полный контекст рынка
        
        Returns:
            {
                "news": [...],
                "calendar": [...],
                "trending": [...],
                "market_mode": "NORMAL|NEWS_ALERT|WAIT_EVENT",
                "timestamp": "..."
            }
        """
        
        # Параллельно получаем все данные
        news_task = self.fetch_news(with_ai=True, limit=10)
        calendar_task = self.fetch_calendar()
        trending_task = self.fetch_coingecko_trending()
        
        news, calendar, trending = await asyncio.gather(
            news_task,
            calendar_task,
            trending_task,
            return_exceptions=True
        )
        
        # Обработка ошибок
        if isinstance(news, Exception):
            logger.error(f"News fetch error: {news}")
            news = []
        if isinstance(calendar, Exception):
            logger.error(f"Calendar fetch error: {calendar}")
            calendar = []
        if isinstance(trending, Exception):
            logger.error(f"Trending fetch error: {trending}")
            trending = []
        
        # Определяем режим рынка
        market_mode = self.determine_market_mode(news, calendar)
        
        return {
            "news": [n.to_dict() for n in news],
            "calendar": [e.to_dict() for e in calendar],
            "trending": trending,
            "market_mode": market_mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "news_count": len(news),
            "upcoming_events": len(calendar)
        }


# Глобальный экземпляр
news_parser = NewsParser()
