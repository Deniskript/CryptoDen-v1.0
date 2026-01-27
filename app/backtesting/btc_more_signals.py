"""
🎯 BTC: ТЕСТ 3 ВАРИАНТОВ ДЛЯ БОЛЬШЕГО КОЛИЧЕСТВА СИГНАЛОВ
Вариант A: 5M таймфрейм
Вариант B: Смягчённые условия (1H)
Вариант C: 5M + смягчённые условия
"""
import json
import pandas as pd
import numpy as np
from datetime import datetime


def load_btc_1h():
    """1H данные"""
    df = pd.read_json("data/BTC_2024_1h.json")
    
    # Извлекаем klines
    klines_list = []
    for _, row in df.iterrows():
        kline = row['klines']
        klines_list.append({
            'open': float(kline['open']),
            'high': float(kline['high']),
            'low': float(kline['low']),
            'close': float(kline['close']),
            'volume': float(kline['volume'])
        })
    
    df = pd.DataFrame(klines_list)
    return df.dropna()


def load_btc_5m():
    """5M данные"""
    df = pd.read_json("data/BTC_2024_5m.json")
    
    # Извлекаем klines
    klines_list = []
    for _, row in df.iterrows():
        kline = row['klines']
        klines_list.append({
            'open': float(kline['open']),
            'high': float(kline['high']),
            'low': float(kline['low']),
            'close': float(kline['close']),
            'volume': float(kline['volume'])
        })
    
    df = pd.DataFrame(klines_list)
    return df.dropna()


