"""
📰 RSS Parser — агрегатор крипто новостей
Собирает новости из лучших источников БЕЗ API

Источники:
- CryptoPanic RSS
- CoinDesk
- Cointelegraph
- The Block
- Decrypt
- Bitcoin Magazine
"""
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import re
import hashlib

from app.core.logger import logger


@dataclass
class NewsItem:
    """Новость"""
    title: str
    description: str
    url: str
    source: str
    published: datetime
    sentiment: str = "neutral"  # bullish, bearish, neutral
    importance: str = "medium"  # low, medium, high, critical
    coins: List[str] = field(default_factory=list)
    news_id: str = ""
    
    def __post_init__(self):
        if not self.news_id:
            self.news_id = hashlib.md5(f"{self.title}{self.url}".encode()).hexdigest()[:12]


class RSSParser:
    """
    📰 RSS Parser
    
    Агрегирует новости из топовых крипто источников
    """
    
    def __init__(self):
        # RSS источники
        self.feeds = {
            # Основные новости
            "cointelegraph": {
                "url": "https://cointelegraph.com/rss",
                "name": "Cointelegraph",
                "priority": 1,
            },
            "coindesk": {
                "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
                "name": "CoinDesk",
                "priority": 1,
            },
            "theblock": {
                "url": "https://www.theblock.co/rss.xml",
                "name": "The Block",
                "priority": 1,
            },
            "decrypt": {
                "url": "https://decrypt.co/feed",
                "name": "Decrypt",
                "priority": 2,
            },
            "bitcoinmagazine": {
                "url": "https://bitcoinmagazine.com/feed",
                "name": "Bitcoin Magazine",
                "priority": 2,
            },
            
            # Быстрые новости
            "cryptopanic": {
                "url": "https://cryptopanic.com/news/rss/",
                "name": "CryptoPanic",
                "priority": 1,
            },
            
            # Аналитика
            "cryptoslate": {
                "url": "https://cryptoslate.com/feed/",
                "name": "CryptoSlate",
                "priority": 2,
            },
            "newsbtc": {
                "url": "https://www.newsbtc.com/feed/",
                "name": "NewsBTC",
                "priority": 3,
            },
        }
        
        # Ключевые слова для анализа
        self.critical_keywords = [
            "sec", "etf approved", "etf rejected", "fed", "fomc",
            "trump", "biden", "regulation", "ban", "hack",
            "bankruptcy", "insolvent", "breaking", "just in",
            "emergency", "halving", "approval"
        ]
        
        self.bullish_keywords = [
            "surge", "soar", "rally", "pump", "breakout", "moon",
            "adoption", "partnership", "bullish", "buy", "accumulate",
            "institutional", "etf approved", "all-time high", "ath",
            "upgrade", "launch", "integration", "support", "record",
            "milestone", "gains", "profit", "growth"
        ]
        
        self.bearish_keywords = [
            "crash", "dump", "plunge", "tank", "bearish", "sell",
            "liquidation", "hack", "scam", "fraud", "ban", "reject",
            "lawsuit", "sec charges", "investigation", "bankrupt",
            "layoff", "delay", "concern", "warning", "risk",
            "losses", "down", "drop", "decline", "fall"
        ]
        
        self.coin_patterns = [
            r'\b(BTC|Bitcoin)\b',
            r'\b(ETH|Ethereum)\b',
            r'\b(SOL|Solana)\b',
            r'\b(BNB|Binance)\b',
            r'\b(XRP|Ripple)\b',
            r'\b(ADA|Cardano)\b',
            r'\b(DOGE|Dogecoin)\b',
            r'\b(AVAX|Avalanche)\b',
            r'\b(LINK|Chainlink)\b',
            r'\b(DOT|Polkadot)\b',
        ]
        
        # Кэш
        self.cache: Dict[str, List[NewsItem]] = {}
        self.cache_time: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=5)
        
        # История для дедупликации
        self.seen_ids: set = set()
        
        logger.info("📰 RSS Parser инициализирован")
    
    async def _fetch_feed(self, feed_id: str) -> List[NewsItem]:
        """Загрузить один RSS фид"""
        
        feed_config = self.feeds.get(feed_id)
        if not feed_config:
            return []
        
        # Проверяем кэш
        if feed_id in self.cache:
            if datetime.now() - self.cache_time.get(feed_id, datetime.min) < self.cache_duration:
                return self.cache[feed_id]
        
        news_items = []
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (compatible; CryptoBot/1.0)"
                }
                
                async with session.get(
                    feed_config["url"],
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    
                    if response.status != 200:
                        logger.debug(f"RSS {feed_id} returned {response.status}")
                        return []
                    
                    content = await response.text()
                    
                    # Парсим XML
                    try:
                        root = ET.fromstring(content)
                    except ET.ParseError as e:
                        logger.debug(f"RSS parse error {feed_id}: {e}")
                        return []
                    
                    # Ищем items (RSS 2.0)
                    items = root.findall('.//item')
                    if not items:
                        # Пробуем Atom формат
                        items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                    
                    for item in items[:20]:  # Только последние 20
                        news = self._parse_item(item, feed_config)
                        if news:
                            news_items.append(news)
            
            # Кэшируем
            self.cache[feed_id] = news_items
            self.cache_time[feed_id] = datetime.now()
            
            logger.debug(f"📰 {feed_id}: {len(news_items)} новостей")
            
        except asyncio.TimeoutError:
            logger.debug(f"RSS timeout {feed_id}")
        except Exception as e:
            logger.debug(f"RSS fetch error {feed_id}: {e}")
        
        return news_items
    
    def _parse_item(self, item: ET.Element, feed_config: Dict) -> Optional[NewsItem]:
        """Распарсить элемент RSS"""
        
        try:
            # Пробуем разные форматы
            title = self._get_text(item, ['title', '{http://www.w3.org/2005/Atom}title'])
            description = self._get_text(item, [
                'description', 
                '{http://www.w3.org/2005/Atom}summary',
                '{http://www.w3.org/2005/Atom}content'
            ])
            url = self._get_link(item)
            pub_date = self._get_text(item, [
                'pubDate', 
                '{http://www.w3.org/2005/Atom}published',
                '{http://www.w3.org/2005/Atom}updated'
            ])
            
            if not title:
                return None
            
            # Парсим дату
            published = self._parse_date(pub_date)
            
            # Очищаем HTML из description
            description = self._clean_html(description or "")
            
            # Анализируем
            full_text = f"{title} {description}".lower()
            sentiment = self._analyze_sentiment(full_text)
            importance = self._analyze_importance(full_text)
            coins = self._extract_coins(f"{title} {description}")
            
            return NewsItem(
                title=title[:200],
                description=description[:500],
                url=url or "",
                source=feed_config["name"],
                published=published,
                sentiment=sentiment,
                importance=importance,
                coins=coins
            )
            
        except Exception as e:
            return None
    
    def _get_text(self, item: ET.Element, tags: List[str]) -> Optional[str]:
        """Получить текст из элемента"""
        
        for tag in tags:
            elem = item.find(tag)
            if elem is not None and elem.text:
                return elem.text.strip()
        return None
    
    def _get_link(self, item: ET.Element) -> Optional[str]:
        """Получить ссылку из элемента"""
        
        # RSS 2.0
        link_elem = item.find('link')
        if link_elem is not None:
            if link_elem.text:
                return link_elem.text.strip()
        
        # Atom
        link_elem = item.find('{http://www.w3.org/2005/Atom}link')
        if link_elem is not None:
            href = link_elem.get('href')
            if href:
                return href.strip()
        
        return None
    
    def _parse_date(self, date_str: Optional[str]) -> datetime:
        """Распарсить дату"""
        
        if not date_str:
            return datetime.now()
        
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        
        # Убираем timezone info если мешает
        clean_date = date_str.strip()
        
        for fmt in formats:
            try:
                dt = datetime.strptime(clean_date, fmt)
                # Убираем timezone для простоты
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
                return dt
            except:
                continue
        
        return datetime.now()
    
    def _clean_html(self, text: str) -> str:
        """Очистить HTML теги"""
        
        # Удаляем теги
        clean = re.sub(r'<[^>]+>', '', text)
        # Декодируем entities
        clean = clean.replace('&amp;', '&')
        clean = clean.replace('&lt;', '<')
        clean = clean.replace('&gt;', '>')
        clean = clean.replace('&quot;', '"')
        clean = clean.replace('&#39;', "'")
        clean = clean.replace('&nbsp;', ' ')
        clean = clean.replace('&#8217;', "'")
        clean = clean.replace('&#8220;', '"')
        clean = clean.replace('&#8221;', '"')
        # Убираем лишние пробелы
        clean = ' '.join(clean.split())
        return clean.strip()
    
    def _analyze_sentiment(self, text: str) -> str:
        """Анализ сентимента"""
        
        bullish_count = sum(1 for w in self.bullish_keywords if w in text)
        bearish_count = sum(1 for w in self.bearish_keywords if w in text)
        
        if bullish_count > bearish_count + 1:
            return "bullish"
        elif bearish_count > bullish_count + 1:
            return "bearish"
        return "neutral"
    
    def _analyze_importance(self, text: str) -> str:
        """Анализ важности"""
        
        # Критические новости
        if any(kw in text for kw in self.critical_keywords):
            return "critical"
        
        # Много ключевых слов = важно
        keyword_count = sum(1 for w in self.bullish_keywords + self.bearish_keywords if w in text)
        
        if keyword_count >= 3:
            return "high"
        elif keyword_count >= 1:
            return "medium"
        return "low"
    
    def _extract_coins(self, text: str) -> List[str]:
        """Извлечь упомянутые монеты"""
        
        coins = set()
        
        coin_map = {
            'BTC': 'BTC', 'BITCOIN': 'BTC',
            'ETH': 'ETH', 'ETHEREUM': 'ETH',
            'SOL': 'SOL', 'SOLANA': 'SOL',
            'BNB': 'BNB', 'BINANCE': 'BNB',
            'XRP': 'XRP', 'RIPPLE': 'XRP',
            'ADA': 'ADA', 'CARDANO': 'ADA',
            'DOGE': 'DOGE', 'DOGECOIN': 'DOGE',
            'AVAX': 'AVAX', 'AVALANCHE': 'AVAX',
            'LINK': 'LINK', 'CHAINLINK': 'LINK',
            'DOT': 'DOT', 'POLKADOT': 'DOT',
            'MATIC': 'MATIC', 'POLYGON': 'MATIC',
        }
        
        text_upper = text.upper()
        for keyword, coin in coin_map.items():
            if keyword in text_upper:
                coins.add(coin)
        
        return list(coins)
    
    async def get_all_news(self, hours: int = 4) -> List[NewsItem]:
        """Получить все новости"""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        all_news = []
        
        # Загружаем параллельно
        tasks = [self._fetch_feed(feed_id) for feed_id in self.feeds.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_news.extend(result)
        
        # Фильтруем по времени
        all_news = [n for n in all_news if n.published > cutoff_time]
        
        # Дедупликация
        unique_news = []
        for news in all_news:
            if news.news_id not in self.seen_ids:
                self.seen_ids.add(news.news_id)
                unique_news.append(news)
        
        # Ограничиваем размер seen_ids
        if len(self.seen_ids) > 1000:
            self.seen_ids = set(list(self.seen_ids)[-500:])
        
        # Сортируем по важности и времени
        importance_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        unique_news.sort(key=lambda x: (
            importance_order.get(x.importance, 4),
            -x.published.timestamp()
        ))
        
        logger.info(f"📰 Собрано {len(unique_news)} уникальных новостей")
        
        return unique_news
    
    async def get_critical_news(self) -> List[NewsItem]:
        """Получить только критические новости"""
        
        all_news = await self.get_all_news(hours=2)
        return [n for n in all_news if n.importance in ["critical", "high"]]
    
    async def get_news_for_coin(self, coin: str) -> List[NewsItem]:
        """Получить новости для конкретной монеты"""
        
        all_news = await self.get_all_news(hours=24)
        return [n for n in all_news if coin in n.coins]
    
    async def get_news_summary(self) -> Dict:
        """Сводка новостей для AI"""
        
        news = await self.get_all_news(hours=4)
        
        if not news:
            return {
                "total": 0,
                "critical": 0,
                "bullish": 0,
                "bearish": 0,
                "sentiment": "neutral",
                "top_news": [],
                "by_coin": {}
            }
        
        critical_count = sum(1 for n in news if n.importance == "critical")
        bullish_count = sum(1 for n in news if n.sentiment == "bullish")
        bearish_count = sum(1 for n in news if n.sentiment == "bearish")
        
        # По монетам
        by_coin = {}
        for n in news:
            for coin in n.coins:
                if coin not in by_coin:
                    by_coin[coin] = {"count": 0, "bullish": 0, "bearish": 0}
                by_coin[coin]["count"] += 1
                if n.sentiment == "bullish":
                    by_coin[coin]["bullish"] += 1
                elif n.sentiment == "bearish":
                    by_coin[coin]["bearish"] += 1
        
        # Общий сентимент
        if bullish_count > bearish_count * 1.5:
            sentiment = "bullish"
        elif bearish_count > bullish_count * 1.5:
            sentiment = "bearish"
        else:
            sentiment = "neutral"
        
        return {
            "total": len(news),
            "critical": critical_count,
            "bullish": bullish_count,
            "bearish": bearish_count,
            "sentiment": sentiment,
            "top_news": news[:5],
            "by_coin": by_coin
        }
    
    def get_status_text(self) -> str:
        """Статус для Telegram"""
        
        cached = sum(len(items) for items in self.cache.values())
        
        sources_list = ', '.join(f.get('name', k) for k, f in list(self.feeds.items())[:4])
        
        return f"""📰 *RSS Parser*

*Источников:* {len(self.feeds)} ({sources_list}...)
*В кэше:* {cached} новостей
*Seen IDs:* {len(self.seen_ids)}
"""


# Singleton
rss_parser = RSSParser()


async def get_latest_news() -> List[NewsItem]:
    """Публичная функция для получения новостей"""
    return await rss_parser.get_all_news()


async def get_news_summary() -> Dict:
    """Публичная функция для сводки"""
    return await rss_parser.get_news_summary()
