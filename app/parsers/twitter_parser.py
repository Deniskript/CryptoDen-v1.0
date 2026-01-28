"""
🐦 Twitter Parser — парсинг через Nitter
Получаем данные китов и новости БЕЗ API

Источники:
- @whale_alert — транзакции китов
- @WatcherGuru — быстрые новости
- @lookonchain — движения китов
- @EmberCN — инсайды
"""
import asyncio
import aiohttp
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from bs4 import BeautifulSoup

from app.core.logger import logger


@dataclass
class WhaleTransaction:
    """Транзакция кита"""
    coin: str
    amount: float
    amount_usd: float
    from_wallet: str
    to_wallet: str
    tx_type: str  # "exchange_in", "exchange_out", "whale_move", "unknown"
    timestamp: datetime
    source: str
    raw_text: str
    
    @property
    def is_bearish(self) -> bool:
        """Медвежий сигнал (приток на биржу)"""
        return self.tx_type == "exchange_in" and self.amount_usd > 10_000_000
    
    @property
    def is_bullish(self) -> bool:
        """Бычий сигнал (отток с биржи)"""
        return self.tx_type == "exchange_out" and self.amount_usd > 10_000_000


@dataclass
class TwitterNews:
    """Новость из Twitter"""
    text: str
    author: str
    timestamp: datetime
    sentiment: str  # "bullish", "bearish", "neutral"
    importance: str  # "low", "medium", "high", "critical"
    coins_mentioned: List[str] = field(default_factory=list)


