"""
🆕 LISTING HUNTER MODULE
Охотник за новыми листингами монет

Источники:
1. Binance Announcements
2. Bybit Announcements  
3. CoinMarketCap New Listings
4. CoinGecko Recently Added

Стратегии:
1. Pre-Listing — монета листится на крупной бирже, покупаем на мелкой
2. Listing Scalp — покупаем в момент листинга на Bybit
3. Launchpad — уведомляем о Launchpad/Launchpool

Режимы:
- signal: только уведомления
- auto: автоматическая торговля (нужен API)
"""
import asyncio
import re
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import feedparser

from app.core.logger import logger
from app.modules.base_module import BaseModule, ModuleSignal


class ListingType(Enum):
    PRE_LISTING = "pre_listing"      # Анонс, монета ещё не торгуется
    LISTING_SCALP = "listing_scalp"  # Листинг прямо сейчас
    LAUNCHPAD = "launchpad"          # Launchpad/Launchpool
    PERPETUAL = "perpetual"          # Фьючерсы добавлены
    UNKNOWN = "unknown"


class ListingSource(Enum):
    BINANCE = "binance"
    BYBIT = "bybit"
    COINMARKETCAP = "coinmarketcap"
    COINGECKO = "coingecko"


@dataclass
class ListingEvent:
    """Обнаруженный листинг"""
    id: str
    source: ListingSource
    listing_type: ListingType
    
    # Информация о монете
    symbol: str                      # Тикер (например "PEPE")
    name: str                        # Название (например "Pepe")
    
    # Информация о листинге
    exchange: str                    # Биржа листинга
    listing_date: Optional[datetime] = None  # Когда листинг
    announced_at: datetime = field(default_factory=datetime.now)
    
    # Дополнительно
    title: str = ""                  # Заголовок объявления
    url: str = ""                    # Ссылка на объявление
    
    # Торговая информация
    is_on_bybit: bool = False        # Уже на Bybit?
    current_price: Optional[float] = None
    other_exchanges: List[str] = field(default_factory=list)
    
    # Статус
    notified: bool = False
    traded: bool = False
    profit_percent: Optional[float] = None


@dataclass
class ListingTrade:
    """Сделка по листингу"""
    id: str
    listing_id: str
    symbol: str
    strategy: ListingType
    
    # Сделка
    entry_price: float
    current_price: float = 0.0
    exit_price: Optional[float] = None
    quantity: float = 0.0
    size_usdt: float = 0.0
    
    # TP/SL
    take_profit: float = 0.0
    stop_loss: float = 0.0
    
    # Время
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    
    # Результат
    status: str = "open"  # open, closed, cancelled
    pnl_percent: float = 0.0
    pnl_usdt: float = 0.0


@dataclass
class ListingConfig:
    """Конфигурация Listing Hunter"""
    enabled: bool = True
    mode: str = "signal"             # "signal" или "auto"
    
    # Интервалы проверки (секунды)
    check_interval_binance: int = 60
    check_interval_bybit: int = 60
    check_interval_cmc: int = 300    # CMC реже (лимиты API)
    check_interval_coingecko: int = 300
    
    # Торговые настройки (для auto режима)
    trade_size_usdt: float = 50.0    # Размер сделки
    max_trades_per_day: int = 5       # Макс сделок в день
    
    # Listing Scalp настройки
    scalp_tp_percent: float = 20.0   # Take Profit +20%
    scalp_sl_percent: float = 5.0    # Stop Loss -5%
    scalp_max_hold_minutes: int = 60  # Макс время удержания
    
    # Фильтры
    min_market_cap: float = 0        # Мин капитализация (0 = любая)
    exclude_symbols: List[str] = field(default_factory=lambda: [
        "BTC", "ETH", "USDT", "USDC", "BNB", "XRP", "SOL"  # Крупные монеты
    ])
    
    # API ключи для внешних сервисов
    cmc_api_key: str = ""            # CoinMarketCap API Key


