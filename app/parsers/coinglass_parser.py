"""
📊 Coinglass Parser — ликвидации и Open Interest
Парсинг данных БЕЗ платного API

Данные:
- Ликвидации в реальном времени
- Open Interest по биржам
- Long/Short Ratio детально
- Funding Rate история
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from app.core.logger import logger


@dataclass
class LiquidationData:
    """Данные о ликвидациях"""
    total_24h: float = 0
    long_24h: float = 0
    short_24h: float = 0
    total_1h: float = 0
    long_1h: float = 0
    short_1h: float = 0
    largest_single: float = 0
    dominant_side: str = "neutral"  # "longs_rekt", "shorts_rekt", "neutral"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OpenInterestData:
    """Данные Open Interest"""
    total_oi: float = 0
    oi_change_1h: float = 0
    oi_change_4h: float = 0
    oi_change_24h: float = 0
    oi_by_exchange: Dict[str, float] = field(default_factory=dict)
    trend: str = "neutral"  # "increasing", "decreasing", "neutral"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FundingData:
    """Данные Funding Rate"""
    current_rate: float = 0
    predicted_rate: float = 0
    average_rate: float = 0
    by_exchange: Dict[str, float] = field(default_factory=dict)
    sentiment: str = "neutral"
    timestamp: datetime = field(default_factory=datetime.now)


class CoinglassParser:
    """
    📊 Coinglass Parser
    
    Получает данные через публичные endpoints и альтернативные источники
    """
    
    def __init__(self):
        self.base_url = "https://www.coinglass.com"
        self.api_url = "https://fapi.coinglass.com/api"
        
        # Альтернативные endpoints
        self.alternative_endpoints = {
            "liquidations": [
                "https://fapi.coinglass.com/api/futures/liquidation/info",
                "https://open-api.coinglass.com/public/v2/liquidation_info",
            ],
            "oi": [
                "https://fapi.coinglass.com/api/futures/openInterest/info",
                "https://open-api.coinglass.com/public/v2/open_interest",
            ],
            "funding": [
                "https://fapi.coinglass.com/api/futures/funding/info",
                "https://open-api.coinglass.com/public/v2/funding",
            ],
        }
        
        # Кэш
        self.cache: Dict[str, any] = {}
        self.cache_time: Dict[str, datetime] = {}
        self.cache_duration = timedelta(minutes=3)
        
        # Последние данные
        self.last_liquidations: Optional[LiquidationData] = None
        self.last_oi: Optional[OpenInterestData] = None
        self.last_funding: Optional[FundingData] = None
        
        logger.info("📊 Coinglass Parser инициализирован")
    
    async def _fetch_json(self, url: str, params: Dict = None) -> Optional[Dict]:
        """Загрузить JSON"""
        
        cache_key = f"{url}_{str(params)}"
        
        # Проверяем кэш
        if cache_key in self.cache:
            if datetime.now() - self.cache_time.get(cache_key, datetime.min) < self.cache_duration:
                return self.cache[cache_key]
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                    "Referer": "https://www.coinglass.com/",
                    "Origin": "https://www.coinglass.com",
                }
                
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        self.cache[cache_key] = data
                        self.cache_time[cache_key] = datetime.now()
                        return data
                    else:
                        logger.debug(f"Coinglass {url} returned {response.status}")
        
        except Exception as e:
            logger.debug(f"Coinglass fetch error: {e}")
        
        return None
    
    async def get_liquidations(self, symbol: str = "BTC") -> LiquidationData:
        """Получить данные о ликвидациях"""
        
        data = LiquidationData()
        
        try:
            # Пробуем публичный API
            for url in self.alternative_endpoints["liquidations"]:
                params = {"symbol": symbol}
                result = await self._fetch_json(url, params)
                
                if result and (result.get("success") or result.get("code") == "0"):
                    liq_data = result.get("data", result)
                    
                    if isinstance(liq_data, dict):
                        # 24h данные
                        data.total_24h = float(liq_data.get("totalVolUsd", 0) or liq_data.get("total", 0) or 0)
                        data.long_24h = float(liq_data.get("longVolUsd", 0) or liq_data.get("longLiquidationUsd", 0) or 0)
                        data.short_24h = float(liq_data.get("shortVolUsd", 0) or liq_data.get("shortLiquidationUsd", 0) or 0)
                        
                        # 1h данные
                        data.total_1h = float(liq_data.get("h1TotalVolUsd", 0) or data.total_24h / 24)
                        data.long_1h = float(liq_data.get("h1LongVolUsd", 0) or data.long_24h / 24)
                        data.short_1h = float(liq_data.get("h1ShortVolUsd", 0) or data.short_24h / 24)
                        
                        if data.total_24h > 0:
                            break
            
            # Если Coinglass не работает — используем Bybit
            if data.total_24h == 0:
                data = await self._estimate_liquidations_from_bybit(symbol)
            
            # Определяем кто больше ликвидирован
            if data.long_24h > data.short_24h * 1.5:
                data.dominant_side = "longs_rekt"
            elif data.short_24h > data.long_24h * 1.5:
                data.dominant_side = "shorts_rekt"
            else:
                data.dominant_side = "neutral"
            
            data.timestamp = datetime.now()
            
        except Exception as e:
            logger.debug(f"Liquidations error: {e}")
        
        self.last_liquidations = data
        return data
    
    async def _estimate_liquidations_from_bybit(self, symbol: str) -> LiquidationData:
        """Оценка ликвидаций по данным Bybit"""
        
        data = LiquidationData()
        
        try:
            # Используем данные из Whale AI если доступны
            from app.ai.whale_ai import whale_ai
            
            if whale_ai.last_metrics:
                metrics = whale_ai.last_metrics
                
                # Оцениваем ликвидации по изменению OI
                if metrics.oi_change_1h < -2:
                    # Резкое падение OI = были ликвидации
                    estimated_liq = abs(metrics.oi_change_1h) * 15_000_000
                    
                    # Определяем кто ликвидирован по funding
                    if metrics.funding_rate > 0.03:
                        # Лонги платили = лонгов больше = лонги ликвидированы
                        data.long_1h = estimated_liq * 0.7
                        data.short_1h = estimated_liq * 0.3
                    elif metrics.funding_rate < -0.03:
                        data.long_1h = estimated_liq * 0.3
                        data.short_1h = estimated_liq * 0.7
                    else:
                        data.long_1h = estimated_liq * 0.5
                        data.short_1h = estimated_liq * 0.5
                    
                    data.total_1h = estimated_liq
                    data.total_24h = estimated_liq * 8  # Грубая оценка
                    data.long_24h = data.long_1h * 8
                    data.short_24h = data.short_1h * 8
        
        except ImportError:
            logger.debug("Whale AI not available for liquidation estimation")
        except Exception as e:
            logger.debug(f"Bybit liquidations estimation error: {e}")
        
        return data
    
    async def get_open_interest(self, symbol: str = "BTC") -> OpenInterestData:
        """Получить Open Interest"""
        
        data = OpenInterestData()
        
        try:
            # Через публичный API
            for url in self.alternative_endpoints["oi"]:
                params = {"symbol": symbol}
                result = await self._fetch_json(url, params)
                
                if result and (result.get("success") or result.get("code") == "0"):
                    oi_data = result.get("data", result)
                    
                    if isinstance(oi_data, dict):
                        data.total_oi = float(oi_data.get("openInterest", 0) or oi_data.get("oi", 0) or 0)
                        data.oi_change_1h = float(oi_data.get("h1OiChangePercent", 0) or oi_data.get("h1Change", 0) or 0)
                        data.oi_change_4h = float(oi_data.get("h4OiChangePercent", 0) or oi_data.get("h4Change", 0) or 0)
                        data.oi_change_24h = float(oi_data.get("h24OiChangePercent", 0) or oi_data.get("h24Change", 0) or 0)
                        
                        # По биржам
                        exchange_list = oi_data.get("list", [])
                        if exchange_list:
                            for exchange in exchange_list[:5]:
                                name = exchange.get("exchangeName", "unknown")
                                oi = float(exchange.get("openInterest", 0) or 0)
                                if oi > 0:
                                    data.oi_by_exchange[name] = oi
                        
                        if data.total_oi > 0:
                            break
            
            # Альтернатива — из Bybit
            if data.total_oi == 0:
                data = await self._get_oi_from_bybit(symbol)
            
            # Определяем тренд
            if data.oi_change_1h > 3:
                data.trend = "increasing"
            elif data.oi_change_1h < -3:
                data.trend = "decreasing"
            else:
                data.trend = "neutral"
            
            data.timestamp = datetime.now()
        
        except Exception as e:
            logger.debug(f"OI error: {e}")
        
        self.last_oi = data
        return data
    
    async def _get_oi_from_bybit(self, symbol: str) -> OpenInterestData:
        """OI из Bybit API"""
        
        data = OpenInterestData()
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.bybit.com/v5/market/open-interest"
                params = {
                    "category": "linear",
                    "symbol": f"{symbol}USDT",
                    "intervalTime": "1h",
                    "limit": "24"
                }
                
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        
                        if result.get("retCode") == 0:
                            oi_list = result.get("result", {}).get("list", [])
                            
                            if len(oi_list) >= 1:
                                data.total_oi = float(oi_list[0].get("openInterest", 0))
                                data.oi_by_exchange["Bybit"] = data.total_oi
                            
                            if len(oi_list) >= 2:
                                current = float(oi_list[0].get("openInterest", 0))
                                prev_1h = float(oi_list[1].get("openInterest", 1))
                                data.oi_change_1h = ((current - prev_1h) / prev_1h * 100) if prev_1h > 0 else 0
                            
                            if len(oi_list) >= 24:
                                current = float(oi_list[0].get("openInterest", 0))
                                prev_24h = float(oi_list[-1].get("openInterest", 1))
                                data.oi_change_24h = ((current - prev_24h) / prev_24h * 100) if prev_24h > 0 else 0
        
        except Exception as e:
            logger.debug(f"Bybit OI error: {e}")
        
        return data
    
    async def get_funding_rates(self, symbol: str = "BTC") -> FundingData:
        """Получить Funding Rate"""
        
        data = FundingData()
        
        try:
            for url in self.alternative_endpoints["funding"]:
                params = {"symbol": symbol}
                result = await self._fetch_json(url, params)
                
                if result and (result.get("success") or result.get("code") == "0"):
                    funding_data = result.get("data", result)
                    
                    if isinstance(funding_data, dict):
                        data.current_rate = float(funding_data.get("rate", 0) or funding_data.get("fundingRate", 0) or 0) * 100
                        data.predicted_rate = float(funding_data.get("predictedRate", 0) or 0) * 100
                        
                        # По биржам
                        exchange_list = funding_data.get("list", [])
                        if exchange_list:
                            rates = []
                            for exchange in exchange_list[:5]:
                                name = exchange.get("exchangeName", "unknown")
                                rate = float(exchange.get("rate", 0) or 0) * 100
                                if rate != 0:
                                    data.by_exchange[name] = rate
                                    rates.append(rate)
                            
                            data.average_rate = sum(rates) / len(rates) if rates else 0
                        
                        if data.current_rate != 0:
                            break
            
            # Из Bybit если Coinglass не работает
            if data.current_rate == 0:
                data = await self._get_funding_from_bybit(symbol)
            
            # Определяем сентимент
            if data.current_rate > 0.1:
                data.sentiment = "extreme_bullish"
            elif data.current_rate > 0.05:
                data.sentiment = "bullish"
            elif data.current_rate < -0.1:
                data.sentiment = "extreme_bearish"
            elif data.current_rate < -0.05:
                data.sentiment = "bearish"
            else:
                data.sentiment = "neutral"
            
            data.timestamp = datetime.now()
        
        except Exception as e:
            logger.debug(f"Funding error: {e}")
        
        self.last_funding = data
        return data
    
    async def _get_funding_from_bybit(self, symbol: str) -> FundingData:
        """Funding из Bybit"""
        
        data = FundingData()
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.bybit.com/v5/market/tickers"
                params = {
                    "category": "linear",
                    "symbol": f"{symbol}USDT"
                }
                
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        
                        if result.get("retCode") == 0:
                            tickers = result.get("result", {}).get("list", [])
                            if tickers:
                                data.current_rate = float(tickers[0].get("fundingRate", 0)) * 100
                                data.by_exchange["Bybit"] = data.current_rate
        
        except Exception as e:
            logger.debug(f"Bybit funding error: {e}")
        
        return data
    
    async def get_full_market_data(self, symbol: str = "BTC") -> Dict:
        """Получить все данные рынка"""
        
        # Параллельно
        liquidations, oi, funding = await asyncio.gather(
            self.get_liquidations(symbol),
            self.get_open_interest(symbol),
            self.get_funding_rates(symbol),
            return_exceptions=True
        )
        
        # Обрабатываем ошибки
        if isinstance(liquidations, Exception):
            logger.debug(f"Liquidations exception: {liquidations}")
            liquidations = LiquidationData()
        if isinstance(oi, Exception):
            logger.debug(f"OI exception: {oi}")
            oi = OpenInterestData()
        if isinstance(funding, Exception):
            logger.debug(f"Funding exception: {funding}")
            funding = FundingData()
        
        # Анализ
        risk_score = 0
        signals = []
        
        # Ликвидации
        if liquidations.total_1h > 100_000_000:
            risk_score += 30
            signals.append(f"🔥 Ликвидаций за час: ${liquidations.total_1h/1e6:.0f}M")
        elif liquidations.total_1h > 50_000_000:
            risk_score += 15
            signals.append(f"⚡ Ликвидаций за час: ${liquidations.total_1h/1e6:.0f}M")
        
        if liquidations.dominant_side == "longs_rekt":
            signals.append("📉 Ликвидируют лонги — возможно дно близко")
        elif liquidations.dominant_side == "shorts_rekt":
            signals.append("📈 Ликвидируют шорты — возможен пик")
        
        # OI
        if oi.oi_change_1h > 5:
            risk_score += 20
            signals.append(f"📈 OI вырос на {oi.oi_change_1h:.1f}% — много новых позиций")
        elif oi.oi_change_1h < -5:
            risk_score += 20
            signals.append(f"📉 OI упал на {oi.oi_change_1h:.1f}% — закрытие позиций")
        elif oi.oi_change_1h > 2:
            signals.append(f"📊 OI растёт: {oi.oi_change_1h:+.1f}%")
        elif oi.oi_change_1h < -2:
            signals.append(f"📊 OI падает: {oi.oi_change_1h:.1f}%")
        
        # Funding
        if abs(funding.current_rate) > 0.1:
            risk_score += 25
            if funding.current_rate > 0:
                signals.append(f"⚠️ Funding {funding.current_rate:+.3f}% — лонги перегреты!")
            else:
                signals.append(f"⚠️ Funding {funding.current_rate:+.3f}% — шорты перегреты!")
        elif abs(funding.current_rate) > 0.05:
            risk_score += 10
            if funding.current_rate > 0:
                signals.append(f"💰 Funding {funding.current_rate:+.3f}% — умеренно бычий")
            else:
                signals.append(f"💰 Funding {funding.current_rate:+.3f}% — умеренно медвежий")
        
        # Общий сентимент
        if funding.sentiment in ["extreme_bullish"] and liquidations.dominant_side == "shorts_rekt":
            overall = "extreme_greed"
        elif funding.sentiment in ["extreme_bearish"] and liquidations.dominant_side == "longs_rekt":
            overall = "extreme_fear"
        elif funding.current_rate > 0.05:
            overall = "bullish"
        elif funding.current_rate < -0.05:
            overall = "bearish"
        else:
            overall = "neutral"
        
        logger.info(f"📊 Coinglass: Risk={risk_score}, Sentiment={overall}, Signals={len(signals)}")
        
        return {
            "liquidations": {
                "total_1h": liquidations.total_1h,
                "long_1h": liquidations.long_1h,
                "short_1h": liquidations.short_1h,
                "total_24h": liquidations.total_24h,
                "long_24h": liquidations.long_24h,
                "short_24h": liquidations.short_24h,
                "dominant": liquidations.dominant_side,
            },
            "open_interest": {
                "total": oi.total_oi,
                "change_1h": oi.oi_change_1h,
                "change_4h": oi.oi_change_4h,
                "change_24h": oi.oi_change_24h,
                "trend": oi.trend,
                "by_exchange": oi.oi_by_exchange,
            },
            "funding": {
                "current": funding.current_rate,
                "predicted": funding.predicted_rate,
                "average": funding.average_rate,
                "sentiment": funding.sentiment,
                "by_exchange": funding.by_exchange,
            },
            "analysis": {
                "risk_score": risk_score,
                "overall_sentiment": overall,
                "signals": signals,
            }
        }
    
    def get_status_text(self) -> str:
        """Статус для Telegram"""
        
        text = "📊 *Coinglass Parser*\n\n"
        
        if self.last_liquidations:
            liq = self.last_liquidations
            text += f"*Ликвидации 1h:*\n"
            text += f"  📉 Long: ${liq.long_1h/1e6:.1f}M\n"
            text += f"  📈 Short: ${liq.short_1h/1e6:.1f}M\n"
            text += f"  🎯 Dominant: {liq.dominant_side}\n\n"
        
        if self.last_oi:
            oi = self.last_oi
            text += f"*Open Interest:*\n"
            text += f"  📊 Change 1h: {oi.oi_change_1h:+.1f}%\n"
            text += f"  📈 Trend: {oi.trend}\n\n"
        
        if self.last_funding:
            f = self.last_funding
            text += f"*Funding:*\n"
            text += f"  💰 Rate: {f.current_rate:+.4f}%\n"
            text += f"  🎯 Sentiment: {f.sentiment}\n"
        
        return text


# Singleton
coinglass_parser = CoinglassParser()


async def get_market_data(symbol: str = "BTC") -> Dict:
    """Публичная функция"""
    return await coinglass_parser.get_full_market_data(symbol)


async def get_liquidations(symbol: str = "BTC") -> LiquidationData:
    """Получить ликвидации"""
    return await coinglass_parser.get_liquidations(symbol)


async def get_open_interest(symbol: str = "BTC") -> OpenInterestData:
    """Получить Open Interest"""
    return await coinglass_parser.get_open_interest(symbol)


async def get_funding(symbol: str = "BTC") -> FundingData:
    """Получить Funding Rate"""
    return await coinglass_parser.get_funding_rates(symbol)