class TwitterParser:
    """
    🐦 Парсер Twitter через Nitter
    
    Nitter — бесплатное зеркало Twitter без API
    
    ⚠️ СТАТУС: ОТКЛЮЧЁН — Nitter инстансы недоступны
    """
    
    def __init__(self):
        # ⚠️ ОТКЛЮЧЁН — Nitter не работает
        self.enabled = False
        
        # Список Nitter инстансов (большинство не работают)
        self.nitter_instances = [
            "https://nitter.privacydev.net",
            "https://nitter.poast.org",
            "https://nitter.woodland.cafe",
            "https://nitter.esmailelbob.xyz",
            "https://nitter.tiekoetter.com",
            "https://nitter.net",
            "https://nitter.cz",
            "https://nitter.unixfox.eu",
        ]
        self.working_instance = None
        
        if not self.enabled:
            logger.warning("⚠️ Twitter Parser ОТКЛЮЧЁН — Nitter недоступен")
        
        # Аккаунты для парсинга
        self.whale_accounts = [
            "whale_alert",      # Основной источник транзакций
            "lookonchain",      # Движения китов
            "EmberCN",          # Китайские инсайды
        ]
        
        self.news_accounts = [
            "WatcherGuru",      # Быстрые новости
            "CryptoPotato_",    # Агрегатор
            "Cointelegraph",    # Основные новости
            "BitcoinMagazine",  # BTC новости
        ]
        
        # Паттерны для парсинга whale_alert
        self.amount_pattern = re.compile(r'([\d,]+(?:\.\d+)?)\s*(BTC|ETH|USDT|USDC|XRP|SOL|BNB|ADA|DOGE|AVAX|LINK)', re.I)
        self.usd_pattern = re.compile(r'\$([\d,]+(?:\.\d+)?)\s*(million|mil|M|billion|bil|B)?', re.I)
        
        # Биржи для определения типа транзакции
        self.exchanges = [
            "binance", "coinbase", "kraken", "bitfinex", "huobi", "okx", "okex",
            "bybit", "kucoin", "gate.io", "gemini", "bitstamp", "ftx", "crypto.com"
        ]
        
        # Кэш
        self.cache: Dict[str, List] = {}
        self.cache_time: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=2)
        
        logger.info("🐦 Twitter Parser инициализирован")
    
    async def _find_working_instance(self) -> Optional[str]:
        """Найти работающий Nitter инстанс"""
        
        # ⚠️ Парсер отключён
        if not self.enabled:
            return None
        
        if self.working_instance:
            # Проверяем что он ещё работает
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.working_instance}/whale_alert",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            return self.working_instance
            except:
                self.working_instance = None
        
        async with aiohttp.ClientSession() as session:
            for instance in self.nitter_instances:
                try:
                    async with session.get(
                        f"{instance}/whale_alert",
                        timeout=aiohttp.ClientTimeout(total=5),
                        headers={"User-Agent": "Mozilla/5.0"}
                    ) as response:
                        if response.status == 200:
                            text = await response.text()
                            if 'timeline-item' in text or 'tweet-content' in text:
                                self.working_instance = instance
                                logger.info(f"🐦 Nitter инстанс: {instance}")
                                return instance
                except Exception as e:
                    logger.debug(f"Nitter {instance} failed: {e}")
                    continue
        
        logger.warning("⚠️ Нет работающих Nitter инстансов")
        return None
    
    async def _fetch_tweets(self, username: str, limit: int = 20) -> List[Dict]:
        """Получить твиты пользователя"""
        
        # Проверяем кэш
        cache_key = f"tweets_{username}"
        if cache_key in self.cache:
            if datetime.now() - self.cache_time.get(cache_key, datetime.min) < self.cache_duration:
                return self.cache[cache_key]
        
        instance = await self._find_working_instance()
        if not instance:
            return []
        
        tweets = []
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{instance}/{username}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.warning(f"🐦 Nitter returned {response.status} for @{username}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Парсим твиты
                    tweet_elements = soup.find_all('div', class_='timeline-item')[:limit]
                    
                    for element in tweet_elements:
                        try:
                            # Текст твита
                            content = element.find('div', class_='tweet-content')
                            if not content:
                                continue
                            text = content.get_text(strip=True)
                            
                            # Время
                            time_elem = element.find('span', class_='tweet-date')
                            timestamp = datetime.now()  # По умолчанию
                            if time_elem:
                                time_link = time_elem.find('a')
                                if time_link and time_link.get('title'):
                                    try:
                                        timestamp = datetime.strptime(
                                            time_link['title'], 
                                            "%b %d, %Y · %I:%M %p %Z"
                                        )
                                    except:
                                        pass
                            
                            tweets.append({
                                "text": text,
                                "author": username,
                                "timestamp": timestamp,
                            })
                            
                        except Exception as e:
                            continue
            
            # Кэшируем
            self.cache[cache_key] = tweets
            self.cache_time[cache_key] = datetime.now()
            
            logger.debug(f"🐦 @{username}: {len(tweets)} твитов")
            
        except Exception as e:
            logger.error(f"🐦 Twitter fetch error for @{username}: {e}")
        
        return tweets
    
    def _parse_whale_transaction(self, tweet: Dict) -> Optional[WhaleTransaction]:
        """Распарсить транзакцию кита из твита"""
        
        text = tweet.get("text", "")
        
        # Ищем сумму и монету
        amount_match = self.amount_pattern.search(text)
        if not amount_match:
            return None
        
        amount_str = amount_match.group(1).replace(",", "")
        coin = amount_match.group(2).upper()
        
        try:
            amount = float(amount_str)
        except:
            return None
        
        # Ищем сумму в USD
        usd_match = self.usd_pattern.search(text)
        amount_usd = 0
        if usd_match:
            usd_str = usd_match.group(1).replace(",", "")
            multiplier = 1
            if usd_match.group(2):
                mult_text = usd_match.group(2).lower()
                if mult_text in ["million", "mil", "m"]:
                    multiplier = 1_000_000
                elif mult_text in ["billion", "bil", "b"]:
                    multiplier = 1_000_000_000
            try:
                amount_usd = float(usd_str) * multiplier
            except:
                pass
        
        # Определяем тип транзакции
        text_lower = text.lower()
        tx_type = "unknown"
        from_wallet = "unknown"
        to_wallet = "unknown"
        
        # Проверяем направление
        for exchange in self.exchanges:
            if f"from {exchange}" in text_lower or f"from #{exchange}" in text_lower:
                from_wallet = exchange
                tx_type = "exchange_out"  # С биржи = бычий
            elif f"to {exchange}" in text_lower or f"to #{exchange}" in text_lower:
                to_wallet = exchange
                tx_type = "exchange_in"  # На биржу = медвежий
        
        if "transferred" in text_lower and tx_type == "unknown":
            tx_type = "whale_move"
        
        return WhaleTransaction(
            coin=coin,
            amount=amount,
            amount_usd=amount_usd,
            from_wallet=from_wallet,
            to_wallet=to_wallet,
            tx_type=tx_type,
            timestamp=tweet.get("timestamp", datetime.now()),
            source=tweet.get("author", ""),
            raw_text=text
        )
    
    def _analyze_news_sentiment(self, text: str) -> tuple:
        """Анализ сентимента новости"""
        
        text_lower = text.lower()
        
        # Бычьи слова
        bullish_words = [
            "surge", "soar", "rally", "breakout", "bullish", "moon", "pump",
            "buy", "accumulate", "adoption", "partnership", "etf approved",
            "institutional", "all-time high", "ath", "green", "gains",
            "record", "milestone", "upgrade", "launch"
        ]
        
        # Медвежьи слова
        bearish_words = [
            "crash", "dump", "plunge", "bearish", "sell", "liquidat",
            "hack", "scam", "ban", "regulation", "sec", "lawsuit",
            "bankrupt", "insolvent", "withdraw", "fear", "red",
            "losses", "down", "drop", "decline", "fall"
        ]
        
        # Критические слова
        critical_words = [
            "breaking", "urgent", "alert", "just in", "confirmed",
            "sec", "fed", "fomc", "trump", "biden", "ban", "etf",
            "halving", "approval", "reject"
        ]
        
        bullish_count = sum(1 for w in bullish_words if w in text_lower)
        bearish_count = sum(1 for w in bearish_words if w in text_lower)
        is_critical = any(w in text_lower for w in critical_words)
        
        # Определяем сентимент
        if bullish_count > bearish_count + 1:
            sentiment = "bullish"
        elif bearish_count > bullish_count + 1:
            sentiment = "bearish"
        else:
            sentiment = "neutral"
        
        # Определяем важность
        if is_critical:
            importance = "critical"
        elif bullish_count + bearish_count > 3:
            importance = "high"
        elif bullish_count + bearish_count > 1:
            importance = "medium"
        else:
            importance = "low"
        
        return sentiment, importance
    
    def _extract_coins(self, text: str) -> List[str]:
        """Извлечь упомянутые монеты"""
        
        coins = []
        patterns = [
            r'\$([A-Z]{2,5})\b',  # $BTC, $ETH
            r'\b(BTC|ETH|SOL|BNB|XRP|ADA|DOGE|AVAX|LINK|DOT|MATIC)\b',
            r'#(Bitcoin|Ethereum|Solana|BNB|XRP|Cardano|Dogecoin)\b',
        ]
        
        text_upper = text.upper()
        
        for pattern in patterns:
            matches = re.findall(pattern, text_upper, re.I)
            coins.extend([m.upper() for m in matches])
        
        # Нормализация названий
        name_map = {
            "BITCOIN": "BTC",
            "ETHEREUM": "ETH",
            "SOLANA": "SOL",
            "CARDANO": "ADA",
            "DOGECOIN": "DOGE",
        }
        
        normalized = []
        for coin in coins:
            normalized.append(name_map.get(coin, coin))
        
        # Убираем дубликаты
        return list(set(normalized))
    
    async def get_whale_transactions(self, hours: int = 4) -> List[WhaleTransaction]:
        """Получить транзакции китов за последние N часов"""
        
        # ⚠️ Парсер отключён
        if not self.enabled:
            return []
        
        transactions = []
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        for account in self.whale_accounts:
            tweets = await self._fetch_tweets(account, limit=30)
            
            for tweet in tweets:
                if tweet.get("timestamp", datetime.now()) < cutoff_time:
                    continue
                
                tx = self._parse_whale_transaction(tweet)
                if tx and tx.amount_usd > 1_000_000:  # Только > $1M
                    transactions.append(tx)
            
            await asyncio.sleep(0.5)  # Rate limit
        
        # Сортируем по времени
        transactions.sort(key=lambda x: x.timestamp, reverse=True)
        
        logger.info(f"🐋 Найдено {len(transactions)} whale транзакций")
        
        return transactions
    
    async def get_crypto_news(self, hours: int = 2) -> List[TwitterNews]:
        """Получить крипто новости"""
        
        # ⚠️ Парсер отключён
        if not self.enabled:
            logger.debug("Twitter Parser отключён — возвращаем пустой список")
            return []
        
        news = []
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        for account in self.news_accounts:
            tweets = await self._fetch_tweets(account, limit=20)
            
            for tweet in tweets:
                if tweet.get("timestamp", datetime.now()) < cutoff_time:
                    continue
                
                text = tweet.get("text", "")
                sentiment, importance = self._analyze_news_sentiment(text)
                coins = self._extract_coins(text)
                
                news_item = TwitterNews(
                    text=text[:500],
                    author=tweet.get("author", ""),
                    timestamp=tweet.get("timestamp", datetime.now()),
                    sentiment=sentiment,
                    importance=importance,
                    coins_mentioned=coins
                )
                news.append(news_item)
            
            await asyncio.sleep(0.5)
        
        # Сортируем по важности и времени
        importance_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        news.sort(key=lambda x: (importance_order.get(x.importance, 4), -x.timestamp.timestamp()))
        
        logger.info(f"📰 Найдено {len(news)} новостей")
        
        return news
    
    async def get_whale_summary(self) -> Dict:
        """Сводка по китам для Whale AI"""
        
        # ⚠️ Парсер отключён — возвращаем пустую сводку
        if not self.enabled:
            return {
                "total_volume_usd": 0,
                "exchange_inflow": 0,
                "exchange_outflow": 0,
                "net_flow": 0,
                "sentiment": "neutral",
                "top_transactions": [],
                "by_coin": {},
                "status": "disabled"
            }
        
        transactions = await self.get_whale_transactions(hours=4)
        
        if not transactions:
            return {
                "total_volume_usd": 0,
                "exchange_inflow": 0,
                "exchange_outflow": 0,
                "net_flow": 0,
                "sentiment": "neutral",
                "top_transactions": [],
                "by_coin": {}
            }
        
        # Считаем потоки
        inflow = sum(tx.amount_usd for tx in transactions if tx.tx_type == "exchange_in")
        outflow = sum(tx.amount_usd for tx in transactions if tx.tx_type == "exchange_out")
        total = sum(tx.amount_usd for tx in transactions)
        net_flow = outflow - inflow
        
        # По монетам
        by_coin = {}
        for tx in transactions:
            if tx.coin not in by_coin:
                by_coin[tx.coin] = {"inflow": 0, "outflow": 0, "moves": 0}
            
            if tx.tx_type == "exchange_in":
                by_coin[tx.coin]["inflow"] += tx.amount_usd
            elif tx.tx_type == "exchange_out":
                by_coin[tx.coin]["outflow"] += tx.amount_usd
            else:
                by_coin[tx.coin]["moves"] += tx.amount_usd
        
        # Определяем сентимент
        if net_flow > 50_000_000:
            sentiment = "bullish"  # Отток с бирж
        elif net_flow < -50_000_000:
            sentiment = "bearish"  # Приток на биржи
        else:
            sentiment = "neutral"
        
        return {
            "total_volume_usd": total,
            "exchange_inflow": inflow,
            "exchange_outflow": outflow,
            "net_flow": net_flow,
            "sentiment": sentiment,
            "top_transactions": transactions[:5],
            "by_coin": by_coin,
            "tx_count": len(transactions)
        }
    
    def get_status_text(self) -> str:
        """Статус для Telegram"""
        
        instance_status = "✅ " + self.working_instance.split("//")[1] if self.working_instance else "❌ не найден"
        
        return f"""🐦 *Twitter Parser*

*Nitter:* {instance_status}
*Whale аккаунты:* {', '.join(self.whale_accounts)}
*News аккаунты:* {', '.join(self.news_accounts)}
*В кэше:* {len(self.cache)} запросов
"""


# Singleton
twitter_parser = TwitterParser()


async def get_whale_data() -> Dict:
    """Публичная функция для получения данных китов"""
    return await twitter_parser.get_whale_summary()


async def get_twitter_news() -> List[TwitterNews]:
    """Публичная функция для получения новостей"""
    return await twitter_parser.get_crypto_news()
