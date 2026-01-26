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
    
    async def get_order(self, symbol: str, order_id: str) -> dict:
        """Получить информацию об ордере"""
        
        return await self._request('GET', '/v5/order/realtime', {
            'category': 'spot',
            'symbol': f"{symbol}USDT",
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


# Глобальный экземпляр
bybit_client = BybitClient()