def add_indicators(df):
    """Индикаторы"""
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / (loss + 1e-10)))
    
    # EMA
    df['ema21'] = df['close'].ewm(span=21).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()
    
    # Stochastic
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch'] = ((df['close'] - low14) / (high14 - low14 + 1e-10)) * 100
    
    # Bollinger
    df['bb_mid'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    
    # Trend
    df['trend'] = 'SIDE'
    df.loc[(df['close'] > df['ema200']) & (df['ema50'] > df['ema200']), 'trend'] = 'UP'
    df.loc[(df['close'] < df['ema200']) & (df['ema50'] < df['ema200']), 'trend'] = 'DOWN'
    
    return df


def backtest(df, timeframe, strict=True, sl_pct=1.5, tp_pct=2.5):
    """
    Бэктест адаптивной стратегии
    strict=True: строгие условия (RSI<35)
    strict=False: мягкие условия (RSI<45)
    """
    trades = []
    
    # Cooldown зависит от таймфрейма
    if timeframe == "5M":
        cooldown = 24  # 2 часа
        max_hold = 288  # 24 часа
    else:
        cooldown = 4   # 4 часа
        max_hold = 48  # 48 часов
    
    # Пороги
    if strict:
        rsi_buy = 35
        rsi_sell = 65
        stoch_buy = 30
        stoch_sell = 70
    else:
        rsi_buy = 45
        rsi_sell = 55
        stoch_buy = 40
        stoch_sell = 60
    
    last_exit = 0
    
    for i in range(200, len(df) - max_hold):
        if i - last_exit < cooldown:
            continue
        
        trend = df.iloc[i]['trend']
        rsi = df.iloc[i]['rsi']
        stoch = df.iloc[i]['stoch']
        close = df.iloc[i]['close']
        bb_lower = df.iloc[i]['bb_lower']
        bb_upper = df.iloc[i]['bb_upper']
        
        signal = None
        direction = None
        
        # === UPTREND: LONG ===
        if trend == 'UP':
            if rsi < rsi_buy and stoch < stoch_buy:
                signal = "UP_RSI"
                direction = "LONG"
            elif close < bb_lower:
                signal = "UP_BB"
                direction = "LONG"
        
        # === DOWNTREND: SHORT ===
        elif trend == 'DOWN':
            if rsi > rsi_sell and stoch > stoch_sell:
                signal = "DOWN_RSI"
                direction = "SHORT"
            elif close > bb_upper:
                signal = "DOWN_BB"
                direction = "SHORT"
        
        # === SIDEWAYS ===
        else:
            if rsi < 25 and stoch < 20:
                signal = "SIDE_LONG"
                direction = "LONG"
            elif rsi > 75 and stoch > 80:
                signal = "SIDE_SHORT"
                direction = "SHORT"
        
        if not signal:
            continue
        
        # Сделка
        entry = close
        
        if direction == "LONG":
            sl_price = entry * (1 - sl_pct / 100)
            tp_price = entry * (1 + tp_pct / 100)
        else:
            sl_price = entry * (1 + sl_pct / 100)
            tp_price = entry * (1 - tp_pct / 100)
        
        for j in range(i + 1, min(i + max_hold, len(df))):
            high = df.iloc[j]['high']
            low = df.iloc[j]['low']
            
            if direction == "LONG":
                if low <= sl_price:
                    trades.append({"pnl": -sl_pct - 0.15, "won": False, "signal": signal})
                    last_exit = j
                    break
                elif high >= tp_price:
                    trades.append({"pnl": tp_pct - 0.15, "won": True, "signal": signal})
                    last_exit = j
                    break
            else:
                if high >= sl_price:
                    trades.append({"pnl": -sl_pct - 0.15, "won": False, "signal": signal})
                    last_exit = j
                    break
                elif low <= tp_price:
                    trades.append({"pnl": tp_pct - 0.15, "won": True, "signal": signal})
                    last_exit = j
                    break
    
    return trades


def analyze(trades, name, days=365):
    """Анализ результатов"""
    if not trades:
        return {"name": name, "trades": 0, "per_day": 0, "wr": 0, "pnl": 0, "per_month": 0, "pnl_month": 0}
    
    wins = sum(1 for t in trades if t['won'])
    pnl = sum(t['pnl'] for t in trades)
    per_day = len(trades) / days
    per_month = len(trades) / 12
    
    return {
        "name": name,
        "trades": len(trades),
        "per_day": per_day,
        "per_month": per_month,
        "wr": wins / len(trades) * 100,
        "pnl": pnl,
        "pnl_month": pnl / 12
    }


def main():
    print("=" * 70)
    print("🎯 ТЕСТ 3 ВАРИАНТОВ ДЛЯ УВЕЛИЧЕНИЯ СИГНАЛОВ")
    print("=" * 70)
    print(f"⏰ Старт: {datetime.now().strftime('%H:%M:%S')}")
    
    results = []
    
    # === ВАРИАНТ D: 1H строгие (базовый) ===
    print("\n📊 Вариант D: 1H строгие (базовый для сравнения)...")
    df_1h = load_btc_1h()
    df_1h = add_indicators(df_1h)
    print(f"   Загружено: {len(df_1h)} свечей ({len(df_1h)//24} дней)")
    
    trades_d = backtest(df_1h, "1H", strict=True, sl_pct=2.0, tp_pct=2.5)
    results.append(analyze(trades_d, "D: 1H строгие (база)"))
    print(f"   ✅ Готово: {len(trades_d)} сделок")
    
    # === ВАРИАНТ B: 1H мягкие условия ===
    print("\n📊 Вариант B: 1H таймфрейм (мягкие условия)...")
    trades_b = backtest(df_1h, "1H", strict=False, sl_pct=2.0, tp_pct=2.5)
    results.append(analyze(trades_b, "B: 1H мягкие"))
    print(f"   ✅ Готово: {len(trades_b)} сделок")
    
    # === ВАРИАНТ A: 5M строгие условия ===
    print("\n📊 Вариант A: 5M таймфрейм (строгие условия)...")
    df_5m = load_btc_5m()
    df_5m = add_indicators(df_5m)
    print(f"   Загружено: {len(df_5m)} свечей ({len(df_5m)//288} дней)")
    
    trades_a = backtest(df_5m, "5M", strict=True, sl_pct=1.0, tp_pct=2.0)
    results.append(analyze(trades_a, "A: 5M строгие"))
    print(f"   ✅ Готово: {len(trades_a)} сделок")
    
    # === ВАРИАНТ C: 5M мягкие условия ===
    print("\n📊 Вариант C: 5M таймфрейм (мягкие условия)...")
    trades_c = backtest(df_5m, "5M", strict=False, sl_pct=1.0, tp_pct=2.0)
    results.append(analyze(trades_c, "C: 5M мягкие"))
    print(f"   ✅ Готово: {len(trades_c)} сделок")
    
    # === РЕЗУЛЬТАТЫ ===
    print("\n" + "=" * 70)
    print("📋 СРАВНЕНИЕ ВАРИАНТОВ")
    print("=" * 70)
    print(f"{'Вариант':<22} | {'Сделок':>6} | {'/День':>6} | {'/Мес':>6} | {'WR':>6} | {'PnL':>8} | {'PnL/мес':>8}")
    print("-" * 70)
    
    for r in results:
        emoji = "✅" if r['pnl'] > 0 and r['wr'] >= 50 else "⚠️" if r['pnl'] > 0 else "❌"
        print(f"{emoji} {r['name']:<20} | {r['trades']:>6} | {r['per_day']:>6.1f} | "
              f"{r['per_month']:>6.1f} | {r['wr']:>5.1f}% | {r['pnl']:>+7.1f}% | {r['pnl_month']:>+7.1f}%")
    
    # === РЕКОМЕНДАЦИЯ ===
    print("\n" + "=" * 70)
    print("🎯 АНАЛИЗ")
    print("=" * 70)
    
    # Найти лучший по балансу сигналов и прибыли
    best = None
    for r in results:
        if r['pnl'] > 0 and r['wr'] >= 50:
            if best is None or (r['per_day'] >= 1 and r['pnl'] > best['pnl']):
                best = r
    
    if best:
        print(f"\n🏆 ЛУЧШИЙ ВАРИАНТ: {best['name']}")
        print(f"   Сигналов в день: {best['per_day']:.1f}")
        print(f"   Win Rate: {best['wr']:.1f}%")
        print(f"   PnL/месяц: {best['pnl_month']:+.1f}%")
        print(f"   PnL/год: {best['pnl']:+.1f}%")
    else:
        print("\n⚠️  Нет явного лидера, все варианты имеют недостатки")
    
    # Детальный вывод по каждому
    print("\n" + "=" * 70)
    print("📊 ДЕТАЛЬНЫЙ АНАЛИЗ")
    print("=" * 70)
    
    all_trades = [("D", trades_d), ("B", trades_b), ("A", trades_a), ("C", trades_c)]
    
    for r, trades in all_trades:
        if trades:
            df_t = pd.DataFrame(trades)
            print(f"\n   {r}:")
            for sig in df_t['signal'].unique():
                sig_trades = df_t[df_t['signal'] == sig]
                sig_wins = sig_trades['won'].sum()
                sig_pnl = sig_trades['pnl'].sum()
                emoji = "✅" if sig_pnl > 0 else "❌"
                print(f"      {emoji} {sig:<15} | {len(sig_trades):>4} сделок | "
                      f"WR: {sig_wins/len(sig_trades)*100:>5.1f}% | PnL: {sig_pnl:>+6.1f}%")
    
    # === 9 МОНЕТ ===
    print("\n" + "=" * 70)
    print("📈 ПРОЕКЦИЯ НА 9 МОНЕТ")
    print("=" * 70)
    
    for r in results:
        if r['pnl'] > 0:
            multi = r['per_day'] * 9
            multi_pnl = r['pnl_month'] * 9
            print(f"   {r['name']}: {multi:.1f} сигналов/день | {multi_pnl:+.1f}%/месяц")
    
    print("\n" + "=" * 70)
    print(f"⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 70)


if __name__ == "__main__":
    main()
