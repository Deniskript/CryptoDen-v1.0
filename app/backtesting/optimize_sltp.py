"""
Оптимизация SL/TP для поиска прибыльных параметров
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime
import aiohttp
import sys
sys.path.insert(0, '/root/crypto-bot')


async def load_data(symbol: str):
    """Загрузить данные с Bybit"""
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
        return pd.DataFrame()
    
    df = pd.DataFrame(klines, columns=['ts','o','h','l','c','v','t'])
    for col in ['o','h','l','c','v']:
        df[col] = pd.to_numeric(df[col])
    df['ts'] = pd.to_datetime(df['ts'].astype(int), unit='ms')
    df = df.sort_values('ts').reset_index(drop=True)
    df = df[df['ts'] >= datetime(2025, 1, 1)]
    return df


def add_indicators(df):
    """Добавить индикаторы"""
    delta = df['c'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / (loss + 1e-10)))
    
    df['ema9'] = df['c'].ewm(span=9).mean()
    df['ema21'] = df['c'].ewm(span=21).mean()
    df['ema50'] = df['c'].ewm(span=50).mean()
    
    df['macd'] = df['c'].ewm(span=12).mean() - df['c'].ewm(span=26).mean()
    df['macd_s'] = df['macd'].ewm(span=9).mean()
    
    low14 = df['l'].rolling(14).min()
    high14 = df['h'].rolling(14).max()
    df['stoch'] = ((df['c'] - low14) / (high14 - low14 + 1e-10)) * 100
    
    df['bb_mid'] = df['c'].rolling(20).mean()
    df['bb_std'] = df['c'].rolling(20).std()
    df['bb_up'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lo'] = df['bb_mid'] - 2 * df['bb_std']
    
    # ATR для динамических SL/TP
    tr = pd.concat([
        df['h'] - df['l'],
        abs(df['h'] - df['c'].shift()),
        abs(df['l'] - df['c'].shift())
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = df['atr'] / df['c'] * 100
    
    return df


# Топ стратегии для оптимизации
STRATEGIES = {
    "RSI_30": lambda df, i: df.iloc[i]['rsi'] < 30,
    "RSI_35": lambda df, i: df.iloc[i]['rsi'] < 35,
    "RSI_40_EMA": lambda df, i: df.iloc[i]['rsi'] < 40 and df.iloc[i]['c'] > df.iloc[i]['ema21'],
    "STOCH_20": lambda df, i: df.iloc[i]['stoch'] < 20,
    "BB_BOUNCE": lambda df, i: df.iloc[i-1]['c'] <= df.iloc[i-1]['bb_lo'] and df.iloc[i]['c'] > df.iloc[i]['bb_lo'],
    "RSI_STOCH": lambda df, i: df.iloc[i]['rsi'] < 40 and df.iloc[i]['stoch'] < 30,
    "TRIPLE": lambda df, i: df.iloc[i]['rsi'] < 45 and df.iloc[i]['macd'] > df.iloc[i]['macd_s'] and df.iloc[i]['c'] > df.iloc[i]['ema21'],
}


def backtest(df, strategy_func, sl_pct, tp_pct, max_hold=24):
    """Бэктест с заданными SL/TP"""
    trades = []
    last_trade = 0
    
    for i in range(50, len(df)):
        if i - last_trade < 2:
            continue
        
        try:
            if strategy_func(df, i):
                entry = df.iloc[i]['c']
                sl_price = entry * (1 - sl_pct)
                tp_price = entry * (1 + tp_pct)
                
                for j in range(i+1, min(i+max_hold, len(df))):
                    if df.iloc[j]['l'] <= sl_price:
                        trades.append(-sl_pct - 0.002)
                        last_trade = j
                        break
                    elif df.iloc[j]['h'] >= tp_price:
                        trades.append(tp_pct - 0.002)
                        last_trade = j
                        break
                else:
                    # Выход по времени
                    if i + max_hold < len(df):
                        exit_price = df.iloc[i + max_hold]['c']
                        pnl = (exit_price - entry) / entry - 0.002
                        trades.append(pnl)
                        last_trade = i + max_hold
        except:
            continue
    
    return trades


async def main():
    symbols = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA"]
    
    print("=" * 80)
    print("📊 ОПТИМИЗАЦИЯ SL/TP ДЛЯ СТРАТЕГИЙ")
    print("=" * 80)
    print(f"⏰ Старт: {datetime.now().strftime('%H:%M:%S')}")
    
    # Загрузка данных
    print("\n📥 Загрузка данных...")
    data = {}
    for symbol in symbols:
        print(f"   {symbol}...", end=" ")
        df = await load_data(symbol)
        if not df.empty:
            data[symbol] = add_indicators(df)
            print(f"✅ {len(df)} свечей")
        else:
            print("❌")
    
    # Параметры для тестирования
    sl_values = [0.005, 0.008, 0.01, 0.012, 0.015, 0.02, 0.025, 0.03]  # 0.5% - 3%
    tp_values = [0.005, 0.008, 0.01, 0.012, 0.015, 0.02, 0.025, 0.03]  # 0.5% - 3%
    
    print("\n" + "=" * 80)
    print("📊 ТЕСТИРОВАНИЕ КОМБИНАЦИЙ SL/TP")
    print("=" * 80)
    
    best_results = []
    
    for name, func in STRATEGIES.items():
        print(f"\n🔍 {name}:")
        
        strategy_best = None
        
        for sl in sl_values:
            for tp in tp_values:
                total_trades = 0
                total_wins = 0
                total_pnl = 0
                
                for symbol, df in data.items():
                    trades = backtest(df, func, sl, tp)
                    total_trades += len(trades)
                    total_wins += sum(1 for t in trades if t > 0)
                    total_pnl += sum(trades) * 100
                
                if total_trades >= 20:
                    wr = total_wins / total_trades * 100
                    
                    if strategy_best is None or total_pnl > strategy_best['pnl']:
                        strategy_best = {
                            'strategy': name,
                            'sl': sl,
                            'tp': tp,
                            'trades': total_trades,
                            'wr': wr,
                            'pnl': total_pnl,
                        }
        
        if strategy_best:
            emoji = "✅" if strategy_best['pnl'] > 0 and strategy_best['wr'] >= 50 else "❌"
            print(f"   {emoji} Best: SL={strategy_best['sl']*100:.1f}% TP={strategy_best['tp']*100:.1f}% | "
                  f"WR={strategy_best['wr']:.1f}% | PnL={strategy_best['pnl']:+.1f}% | "
                  f"Trades={strategy_best['trades']}")
            best_results.append(strategy_best)
    
    # Итоговая таблица лучших
    print("\n" + "=" * 80)
    print("🏆 ЛУЧШИЕ КОМБИНАЦИИ")
    print("=" * 80)
    
    # Сортируем по PnL
    best_results.sort(key=lambda x: x['pnl'], reverse=True)
    
    print(f"{'Стратегия':<15} | {'SL':>5} | {'TP':>5} | {'WR':>6} | {'PnL':>8} | {'Trades':>7}")
    print("-" * 80)
    
    profitable = []
    for r in best_results:
        emoji = "✅" if r['pnl'] > 0 and r['wr'] >= 50 else "❌"
        print(f"{emoji} {r['strategy']:<13} | {r['sl']*100:>4.1f}% | {r['tp']*100:>4.1f}% | "
              f"{r['wr']:>5.1f}% | {r['pnl']:>+7.1f}% | {r['trades']:>7}")
        
        if r['pnl'] > 0 and r['wr'] >= 50:
            profitable.append(r)
    
    print("\n" + "=" * 80)
    print(f"📊 ПРИБЫЛЬНЫХ СТРАТЕГИЙ: {len(profitable)}")
    print("=" * 80)
    
    if profitable:
        # Рекомендуемые параметры
        avg_sl = np.mean([r['sl'] for r in profitable])
        avg_tp = np.mean([r['tp'] for r in profitable])
        total_pnl = sum(r['pnl'] for r in profitable)
        
        print(f"\n💡 РЕКОМЕНДАЦИИ:")
        print(f"   • Средний оптимальный SL: {avg_sl*100:.2f}%")
        print(f"   • Средний оптимальный TP: {avg_tp*100:.2f}%")
        print(f"   • Соотношение TP/SL: {avg_tp/avg_sl:.2f}:1")
        print(f"   • Общий потенциальный PnL: {total_pnl:+.1f}%")
        
        print(f"\n🎯 СТРАТЕГИИ ДЛЯ ИСПОЛЬЗОВАНИЯ:")
        for r in profitable:
            daily = r['trades'] / 27
            print(f"   ✅ {r['strategy']}: SL={r['sl']*100:.1f}%, TP={r['tp']*100:.1f}%, {daily:.1f} сиг/день")
    else:
        print("\n⚠️ Нет прибыльных комбинаций.")
        print("   Рынок январь 2025 был сложным для этих стратегий.")
        print("\n💡 РЕКОМЕНДАЦИИ:")
        print("   1. Попробовать более длинные таймфреймы (4H, 1D)")
        print("   2. Добавить фильтр тренда (торговать только по тренду)")
        print("   3. Увеличить SL до 2-3% для волатильных монет")
        print("   4. Рассмотреть SHORT стратегии для медвежьего рынка")
    
    print("\n" + "=" * 80)
    print(f"⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
