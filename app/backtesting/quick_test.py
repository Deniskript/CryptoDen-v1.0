"""
Быстрый тест стратегий - СПОТ
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import aiohttp
import sys
sys.path.insert(0, '/root/crypto-bot')


async def load_data(symbol: str):
    """Загрузить данные с Bybit"""
    print(f"📥 {symbol}...", end=" ")
    klines = []
    end = int(datetime.now().timestamp() * 1000)
    start = int(datetime(2025, 1, 1).timestamp() * 1000)
    
    async with aiohttp.ClientSession() as session:
        while end > start:
            url = "https://api.bybit.com/v5/market/kline"
            params = {
                "category": "spot",
                "symbol": f"{symbol}USDT",
                "interval": "60",
                "limit": 1000,
                "end": end
            }
            
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                
                if data.get('retCode') != 0:
                    break
                
                result = data.get('result', {}).get('list', [])
                if not result:
                    break
                
                klines = result + klines
                end = int(result[-1][0]) - 1
            
            await asyncio.sleep(0.05)
    
    if not klines:
        print("❌")
        return pd.DataFrame()
    
    df = pd.DataFrame(klines, columns=['ts','o','h','l','c','v','t'])
    for col in ['o','h','l','c','v']:
        df[col] = pd.to_numeric(df[col])
    df['ts'] = pd.to_datetime(df['ts'].astype(int), unit='ms')
    df = df.sort_values('ts').reset_index(drop=True)
    df = df[df['ts'] >= datetime(2025, 1, 1)]
    print(f"✅ {len(df)} свечей")
    return df


def add_indicators(df):
    """Добавить индикаторы"""
    # RSI
    delta = df['c'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / (loss + 1e-10)))
    
    # EMA
    df['ema9'] = df['c'].ewm(span=9).mean()
    df['ema21'] = df['c'].ewm(span=21).mean()
    df['ema50'] = df['c'].ewm(span=50).mean()
    
    # MACD
    df['macd'] = df['c'].ewm(span=12).mean() - df['c'].ewm(span=26).mean()
    df['macd_s'] = df['macd'].ewm(span=9).mean()
    
    # Stoch
    low14 = df['l'].rolling(14).min()
    high14 = df['h'].rolling(14).max()
    df['stoch'] = ((df['c'] - low14) / (high14 - low14 + 1e-10)) * 100
    
    # BB
    df['bb_mid'] = df['c'].rolling(20).mean()
    df['bb_std'] = df['c'].rolling(20).std()
    df['bb_up'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lo'] = df['bb_mid'] - 2 * df['bb_std']
    
    return df


# 15 стратегий для теста
STRATEGIES = {
    "RSI_30": lambda df, i: df.iloc[i]['rsi'] < 30,
    "RSI_35": lambda df, i: df.iloc[i]['rsi'] < 35,
    "RSI_40": lambda df, i: df.iloc[i]['rsi'] < 40 and df.iloc[i]['c'] > df.iloc[i]['ema21'],
    "EMA_CROSS": lambda df, i: df.iloc[i-1]['ema9'] <= df.iloc[i-1]['ema21'] and df.iloc[i]['ema9'] > df.iloc[i]['ema21'],
    "MACD_CROSS": lambda df, i: df.iloc[i-1]['macd'] <= df.iloc[i-1]['macd_s'] and df.iloc[i]['macd'] > df.iloc[i]['macd_s'],
    "STOCH_20": lambda df, i: df.iloc[i]['stoch'] < 20,
    "STOCH_25": lambda df, i: df.iloc[i]['stoch'] < 25,
    "BB_BOUNCE": lambda df, i: df.iloc[i-1]['c'] <= df.iloc[i-1]['bb_lo'] and df.iloc[i]['c'] > df.iloc[i]['bb_lo'],
    "RSI_EMA": lambda df, i: df.iloc[i]['rsi'] < 40 and df.iloc[i]['ema9'] > df.iloc[i]['ema21'],
    "TRIPLE": lambda df, i: df.iloc[i]['rsi'] < 45 and df.iloc[i]['macd'] > df.iloc[i]['macd_s'] and df.iloc[i]['c'] > df.iloc[i]['ema21'],
    "PULLBACK": lambda df, i: df.iloc[i]['ema9'] > df.iloc[i]['ema21'] and df.iloc[i]['rsi'] < 45 and df.iloc[i]['rsi'] > 30,
    "MOMENTUM": lambda df, i: df.iloc[i]['c'] > df.iloc[i-3]['c'] * 1.01 and df.iloc[i]['rsi'] < 60,
    "BREAKOUT": lambda df, i: df.iloc[i]['c'] > df.iloc[i]['bb_up'] and df.iloc[i]['rsi'] < 70,
    "RSI_STOCH": lambda df, i: df.iloc[i]['rsi'] < 40 and df.iloc[i]['stoch'] < 30,
    "EMA_MACD": lambda df, i: df.iloc[i]['ema9'] > df.iloc[i]['ema21'] and df.iloc[i]['macd'] > 0,
}


def backtest(df, strategy_func, sl=0.015, tp=0.025):
    """Бэктест одной стратегии"""
    trades = []
    last_trade = 0
    
    for i in range(50, len(df)):
        if i - last_trade < 2:  # Мин 2 часа между сделками
            continue
        
        try:
            if strategy_func(df, i):
                entry = df.iloc[i]['c']
                sl_price = entry * (1 - sl)
                tp_price = entry * (1 + tp)
                
                # Ищем выход
                for j in range(i+1, min(i+48, len(df))):
                    if df.iloc[j]['l'] <= sl_price:
                        pnl = -sl - 0.002  # SL + комиссия
                        trades.append(pnl)
                        last_trade = j
                        break
                    elif df.iloc[j]['h'] >= tp_price:
                        pnl = tp - 0.002  # TP + комиссия
                        trades.append(pnl)
                        last_trade = j
                        break
        except:
            continue
    
    return trades


async def main():
    symbols = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA"]
    
    print("=" * 70)
    print("📊 БЫСТРЫЙ ТЕСТ СТРАТЕГИЙ - СПОТ (Январь 2025)")
    print("=" * 70)
    print(f"⏰ Старт: {datetime.now().strftime('%H:%M:%S')}")
    print(f"📈 Стратегий: {len(STRATEGIES)}")
    print(f"🪙 Монет: {len(symbols)}")
    print(f"📊 SL: 1.5% | TP: 2.5%")
    print("-" * 70)
    
    results = {s: {'trades': 0, 'wins': 0, 'pnl': 0} for s in STRATEGIES}
    
    print("\n📥 Загрузка данных:")
    for symbol in symbols:
        df = await load_data(symbol)
        if df.empty:
            continue
        df = add_indicators(df)
        
        for name, func in STRATEGIES.items():
            trades = backtest(df, func)
            results[name]['trades'] += len(trades)
            results[name]['wins'] += sum(1 for t in trades if t > 0)
            results[name]['pnl'] += sum(trades) * 100
    
    print("\n" + "=" * 70)
    print("📋 РЕЗУЛЬТАТЫ")
    print("=" * 70)
    print(f"{'Стратегия':<15} | {'Сделок':>7} | {'WR':>6} | {'PnL':>8} | {'Сиг/день':>8}")
    print("-" * 70)
    
    sorted_results = sorted(results.items(), key=lambda x: x[1]['pnl'], reverse=True)
    
    for name, data in sorted_results:
        if data['trades'] > 0:
            wr = data['wins'] / data['trades'] * 100
            daily = data['trades'] / 27  # ~27 дней в январе
            emoji = "✅" if wr >= 55 and data['pnl'] > 0 else "❌"
            print(f"{emoji} {name:<13} | {data['trades']:>7} | {wr:>5.1f}% | {data['pnl']:>+7.1f}% | {daily:>7.1f}")
    
    # Лучшие
    good = [(n, d) for n, d in sorted_results if d['trades'] > 10 and d['wins']/d['trades'] >= 0.55 and d['pnl'] > 0]
    
    print("\n" + "=" * 70)
    print(f"🏆 ЛУЧШИЕ СТРАТЕГИИ (WR >= 55%, PnL > 0): {len(good)}")
    print("=" * 70)
    
    total_signals = 0
    for name, data in good[:7]:
        daily = data['trades'] / 27
        total_signals += daily
        wr = data['wins'] / data['trades'] * 100
        print(f"   ✅ {name}: {daily:.1f} сиг/день, WR {wr:.0f}%, PnL {data['pnl']:+.1f}%")
    
    if good:
        avg_wr = sum(d['wins']/d['trades'] for _, d in good) / len(good) * 100
        total_pnl = sum(d['pnl'] for _, d in good)
        print(f"\n📊 ИТОГО: ~{total_signals:.0f} сигналов в день с {len(good)} стратегий")
        print(f"📈 Средний WR: {avg_wr:.0f}%")
        print(f"💰 Общий PnL: {total_pnl:+.1f}%")
    else:
        print("\n⚠️ Нет стратегий с WR >= 55% и положительным PnL")
        print("   Рекомендуется пересмотреть параметры SL/TP")
    
    print("\n" + "=" * 70)
    print(f"⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
