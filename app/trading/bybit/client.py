"""
Bybit Spot Client — Реальная торговля на споте
"""
import asyncio
import hmac
import hashlib
import time
from typing import Optional, Dict, List, Any
from datetime import datetime

import aiohttp

from app.core.config import settings
from app.core.logger import logger


class BybitClient:
    """
    Bybit Spot API клиент
    
    Функции:
    - Получение баланса
    - Рыночные ордера (buy/sell)
    - Получение цен
    - История ордеров
    """
    
    MAINNET_URL = "https://api.bybit.com"
    TESTNET_URL = "https://api-testnet.bybit.com"
    
    def __init__(self, testnet: bool = None):
        self.api_key = settings.bybit_api_key or ""
        self.api_secret = settings.bybit_api_secret or ""
        self.testnet = testnet if testnet is not None else settings.bybit_testnet
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Выбираем URL
        self.BASE_URL = self.TESTNET_URL if self.testnet else self.MAINNET_URL
        
        logger.info(f"BybitClient initialized (testnet={self.testnet})")
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    def _generate_signature(self, timestamp: str, params: str = "") -> str:
        """Генерация подписи для V5 API"""
        recv_window = "5000"
        param_str = f"{timestamp}{self.api_key}{recv_window}{params}"
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        params: dict = None,
        private: bool = False
    ) -> dict:
        """Выполнить запрос к API"""
        
        if self.session is None:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.BASE_URL}{endpoint}"
        params = params or {}
        
        try:
            timestamp = str(int(time.time() * 1000))
            
            if private:
                # Проверяем наличие API ключей
                if not self.api_key or not self.api_secret:
                    logger.warning("API keys not configured")
                    return {'retCode': -1, 'retMsg': 'API keys not configured'}
                
                if method == 'GET':
                    # Для GET запросов параметры в query string
                    query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
                    signature = self._generate_signature(timestamp, query_string)
                else:
                    # Для POST запросов параметры в JSON
                    import json
                    signature = self._generate_signature(timestamp, json.dumps(params))
                
                headers = {
                    'X-BAPI-API-KEY': self.api_key,
                    'X-BAPI-TIMESTAMP': timestamp,
                    'X-BAPI-SIGN': signature,
                    'X-BAPI-RECV-WINDOW': '5000',
                    'Content-Type': 'application/json'
                }
            else:
                headers = {'Content-Type': 'application/json'}
            
            if method == 'GET':
                async with self.session.get(url, params=params, headers=headers) as resp:
                    data = await resp.json()
            else:
                async with self.session.post(url, json=params, headers=headers) as resp:
                    data = await resp.json()
            
            if data.get('retCode') != 0:
                logger.warning(f"Bybit API: {data.get('retMsg', 'Unknown error')}")
            
            return data
            
        except Exception as e:
            logger.error(f"Request error: {e}")
            return {'retCode': -1, 'retMsg': str(e)}
    
    # === PUBLIC METHODS ===
    
    async def get_price(self, symbol: str) -> Optional[float]:
        """Получить текущую цену"""
        
        resp = await self._request('GET', '/v5/market/tickers', {
            'category': 'spot',
            'symbol': f"{symbol}USDT"
        })
        
        if resp.get('retCode') == 0:
            result = resp.get('result', {}).get('list', [])
            if result:
                return float(result[0].get('lastPrice', 0))
        
        return None
    
    async def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Получить цены для списка символов"""
        
        prices = {}
        
        for symbol in symbols:
            price = await self.get_price(symbol)
            if price:
                prices[symbol] = price
            await asyncio.sleep(0.05)  # Rate limiting
        
        return prices
    
    async def get_all_spot_prices(self) -> Dict[str, float]:
        """Получить все цены спота за один запрос"""
        
        resp = await self._request('GET', '/v5/market/tickers', {
            'category': 'spot'
        })
        
        prices = {}
        if resp.get('retCode') == 0:
            for item in resp.get('result', {}).get('list', []):
                symbol = item.get('symbol', '')
                if symbol.endswith('USDT'):
                    coin = symbol.replace('USDT', '')
                    prices[coin] = float(item.get('lastPrice', 0))
        
        return prices
    
    async def get_balance(self, coin: str = "USDT") -> Optional[float]:
        """Получить баланс монеты"""
        
        resp = await self._request('GET', '/v5/account/wallet-balance', {
            'accountType': 'UNIFIED'
        }, private=True)
        
        if resp.get('retCode') == 0:
            accounts = resp.get('result', {}).get('list', [])
            for account in accounts:
                coins = account.get('coin', [])
                for c in coins:
                    if c.get('coin') == coin:
                        return float(c.get('availableToWithdraw', 0))
        
        return None
    
    async def get_all_balances(self) -> Dict[str, float]:
        """Получить все балансы"""
        
        resp = await self._request('GET', '/v5/account/wallet-balance', {
            'accountType': 'UNIFIED'
        }, private=True)
        
        balances = {}
        
        if resp.get('retCode') == 0:
            accounts = resp.get('result', {}).get('list', [])
            for account in accounts:
                coins = account.get('coin', [])
                for c in coins:
                    balance = float(c.get('availableToWithdraw', 0))
                    if balance > 0:
                        balances[c.get('coin')] = balance
        
        return balances
    
    # === TRADING METHODS ===
    
    async def market_buy(
        self, 
        symbol: str, 
        qty: float = None,
        quote_qty: float = None  # Сумма в USDT
    ) -> dict:
        """Рыночная покупка"""
        
        params = {
            'category': 'spot',
            'symbol': f"{symbol}USDT",
            'side': 'Buy',
            'orderType': 'Market',
        }
        
        if quote_qty:
            params['marketUnit'] = 'quoteCoin'
            params['qty'] = str(quote_qty)
        elif qty:
            params['marketUnit'] = 'baseCoin'
            params['qty'] = str(qty)
        else:
            return {'retCode': -1, 'retMsg': 'qty or quote_qty required'}
        
        resp = await self._request('POST', '/v5/order/create', params, private=True)
        
        if resp.get('retCode') == 0:
            order_id = resp.get('result', {}).get('orderId')
            logger.info(f"✅ Market BUY {symbol}: order {order_id}")
        else:
            logger.error(f"❌ Market BUY failed: {resp}")
        
        return resp
    
    async def market_sell(
        self, 
        symbol: str, 
        qty: float
    ) -> dict:
        """Рыночная продажа"""
        
        params = {
            'category': 'spot',
            'symbol': f"{symbol}USDT",
            'side': 'Sell',
            'orderType': 'Market',
            'qty': str(qty),
        }
        
        resp = await self._request('POST', '/v5/order/create', params, private=True)
        
        if resp.get('retCode') == 0:
            order_id = resp.get('result', {}).get('orderId')
            logger.info(f"✅ Market SELL {symbol}: order {order_id}")
        else:
            logger.error(f"❌ Market SELL failed: {resp}")
        
        return resp
    
    # === LIMIT ORDERS (для Grid Bot) ===
    
    async def limit_buy(
        self, 
        symbol: str, 
        price: float, 
        qty: float,
        time_in_force: str = "GTC"
    ) -> Optional[Dict]:
        """
        Лимитный ордер на покупку
        
        Args:
            symbol: Торговая пара (например "BTCUSDT" или "BTC")
            price: Цена покупки
            qty: Количество базовой валюты
            time_in_force: GTC (до отмены), IOC (немедленно или отмена), FOK (всё или ничего)
        
        Returns:
            {"orderId": "xxx", "orderLinkId": "xxx"} или None
        """
        try:
            # Нормализуем symbol
            if not symbol.endswith("USDT"):
                symbol = f"{symbol}USDT"
            
            params = {
                "category": "spot",
                "symbol": symbol,
                "side": "Buy",
                "orderType": "Limit",
                "qty": str(qty),
                "price": str(price),
                "timeInForce": time_in_force,
            }
            
            resp = await self._request("POST", "/v5/order/create", params, private=True)
            
            if resp and resp.get("retCode") == 0:
                order_info = resp.get("result", {})
                logger.info(f"📗 Limit BUY: {symbol} @ ${price}, qty={qty}, orderId={order_info.get('orderId')}")
                return order_info
            else:
                logger.error(f"❌ Limit BUY failed: {resp}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Limit BUY error: {e}")
            return None

    async def limit_sell(
        self, 
        symbol: str, 
        price: float, 
        qty: float,
        time_in_force: str = "GTC"
    ) -> Optional[Dict]:
        """
        Лимитный ордер на продажу
        
        Args:
            symbol: Торговая пара (например "BTCUSDT" или "BTC")
            price: Цена продажи
            qty: Количество базовой валюты
            time_in_force: GTC, IOC, FOK
        
        Returns:
            {"orderId": "xxx", "orderLinkId": "xxx"} или None
        """
        try:
            # Нормализуем symbol
            if not symbol.endswith("USDT"):
                symbol = f"{symbol}USDT"
            
            params = {
                "category": "spot",
                "symbol": symbol,
                "side": "Sell",
                "orderType": "Limit",
                "qty": str(qty),
                "price": str(price),
                "timeInForce": time_in_force,
            }
            
            resp = await self._request("POST", "/v5/order/create", params, private=True)
            
            if resp and resp.get("retCode") == 0:
                order_info = resp.get("result", {})
                logger.info(f"📕 Limit SELL: {symbol} @ ${price}, qty={qty}, orderId={order_info.get('orderId')}")
                return order_info
            else:
                logger.error(f"❌ Limit SELL failed: {resp}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Limit SELL error: {e}")
            return None

    async def get_order_status(self, symbol: str, order_id: str) -> Optional[str]:
        """
        Получить статус ордера
        
        Args:
            symbol: Торговая пара (например "BTCUSDT" или "BTC")
            order_id: ID ордера
        
        Returns:
            "New", "PartiallyFilled", "Filled", "Cancelled", "Rejected" или None
        """
        try:
            # Нормализуем symbol
            if not symbol.endswith("USDT"):
                symbol = f"{symbol}USDT"
            
            params = {
                "category": "spot",
                "symbol": symbol,
                "orderId": order_id,
            }
            
            resp = await self._request("GET", "/v5/order/realtime", params, private=True)
            
            if resp and resp.get("retCode") == 0:
                orders = resp.get("result", {}).get("list", [])
                if orders:
                    return orders[0].get("orderStatus")
            return None
            
        except Exception as e:
            logger.error(f"❌ Get order status error: {e}")
            return None

    async def get_order(self, symbol: str, order_id: str) -> dict:
        """Получить информацию об ордере"""
        
        # Нормализуем symbol
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        return await self._request('GET', '/v5/order/realtime', {
            'category': 'spot',
            'symbol': symbol,
            'orderId': order_id,
        }, private=True)
    
    async def get_open_orders(self, symbol: str = None) -> List[dict]:
        """Получить открытые ордера"""
        
        params = {'category': 'spot'}
        if symbol:
            params['symbol'] = f"{symbol}USDT"
        
        resp = await self._request('GET', '/v5/order/realtime', params, private=True)
        
        if resp.get('retCode') == 0:
            return resp.get('result', {}).get('list', [])
        
        return []
    
    async def get_order_history(self, symbol: str = None, limit: int = 50) -> List[dict]:
        """История ордеров"""
        
        params = {
            'category': 'spot',
            'limit': str(limit)
        }
        if symbol:
            params['symbol'] = f"{symbol}USDT"
        
        resp = await self._request('GET', '/v5/order/history', params, private=True)
        
        if resp.get('retCode') == 0:
            return resp.get('result', {}).get('list', [])
        
        return []
    
    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        """Отменить ордер"""
        
        params = {
            'category': 'spot',
            'symbol': f"{symbol}USDT",
            'orderId': order_id,
        }
        
        resp = await self._request('POST', '/v5/order/cancel', params, private=True)
        
        if resp.get('retCode') == 0:
            logger.info(f"✅ Order cancelled: {order_id}")
        else:
            logger.error(f"❌ Cancel failed: {resp}")
        
        return resp

    # === MARKET DATA METHODS (для DirectorBrain) ===
    
    async def get_orderbook(self, symbol: str, limit: int = 50) -> Dict:
        """
        Получить стакан ордеров
        https://bybit-exchange.github.io/docs/v5/market/orderbook
        
        Returns:
            {
                "bids": [[price, qty], ...],  # Покупки
                "asks": [[price, qty], ...],  # Продажи
            }
        """
        # Нормализуем symbol
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        resp = await self._request("GET", "/v5/market/orderbook", {
            "category": "spot",
            "symbol": symbol,
            "limit": limit
        })
        
        result = resp.get("result", {})
        return {
            "bids": [[float(b[0]), float(b[1])] for b in result.get("b", [])],
            "asks": [[float(a[0]), float(a[1])] for a in result.get("a", [])]
        }

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """
        Получить последние сделки
        https://bybit-exchange.github.io/docs/v5/market/recent-trade
        
        Returns:
            [{"price": float, "qty": float, "side": "Buy"/"Sell", "time": int}, ...]
        """
        # Нормализуем symbol
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        resp = await self._request("GET", "/v5/market/recent-trade", {
            "category": "spot",
            "symbol": symbol,
            "limit": limit
        })
        
        trades = resp.get("result", {}).get("list", [])
        return [
            {
                "price": float(t["price"]),
                "qty": float(t["size"]),
                "side": t["side"],
                "time": int(t["time"])
            }
            for t in trades
        ]

    async def get_klines(self, symbol: str, interval: str = "60", limit: int = 100) -> List:
        """
        Получить свечи (OHLCV)
        https://bybit-exchange.github.io/docs/v5/market/kline
        
        Args:
            symbol: BTCUSDT или BTC
            interval: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M
            limit: количество свечей (макс 1000)
        
        Returns:
            [[timestamp, open, high, low, close, volume, turnover], ...]
        """
        # Нормализуем symbol
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        resp = await self._request("GET", "/v5/market/kline", {
            "category": "spot",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        })
        
        klines = resp.get("result", {}).get("list", [])
        
        # Bybit возвращает в обратном порядке (новые первые), разворачиваем
        return [
            {
                "timestamp": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "turnover": float(k[6])
            }
            for k in reversed(klines)
        ]

    async def get_klines_multi_timeframe(self, symbol: str) -> Dict:
        """
        Получить свечи с нескольких таймфреймов
        
        Returns:
            {
                "5m": [...],
                "15m": [...],
                "1h": [...],
                "4h": [...]
            }
        """
        result = {}
        timeframes = [("5", 50, "5m"), ("15", 30, "15m"), ("60", 24, "1h"), ("240", 20, "4h")]
        
        for interval, limit, tf_name in timeframes:
            try:
                klines = await self.get_klines(symbol, interval, limit)
                result[tf_name] = klines
            except Exception as e:
                logger.warning(f"Failed to get {interval} klines for {symbol}: {e}")
                result[tf_name] = []
        
        return result

    async def get_ticker_24h(self, symbol: str) -> Dict:
        """
        Получить 24h статистику
        
        Returns:
            {
                "price": float,
                "change_24h": float,  # %
                "high_24h": float,
                "low_24h": float,
                "volume_24h": float,
                "turnover_24h": float
            }
        """
        # Нормализуем symbol
        if not symbol.endswith("USDT"):
            symbol = f"{symbol}USDT"
        
        resp = await self._request("GET", "/v5/market/tickers", {
            "category": "spot",
            "symbol": symbol
        })
        
        result = resp.get("result", {}).get("list", [{}])[0]
        
        return {
            "price": float(result.get("lastPrice", 0)),
            "change_24h": float(result.get("price24hPcnt", 0)) * 100,
            "high_24h": float(result.get("highPrice24h", 0)),
            "low_24h": float(result.get("lowPrice24h", 0)),
            "volume_24h": float(result.get("volume24h", 0)),
            "turnover_24h": float(result.get("turnover24h", 0))
        }


# Глобальный экземпляр
bybit_client = BybitClient()