class ListingHunter(BaseModule):
    """
    🆕 Listing Hunter — Охотник за листингами
    
    Мониторит анонсы бирж и находит новые листинги.
    Может автоматически торговать или просто уведомлять.
    """
    
    name = "listing_hunter"
    
    # Ключевые слова для детекции
    LISTING_KEYWORDS = [
        # English
        "will list", "listing", "lists", "to list",
        "new listing", "adds", "adding",
        "spot trading", "new trading pair",
        "perpetual", "perp contract",
        "launchpad", "launchpool", "token sale",
        # Patterns
        "trading starts", "trading begins",
    ]
    
    LAUNCHPAD_KEYWORDS = [
        "launchpad", "launchpool", "token sale",
        "ieo", "ido", "farming", "staking event"
    ]
    
    # Regex для извлечения тикера
    TICKER_PATTERNS = [
        r'\(([A-Z]{2,10})\)',           # (PEPE)
        r'([A-Z]{2,10})/USDT',          # PEPE/USDT
        r'([A-Z]{2,10})USDT',           # PEPEUSDT
        r'list\s+([A-Z]{2,10})',        # list PEPE
        r'lists\s+([A-Z]{2,10})',       # lists PEPE
        r'add\s+([A-Z]{2,10})',         # add PEPE
        r'([A-Z]{2,10})\s+listing',     # PEPE listing
        r'([A-Z]{2,10})\s+perpetual',   # PEPE perpetual
    ]
    
    def __init__(self):
        self.enabled = True
        self.config = ListingConfig()
        
        # Кэш обработанных объявлений (чтобы не дублировать)
        self.processed_ids: Set[str] = set()
        
        # Обнаруженные листинги
        self.listings: Dict[str, ListingEvent] = {}
        
        # Активные сделки
        self.trades: Dict[str, ListingTrade] = {}
        
        # История
        self.history: List[ListingEvent] = []
        self.trade_history: List[ListingTrade] = []
        
        # Статистика
        self.stats = {
            "listings_detected": 0,
            "pre_listings": 0,
            "scalp_opportunities": 0,
            "launchpads": 0,
            "trades_executed": 0,
            "trades_profitable": 0,
            "total_profit_usdt": 0.0,
            "today_listings": 0,
            "today_trades": 0,
            "last_check": None,
        }
        
        # Bybit symbols (для проверки доступности)
        self.bybit_symbols: Set[str] = set()
        self.last_symbols_update: Optional[datetime] = None
        
        logger.info("🆕 Listing Hunter initialized")
    
    def _generate_id(self, text: str) -> str:
        """Генерация уникального ID для объявления"""
        return hashlib.md5(text.encode()).hexdigest()[:12]
    
    def _extract_ticker(self, text: str) -> Optional[str]:
        """Извлечь тикер монеты из текста"""
        
        text_upper = text.upper()
        
        for pattern in self.TICKER_PATTERNS:
            match = re.search(pattern, text_upper)
            if match:
                ticker = match.group(1)
                
                # Фильтруем служебные слова
                if ticker in ["THE", "AND", "FOR", "NEW", "ALL", "USD", "SPOT", "WILL"]:
                    continue
                
                # Фильтруем исключённые символы
                if ticker in self.config.exclude_symbols:
                    continue
                
                return ticker
        
        return None
    
    def _detect_listing_type(self, text: str) -> ListingType:
        """Определить тип листинга"""
        
        text_lower = text.lower()
        
        # Launchpad/Launchpool
        for keyword in self.LAUNCHPAD_KEYWORDS:
            if keyword in text_lower:
                return ListingType.LAUNCHPAD
        
        # Perpetual (фьючерсы)
        if "perpetual" in text_lower or "perp" in text_lower:
            return ListingType.PERPETUAL
        
        # Обычный листинг
        if "will list" in text_lower or "to list" in text_lower:
            return ListingType.PRE_LISTING
        
        if "trading starts" in text_lower or "now available" in text_lower:
            return ListingType.LISTING_SCALP
        
        return ListingType.UNKNOWN
    
    def _parse_listing_date(self, text: str) -> Optional[datetime]:
        """Попытаться извлечь дату листинга из текста"""
        
        # Паттерны дат
        patterns = [
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',  # 2025-01-28 10:00
            r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})',  # 01/28/2025 10:00
            r'(\w+\s+\d{1,2},?\s+\d{4})',          # January 28, 2025
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    date_str = match.group(1)
                    # Попробуем разные форматы
                    for fmt in [
                        "%Y-%m-%d %H:%M",
                        "%m/%d/%Y %H:%M", 
                        "%B %d, %Y",
                        "%B %d %Y"
                    ]:
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            continue
                except Exception:
                    pass
        
        return None
    
    async def update_bybit_symbols(self):
        """Обновить список символов на Bybit"""
        
        # Обновляем раз в 10 минут
        if self.last_symbols_update:
            elapsed = (datetime.now() - self.last_symbols_update).seconds
            if elapsed < 600:
                return
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.bybit.com/v5/market/instruments-info"
                params = {"category": "spot"}
                
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("retCode") == 0:
                            instruments = data.get("result", {}).get("list", [])
                            
                            self.bybit_symbols = set()
                            for inst in instruments:
                                symbol = inst.get("baseCoin", "")
                                if symbol:
                                    self.bybit_symbols.add(symbol)
                            
                            self.last_symbols_update = datetime.now()
                            logger.debug(f"🆕 Updated Bybit symbols: {len(self.bybit_symbols)}")
        
        except Exception as e:
            logger.error(f"Update Bybit symbols error: {e}")
    
    async def check_binance_announcements(self) -> List[ListingEvent]:
        """Проверить анонсы Binance"""
        
        listings = []
        
        try:
            async with aiohttp.ClientSession() as session:
                # Binance Announcements API
                url = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
                params = {
                    "type": 1,
                    "pageNo": 1,
                    "pageSize": 20
                }
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                async with session.get(url, params=params, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        articles = data.get("data", {}).get("catalogs", [{}])[0].get("articles", [])
                        
                        for article in articles[:20]:
                            title = article.get("title", "")
                            code = article.get("code", "")
                            
                            # Проверяем ключевые слова
                            if not any(kw in title.lower() for kw in self.LISTING_KEYWORDS):
                                continue
                            
                            # Генерируем ID
                            listing_id = self._generate_id(title + code)
                            
                            # Уже обработали?
                            if listing_id in self.processed_ids:
                                continue
                            
                            # Извлекаем тикер
                            ticker = self._extract_ticker(title)
                            if not ticker:
                                continue
                            
                            # Определяем тип
                            listing_type = self._detect_listing_type(title)
                            
                            # Парсим дату
                            listing_date = self._parse_listing_date(title)
                            
                            # Создаём событие
                            event = ListingEvent(
                                id=listing_id,
                                source=ListingSource.BINANCE,
                                listing_type=listing_type,
                                symbol=ticker,
                                name=ticker,
                                exchange="Binance",
                                listing_date=listing_date,
                                title=title,
                                url=f"https://www.binance.com/en/support/announcement/{code}",
                                is_on_bybit=ticker in self.bybit_symbols,
                            )
                            
                            listings.append(event)
                            self.processed_ids.add(listing_id)
                            
                            logger.info(f"🆕 Binance listing detected: {ticker} ({listing_type.value})")
        
        except Exception as e:
            logger.error(f"Binance announcements error: {e}")
        
        return listings
    
    async def check_bybit_announcements(self) -> List[ListingEvent]:
        """Проверить анонсы Bybit"""
        
        listings = []
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.bybit.com/v5/announcements/index"
                params = {
                    "locale": "en-US",
                    "limit": 20
                }
                
                async with session.get(url, params=params, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("retCode") == 0:
                            items = data.get("result", {}).get("list", [])
                            
                            for item in items:
                                title = item.get("title", "")
                                url_link = item.get("url", "")
                                
                                # Проверяем ключевые слова
                                if not any(kw in title.lower() for kw in self.LISTING_KEYWORDS):
                                    continue
                                
                                # Генерируем ID
                                listing_id = self._generate_id(title + str(item.get("id", "")))
                                
                                # Уже обработали?
                                if listing_id in self.processed_ids:
                                    continue
                                
                                # Извлекаем тикер
                                ticker = self._extract_ticker(title)
                                if not ticker:
                                    continue
                                
                                # Определяем тип
                                listing_type = self._detect_listing_type(title)
                                
                                # Bybit листинг = можем торговать!
                                if "trading starts" in title.lower() or "now available" in title.lower():
                                    listing_type = ListingType.LISTING_SCALP
                                
                                # Парсим дату
                                listing_date = self._parse_listing_date(title)
                                
                                # Создаём событие
                                event = ListingEvent(
                                    id=listing_id,
                                    source=ListingSource.BYBIT,
                                    listing_type=listing_type,
                                    symbol=ticker,
                                    name=ticker,
                                    exchange="Bybit",
                                    listing_date=listing_date,
                                    title=title,
                                    url=url_link,
                                    is_on_bybit=True,
                                )
                                
                                listings.append(event)
                                self.processed_ids.add(listing_id)
                                
                                logger.info(f"🆕 Bybit listing detected: {ticker} ({listing_type.value})")
        
        except Exception as e:
            logger.error(f"Bybit announcements error: {e}")
        
        return listings
    
    async def check_coinmarketcap(self) -> List[ListingEvent]:
        """Проверить новые монеты на CoinMarketCap"""
        
        listings = []
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing"
                params = {
                    "start": 1,
                    "limit": 20,
                    "sortBy": "date_added",
                    "sortType": "desc"
                }
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                async with session.get(url, params=params, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        coins = data.get("data", {}).get("cryptoCurrencyList", [])
                        
                        for coin in coins:
                            symbol = coin.get("symbol", "")
                            name = coin.get("name", "")
                            date_added = coin.get("dateAdded", "")
                            
                            # Только последние 24 часа
                            if date_added:
                                try:
                                    added_dt = datetime.fromisoformat(date_added.replace("Z", "+00:00"))
                                    if datetime.now(timezone.utc) - added_dt > timedelta(days=1):
                                        continue
                                except:
                                    pass
                            
                            # Фильтруем
                            if symbol in self.config.exclude_symbols:
                                continue
                            
                            listing_id = self._generate_id(f"cmc_{symbol}_{date_added}")
                            
                            if listing_id in self.processed_ids:
                                continue
                            
                            event = ListingEvent(
                                id=listing_id,
                                source=ListingSource.COINMARKETCAP,
                                listing_type=ListingType.PRE_LISTING,
                                symbol=symbol,
                                name=name,
                                exchange="CoinMarketCap",
                                title=f"New on CMC: {name} ({symbol})",
                                is_on_bybit=symbol in self.bybit_symbols,
                            )
                            
                            listings.append(event)
                            self.processed_ids.add(listing_id)
                            
                            logger.info(f"🆕 CMC new coin: {symbol}")
        
        except Exception as e:
            logger.error(f"CoinMarketCap error: {e}")
        
        return listings
    
    async def check_coingecko(self) -> List[ListingEvent]:
        """Проверить новые монеты на CoinGecko"""
        
        listings = []
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.coingecko.com/api/v3/coins/list"
                params = {"include_platform": "false"}
                
                headers = {"accept": "application/json"}
                
                async with session.get(url, params=params, headers=headers, timeout=15) as resp:
                    if resp.status == 200:
                        logger.debug("CoinGecko check completed")
        
        except Exception as e:
            logger.error(f"CoinGecko error: {e}")
        
        return listings
    
    async def get_price_on_other_exchanges(self, symbol: str) -> Dict[str, float]:
        """Получить цену на других биржах (через CoinGecko)"""
        
        prices = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.coingecko.com/api/v3/simple/price"
                params = {
                    "ids": symbol.lower(),
                    "vs_currencies": "usd"
                }
                
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if symbol.lower() in data:
                            prices["coingecko"] = data[symbol.lower()].get("usd", 0)
        
        except Exception as e:
            logger.debug(f"Price check error for {symbol}: {e}")
        
        return prices
    
    async def _is_tradeable_on_bybit(self, symbol: str) -> bool:
        """Проверить что монета торгуется на Bybit"""
        try:
            from app.trading.bybit.client import bybit_client
            price = await bybit_client.get_price(f"{symbol}USDT")
            return price is not None and price > 0
        except:
            return False
    
    async def process_listing(self, listing: ListingEvent) -> Optional[ModuleSignal]:
        """Обработать обнаруженный листинг"""
        
        # ФИЛЬТР PERPETUAL: пропускаем фьючерсы!
        if listing.listing_type == ListingType.PERPETUAL:
            logger.debug(f"Skip perpetual listing: {listing.symbol}")
            return None
        
        if "perpetual" in listing.title.lower():
            logger.debug(f"Skip perpetual listing (title): {listing.symbol}")
            return None
        
        if "futures" in listing.title.lower():
            logger.debug(f"Skip futures listing: {listing.symbol}")
            return None
        
        # Проверяем не обработан ли уже этот листинг
        if listing.id in self.listings:
            return None  # Уже обработан
        
        # Проверяем по символу - не было ли уже такого листинга недавно
        for existing in self.history[-50:]:  # Проверяем последние 50
            if existing.symbol == listing.symbol and existing.exchange == listing.exchange:
                # Листинг с таким символом уже есть
                return None
        
        # Сохраняем
        self.listings[listing.id] = listing
        self.history.append(listing)
        
        # Обновляем статистику
        self.stats["listings_detected"] += 1
        self.stats["today_listings"] += 1
        
        if listing.listing_type == ListingType.PRE_LISTING:
            self.stats["pre_listings"] += 1
        elif listing.listing_type == ListingType.LISTING_SCALP:
            self.stats["scalp_opportunities"] += 1
        elif listing.listing_type == ListingType.LAUNCHPAD:
            self.stats["launchpads"] += 1
        
        # Проверяем цену на других биржах
        other_prices = await self.get_price_on_other_exchanges(listing.symbol)
        if other_prices:
            listing.current_price = list(other_prices.values())[0]
            listing.other_exchanges = list(other_prices.keys())
        
        # Создаём сигнал
        signal = ModuleSignal(
            module_name=self.name,
            symbol=listing.symbol,
            direction="LISTING",
            entry_price=listing.current_price or 0,
            stop_loss=0,
            take_profit=0,
            reason=f"{listing.listing_type.value}: {listing.exchange}",
            confidence=0.8,
        )
        
        # Auto режим: торгуем если можем
        if self.config.mode == "auto":
            if listing.listing_type == ListingType.LISTING_SCALP and listing.is_on_bybit:
                await self._execute_scalp_trade(listing)
        
        listing.notified = True
        
        return signal
    
    async def _execute_scalp_trade(self, listing: ListingEvent):
        """Выполнить скальп-сделку (для auto режима)"""
        
        # Проверяем лимиты
        if self.stats["today_trades"] >= self.config.max_trades_per_day:
            logger.warning("🆕 Daily trade limit reached")
            return
        
        try:
            # Получаем цену на Bybit
            from app.trading.bybit.client import bybit_client
            
            symbol_pair = f"{listing.symbol}USDT"
            price = await bybit_client.get_price(symbol_pair)
            
            if not price:
                logger.warning(f"🆕 No price for {symbol_pair}")
                return
            
            # Рассчитываем TP/SL
            tp = price * (1 + self.config.scalp_tp_percent / 100)
            sl = price * (1 - self.config.scalp_sl_percent / 100)
            
            # Создаём сделку
            trade = ListingTrade(
                id=f"LH_{listing.symbol}_{datetime.now().strftime('%H%M%S')}",
                listing_id=listing.id,
                symbol=listing.symbol,
                strategy=listing.listing_type,
                entry_price=price,
                current_price=price,
                size_usdt=self.config.trade_size_usdt,
                take_profit=tp,
                stop_loss=sl,
            )
            
            # Paper trading пока
            logger.info(f"🆕 [PAPER] Scalp trade: BUY {listing.symbol} @ {price:.4f}")
            
            self.trades[trade.id] = trade
            self.stats["trades_executed"] += 1
            self.stats["today_trades"] += 1
            
            listing.traded = True
        
        except Exception as e:
            logger.error(f"Scalp trade error: {e}")
    
    async def check_open_trades(self, prices: Dict[str, float]):
        """Проверить открытые сделки на TP/SL"""
        
        closed = []
        
        for trade_id, trade in self.trades.items():
            symbol_pair = f"{trade.symbol}USDT"
            price = prices.get(symbol_pair) or prices.get(trade.symbol, 0)
            
            if not price:
                continue
            
            trade.current_price = price
            trade.pnl_percent = (price - trade.entry_price) / trade.entry_price * 100
            trade.pnl_usdt = (trade.pnl_percent / 100) * trade.size_usdt
            
            should_close = False
            reason = ""
            
            # TP
            if price >= trade.take_profit:
                should_close = True
                reason = "Take Profit"
            
            # SL
            elif price <= trade.stop_loss:
                should_close = True
                reason = "Stop Loss"
            
            # Время
            elif (datetime.now() - trade.opened_at).seconds > self.config.scalp_max_hold_minutes * 60:
                should_close = True
                reason = "Max hold time"
            
            if should_close:
                trade.status = "closed"
                trade.closed_at = datetime.now()
                trade.exit_price = price
                
                self.trade_history.append(trade)
                closed.append(trade_id)
                
                self.stats["total_profit_usdt"] += trade.pnl_usdt
                if trade.pnl_percent > 0:
                    self.stats["trades_profitable"] += 1
                
                logger.info(f"🆕 Trade closed: {trade.symbol} {reason} "
                           f"PnL: {trade.pnl_percent:+.2f}%")
        
        for trade_id in closed:
            del self.trades[trade_id]
    
    async def get_signals(self, market_data: Dict) -> List[ModuleSignal]:
        """Получить сигналы от Listing Hunter"""
        
        if not self.enabled:
            return []
        
        signals = []
        
        # Обновляем список символов Bybit
        await self.update_bybit_symbols()
        
        # Проверяем источники
        binance_listings = await self.check_binance_announcements()
        bybit_listings = await self.check_bybit_announcements()
        cmc_listings = await self.check_coinmarketcap()
        
        all_listings = binance_listings + bybit_listings + cmc_listings
        
        # Обрабатываем новые листинги
        for listing in all_listings:
            signal = await self.process_listing(listing)
            if signal:
                signals.append(signal)
        
        # Проверяем открытые сделки
        prices = market_data.get("prices", {})
        await self.check_open_trades(prices)
        
        self.stats["last_check"] = datetime.now()
        
        return signals
    
    async def get_status(self) -> Dict:
        """Статус Listing Hunter"""
        
        win_rate = 0
        if self.stats["trades_executed"] > 0:
            win_rate = self.stats["trades_profitable"] / self.stats["trades_executed"] * 100
        
        recent_listings = sorted(
            self.history[-10:],
            key=lambda x: x.announced_at,
            reverse=True
        )
        
        return {
            "enabled": self.enabled,
            "mode": self.config.mode,
            "stats": {
                "listings_detected": self.stats["listings_detected"],
                "pre_listings": self.stats["pre_listings"],
                "scalp_opportunities": self.stats["scalp_opportunities"],
                "launchpads": self.stats["launchpads"],
                "trades_executed": self.stats["trades_executed"],
                "win_rate": win_rate,
                "total_profit_usdt": self.stats["total_profit_usdt"],
                "today_listings": self.stats["today_listings"],
                "today_trades": self.stats["today_trades"],
            },
            "active_trades": len(self.trades),
            "recent_listings": [
                {
                    "symbol": l.symbol,
                    "exchange": l.exchange,
                    "type": l.listing_type.value,
                    "on_bybit": l.is_on_bybit,
                }
                for l in recent_listings[:5]
            ],
            "bybit_symbols_count": len(self.bybit_symbols),
            "last_check": self.stats["last_check"],
        }
    
    def get_status_text(self) -> str:
        """Текст для Telegram"""
        
        mode_emoji = "🤖" if self.config.mode == "auto" else "📢"
        mode_text = "Авто" if self.config.mode == "auto" else "Сигналы"
        
        win_rate = 0
        if self.stats["trades_executed"] > 0:
            win_rate = self.stats["trades_profitable"] / self.stats["trades_executed"] * 100
        
        # Последние листинги
        recent = ""
        recent_listings = sorted(
            self.history[-5:],
            key=lambda x: x.announced_at,
            reverse=True
        )
        
        for listing in recent_listings:
            type_emoji = {
                ListingType.PRE_LISTING: "📋",
                ListingType.LISTING_SCALP: "⚡",
                ListingType.LAUNCHPAD: "🚀",
                ListingType.PERPETUAL: "📊",
            }.get(listing.listing_type, "❓")
            
            bybit_status = "✅" if listing.is_on_bybit else "❌"
            
            recent += f"\n   {type_emoji} {listing.symbol} ({listing.exchange}) {bybit_status}"
        
        if not recent:
            recent = "\n   Пока нет обнаруженных листингов"
        
        # Активные сделки
        trades_text = ""
        for trade in self.trades.values():
            pnl_emoji = "📈" if trade.pnl_percent > 0 else "📉"
            trades_text += f"\n   {trade.symbol}: {pnl_emoji} {trade.pnl_percent:+.2f}%"
        
        if not trades_text:
            trades_text = "\n   Нет активных сделок"
        
        last_check = self.stats['last_check'].strftime('%H:%M:%S') if self.stats['last_check'] else 'N/A'
        
        text = f"""
🆕 *LISTING HUNTER*

{'🟢 Активен' if self.enabled else '🔴 Остановлен'} | {mode_emoji} {mode_text}

📊 *Статистика:*
├── Листингов найдено: {self.stats['listings_detected']}
├── Pre-listings: {self.stats['pre_listings']}
├── Scalp возможностей: {self.stats['scalp_opportunities']}
├── Launchpad: {self.stats['launchpads']}
└── Сегодня: {self.stats['today_listings']}

💰 *Торговля:*
├── Сделок: {self.stats['trades_executed']}
├── Win Rate: {win_rate:.1f}%
└── Профит: ${self.stats['total_profit_usdt']:.2f}

📋 *Последние листинги:*{recent}

📈 *Активные сделки:*{trades_text}

⏰ Последняя проверка: {last_check}
"""
        return text
    
    def set_mode(self, mode: str) -> bool:
        """Установить режим работы"""
        if mode in ["signal", "auto"]:
            self.config.mode = mode
            logger.info(f"🆕 Listing Hunter mode: {mode}")
            return True
        return False


# Синглтон
listing_hunter = ListingHunter()
