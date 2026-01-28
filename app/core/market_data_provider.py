"""
Market Data Provider — получение реальных данных рынка
Единая точка для получения цен, RSI, Fear & Greed
"""
import asyncio
import aiohttp
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.core.logger import logger


@dataclass
class MarketSnapshot:
    """Снимок состояния рынка"""
    btc_price: float = 0
    eth_price: float = 0
    sol_price: float = 0
    
    btc_rsi: float = 50
    eth_rsi: float = 50
    sol_rsi: float = 50
    
    fear_greed: int = 50
    fear_greed_text: str = "Нейтрально"
    
    btc_change_24h: float = 0
    eth_change_24h: float = 0
    
    timestamp: datetime = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now()


class MarketDataProvider:
    """
    Провайдер рыночных данных
    
    Кэширует данные на 1 минуту чтобы не спамить API
    """
    
    CACHE_TTL = timedelta(minutes=1)
    
    def __init__(self):
        self._cache: Optional[MarketSnapshot] = None
        self._cache_time: Optional[datetime] = None
        
        logger.info("📊 MarketDataProvider initialized")
    
    async def get_snapshot(self, force_refresh: bool = False) -> MarketSnapshot:
        """Получить актуальный снимок рынка"""
        
        # Проверяем кэш
        if not force_refresh and self._cache and self._cache_time:
            if datetime.now() - self._cache_time < self.CACHE_TTL:
                return self._cache
        
        # Получаем свежие данные
        snapshot = MarketSnapshot()
        
        try:
            # Параллельно запрашиваем всё
            prices_task = self._fetch_prices()
            fg_task = self._fetch_fear_greed()
            
            prices, fear_greed = await asyncio.gather(
                prices_task, 
                fg_task,
                return_exceptions=True
            )
            
            # Обрабатываем цены
            if isinstance(prices, dict):
                snapshot.btc_price = prices.get('BTC', 0)
                snapshot.eth_price = prices.get('ETH', 0)
                snapshot.sol_price = prices.get('SOL', 0)
                snapshot.btc_change_24h = prices.get('BTC_change', 0)
                snapshot.eth_change_24h = prices.get('ETH_change', 0)
            
            # Обрабатываем Fear & Greed
            if isinstance(fear_greed, tuple):
                snapshot.fear_greed = fear_greed[0]
                snapshot.fear_greed_text = fear_greed[1]
            
            # Получаем RSI (после получения цен)
            rsi_data = await self._calculate_rsi()
            if rsi_data:
                snapshot.btc_rsi = rsi_data.get('BTC', 50)
                snapshot.eth_rsi = rsi_data.get('ETH', 50)
                snapshot.sol_rsi = rsi_data.get('SOL', 50)
            
            # Сохраняем в кэш
            self._cache = snapshot
            self._cache_time = datetime.now()
            
            logger.debug(f"📊 Market snapshot: BTC=${snapshot.btc_price:,.0f}, RSI={snapshot.btc_rsi:.0f}")
            
        except Exception as e:
            logger.error(f"Market data error: {e}")
            # Возвращаем кэш если есть
            if self._cache:
                return self._cache
        
        return snapshot
    
    async def _fetch_prices(self) -> Dict:
        """Получить цены с Bybit"""
        prices = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                # Bybit API v5
                url = "https://api.bybit.com/v5/market/tickers"
                params = {"category": "linear"}
                
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get('retCode') == 0:
                            for item in data.get('result', {}).get('list', []):
                                symbol = item.get('symbol', '')
                                
                                if symbol == 'BTCUSDT':
                                    prices['BTC'] = float(item.get('lastPrice', 0))
                                    prices['BTC_change'] = float(item.get('price24hPcnt', 0)) * 100
                                elif symbol == 'ETHUSDT':
                                    prices['ETH'] = float(item.get('lastPrice', 0))
                                    prices['ETH_change'] = float(item.get('price24hPcnt', 0)) * 100
                                elif symbol == 'SOLUSDT':
                                    prices['SOL'] = float(item.get('lastPrice', 0))
                                    
        except Exception as e:
            logger.error(f"Fetch prices error: {e}")
        
        return prices
    
    async def _fetch_fear_greed(self) -> Tuple[int, str]:
        """Получить Fear & Greed Index"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.alternative.me/fng/"
                
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get('data'):
                            value = int(data['data'][0].get('value', 50))
                            classification = data['data'][0].get('value_classification', 'Neutral')
                            
                            # Переводим на русский
                            ru_class = {
                                'Extreme Fear': 'Сильный страх',
                                'Fear': 'Страх',
                                'Neutral': 'Нейтрально',
                                'Greed': 'Жадность',
                                'Extreme Greed': 'Сильная жадность'
                            }.get(classification, 'Нейтрально')
                            
                            return (value, ru_class)
                            
        except Exception as e:
            logger.error(f"Fetch Fear & Greed error: {e}")
        
        return (50, 'Нейтрально')
    
    async def _calculate_rsi(self) -> Dict[str, float]:
        """Рассчитать RSI для основных монет"""
        rsi_values = {}
        
        try:
            from app.strategies.indicators import TechnicalIndicators
            
            indicators = TechnicalIndicators()
            
            async with aiohttp.ClientSession() as session:
                for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
                    try:
                        # Bybit klines API
                        url = "https://api.bybit.com/v5/market/kline"
                        params = {
                            "category": "linear",
                            "symbol": symbol,
                            "interval": "15",  # 15 минут
                            "limit": 50
                        }
                        
                        async with session.get(url, params=params, timeout=10) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                
                                if data.get('retCode') == 0:
                                    klines = data.get('result', {}).get('list', [])
                                    
                                    if len(klines) >= 20:
                                        # Bybit возвращает в обратном порядке
                                        closes = [float(k[4]) for k in reversed(klines)]
                                        
                                        import pandas as pd
                                        series = pd.Series(closes)
                                        rsi = indicators.rsi(series, 14)
                                        
                                        coin = symbol.replace('USDT', '')
                                        rsi_values[coin] = rsi
                                        
                    except Exception as e:
                        logger.debug(f"RSI calc error for {symbol}: {e}")
                        
        except Exception as e:
            logger.error(f"Calculate RSI error: {e}")
        
        return rsi_values
    
    def get_rsi_status(self, rsi: float) -> Tuple[str, str]:
        """Получить статус и эмодзи для RSI"""
        if rsi < 25:
            return ("🟢", "сильно перепродан")
        elif rsi < 35:
            return ("🟡", "перепродан")
        elif rsi < 45:
            return ("⚪", "ниже среднего")
        elif rsi <= 55:
            return ("⚪", "нейтрально")
        elif rsi <= 65:
            return ("⚪", "выше среднего")
        elif rsi <= 75:
            return ("🟡", "перекуплен")
        else:
            return ("🔴", "сильно перекуплен")
    
    def get_fg_emoji(self, value: int) -> str:
        """Получить эмодзи для Fear & Greed"""
        if value < 25:
            return "😱"
        elif value < 45:
            return "😟"
        elif value <= 55:
            return "😐"
        elif value <= 75:
            return "😊"
        else:
            return "🤑"


# Синглтон
market_data = MarketDataProvider()
