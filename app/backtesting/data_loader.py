"""
Data Loader — Загрузка исторических данных с Bybit
Период: 2023-01-01 до 2025-12-31 (3 года)
"""
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
import json

from app.core.logger import logger


class BybitDataLoader:
    """
    Загрузчик исторических данных с Bybit API
    
    Особенности:
    - Загрузка по частям (лимит 1000 свечей за запрос)
    - Кэширование в CSV
    - Поддержка всех таймфреймов
    """
    
    BASE_URL = "https://api.bybit.com"
    DATA_DIR = Path("/root/crypto-bot/data")
    
    SYMBOLS = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "MATIC", "LINK", "AVAX"]
    
    # Bybit API intervals: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M
    TIMEFRAMES = {
        "1m": ("1", 1),
        "5m": ("5", 5),
        "15m": ("15", 15),
        "30m": ("30", 30),
        "1h": ("60", 60),
        "4h": ("240", 240),
        "1d": ("D", 1440),
    }
    
    def __init__(self):
        self.DATA_DIR.mkdir(exist_ok=True)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, *args):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    async def _ensure_session(self):
        """Гарантировать что сессия активна"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
    
    def _get_cache_path(self, symbol: str, timeframe: str, start_year: int, end_year: int) -> Path:
        """Путь к кэш-файлу"""
        return self.DATA_DIR / f"{symbol}_{timeframe}_{start_year}_{end_year}.csv"
    
    async def _fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        limit: int = 1000
    ) -> List[list]:
        """Запрос свечей с API"""
        
        url = f"{self.BASE_URL}/v5/market/kline"
        params = {
            "category": "spot",
            "symbol": f"{symbol}USDT",
            "interval": interval,
            "start": start_time,
            "end": end_time,
            "limit": limit
        }
        
        # Убедиться что сессия активна
        await self._ensure_session()
        
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("retCode") == 0:
                        return data.get("result", {}).get("list", [])
                    else:
                        logger.warning(f"API error: {data.get('retMsg')}")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {symbol}")
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
        
        return []
    
    async def download_symbol(
        self,
        symbol: str,
        timeframe: str = "5m",
        start_date: str = "2023-01-01",
        end_date: str = "2025-12-31",
        force: bool = False
    ) -> Optional[pd.DataFrame]:
        """
        Скачать данные для одного символа
        
        Args:
            symbol: BTC, ETH, etc.
            timeframe: 1m, 5m, 15m, 1h, 4h, 1d
            start_date: Начальная дата
            end_date: Конечная дата
            force: Перезаписать кэш
        """
        
        logger.info(f"📥 Downloading {symbol} {timeframe} from {start_date} to {end_date}")
        
        # Проверяем кэш
        cache_file = self._get_cache_path(symbol, timeframe, int(start_date[:4]), int(end_date[:4]))
        
        if cache_file.exists() and not force:
            logger.info(f"📂 Loading from cache: {cache_file}")
            df = pd.read_csv(cache_file, parse_dates=['timestamp'])
            return df
        
        # Парсим даты
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Ограничиваем end_date текущей датой
        now = datetime.utcnow()
        if end_dt > now:
            end_dt = now
            logger.info(f"  Adjusted end date to {end_dt.strftime('%Y-%m-%d')}")
        
        # Интервал: (api_value, minutes)
        tf_data = self.TIMEFRAMES.get(timeframe, ("5", 5))
        api_interval = tf_data[0]
        interval_minutes = tf_data[1]
        
        # Собираем данные
        all_data = []
        current_end = end_dt
        
        # Bybit возвращает данные в обратном порядке (от новых к старым)
        while current_end > start_dt:
            # Запрос
            end_ts = int(current_end.timestamp() * 1000)
            
            klines = await self._fetch_klines(
                symbol=symbol,
                interval=api_interval,
                start_time=int(start_dt.timestamp() * 1000),
                end_time=end_ts,
                limit=1000
            )
            
            if klines:
                all_data.extend(klines)
                
                # Находим самую старую свечу в этом чанке
                oldest_ts = min(int(k[0]) for k in klines)
                current_end = datetime.fromtimestamp(oldest_ts / 1000) - timedelta(minutes=1)
                
                logger.debug(f"  Got {len(klines)} candles, oldest: {current_end}")
            else:
                break
            
            # Rate limiting
            await asyncio.sleep(0.15)
        
        if not all_data:
            logger.error(f"❌ No data for {symbol}")
            return None
        
        # Конвертируем в DataFrame
        df = pd.DataFrame(all_data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])
        
        # Преобразуем типы
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        
        # Сортируем по времени
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Удаляем дубликаты
        df = df.drop_duplicates(subset=['timestamp'])
        
        # Фильтруем по датам
        df = df[(df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)]
        
        # Сохраняем в кэш
        df.to_csv(cache_file, index=False)
        logger.info(f"💾 Saved {len(df):,} candles to {cache_file}")
        
        return df
    
    async def download_all_symbols(
        self,
        timeframe: str = "5m",
        start_date: str = "2023-01-01",
        end_date: str = "2025-12-31",
        force: bool = False
    ) -> Dict[str, pd.DataFrame]:
        """Скачать данные для всех символов"""
        
        results = {}
        
        for symbol in self.SYMBOLS:
            df = await self.download_symbol(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                force=force
            )
            
            if df is not None and len(df) > 0:
                results[symbol] = df
                logger.info(f"✅ {symbol}: {len(df):,} candles")
            else:
                logger.warning(f"⚠️ {symbol}: No data")
            
            # Пауза между символами
            await asyncio.sleep(0.5)
        
        return results
    
    def load_from_cache(self, symbol: str, timeframe: str = "5m") -> Optional[pd.DataFrame]:
        """Загрузить из кэша"""
        
        # Ищем CSV файлы для этого символа
        pattern = f"{symbol}_{timeframe}_*.csv"
        files = list(self.DATA_DIR.glob(pattern))
        
        if files:
            # Берём самый свежий
            latest = max(files, key=lambda f: f.stat().st_mtime)
            logger.info(f"📂 Loading from CSV: {latest}")
            return pd.read_csv(latest, parse_dates=['timestamp'])
        
        # Ищем JSON файлы из старого проекта
        # Формат: SYMBOL_YEAR_TF.json
        json_pattern = f"{symbol}_*_{timeframe}.json"
        json_files = list(self.DATA_DIR.glob(json_pattern))
        
        if not json_files:
            # Пробуем без timeframe
            json_files = list(self.DATA_DIR.glob(f"{symbol}_*.json"))
        
        if json_files:
            latest = max(json_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"📂 Loading from JSON: {latest}")
            
            with open(latest, 'r') as f:
                data = json.load(f)
            
            # Обрабатываем разные форматы JSON
            if isinstance(data, dict):
                # Формат: {"klines": [...], "symbol": "BTC", ...}
                if 'klines' in data:
                    df = pd.DataFrame(data['klines'])
                else:
                    # Формат: {"timestamp": [...], "open": [...], ...}
                    df = pd.DataFrame(data)
            elif isinstance(data, list):
                # Формат: [{...}, {...}, ...]
                df = pd.DataFrame(data)
            else:
                logger.error(f"Unknown JSON format in {latest}")
                return None
            
            # Преобразуем timestamp
            if 'timestamp' in df.columns:
                # Если timestamp в миллисекундах (большое число)
                if df['timestamp'].iloc[0] > 1e12:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                else:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
            elif 'datetime' in df.columns:
                df['timestamp'] = pd.to_datetime(df['datetime'])
            
            # Убеждаемся что есть нужные колонки
            required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if all(col in df.columns for col in required):
                return df[required].sort_values('timestamp').reset_index(drop=True)
            else:
                logger.warning(f"Missing columns. Available: {df.columns.tolist()}")
                return df
        
        return None
    
    def get_available_data(self) -> Dict[str, List[str]]:
        """Показать доступные данные"""
        available = {}
        
        for symbol in self.SYMBOLS:
            files = list(self.DATA_DIR.glob(f"{symbol}_*.csv"))
            if files:
                available[symbol] = [f.name for f in files]
        
        return available


# Глобальный экземпляр
data_loader = BybitDataLoader()


async def download_all_data():
    """Скрипт загрузки всех данных"""
    
    logger.info("🚀 Starting data download for 2023-2025...")
    
    async with BybitDataLoader() as loader:
        results = await loader.download_all_symbols(
            timeframe="5m",
            start_date="2023-01-01",
            end_date="2025-12-31"
        )
    
    logger.info(f"✅ Downloaded data for {len(results)} symbols")
    
    # Статистика
    total_candles = sum(len(df) for df in results.values())
    logger.info(f"📊 Total candles: {total_candles:,}")
    
    return results


if __name__ == "__main__":
    asyncio.run(download_all_data())
