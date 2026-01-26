#!/usr/bin/env python3
"""
Download Data - Загрузка исторических данных
============================================

Использование:
    python scripts/download_data.py --symbol BTC --year 2024
    python scripts/download_data.py --all --year 2024
"""

import asyncio
import argparse
import sys
sys.path.insert(0, "/root/crypto-bot")

from app.core.logger import logger
from app.core.constants import COINS
from app.backtesting.data_loader import data_loader


async def download_single(symbol: str, year: int, timeframe: str):
    """Загрузить данные для одной монеты"""
    print(f"📥 Загрузка {symbol} {year} {timeframe}m...")
    
    df = await data_loader.load(symbol, timeframe, year, use_cache=False)
    
    if not df.empty:
        print(f"✅ {symbol}: {len(df)} свечей")
        print(f"   Период: {df['timestamp'].min()} - {df['timestamp'].max()}")
    else:
        print(f"❌ {symbol}: нет данных")


async def download_all(year: int, timeframe: str):
    """Загрузить данные для всех монет"""
    print(f"📥 Загрузка данных для {len(COINS)} монет...")
    
    for symbol in COINS:
        await download_single(symbol, year, timeframe)
        await asyncio.sleep(1)  # Пауза между запросами
    
    print("\n✅ Загрузка завершена!")


def main():
    parser = argparse.ArgumentParser(description="Download historical data")
    parser.add_argument("--symbol", type=str, help="Торговая пара")
    parser.add_argument("--year", type=int, default=2024, help="Год")
    parser.add_argument("--timeframe", type=str, default="5", help="Таймфрейм (минуты)")
    parser.add_argument("--all", action="store_true", help="Все монеты")
    
    args = parser.parse_args()
    
    if args.all:
        asyncio.run(download_all(args.year, args.timeframe))
    elif args.symbol:
        asyncio.run(download_single(args.symbol, args.year, args.timeframe))
    else:
        print("Укажите --symbol или --all")
        parser.print_help()


if __name__ == "__main__":
    main()
