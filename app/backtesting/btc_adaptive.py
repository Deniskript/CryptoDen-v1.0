"""
🎯 BTC АДАПТИВНАЯ СТРАТЕГИЯ
Работает в любом рынке: LONG + SHORT + RANGE
Тест на 2024 году (все типы рынка)
"""
import json
import pandas as pd
import numpy as np
from datetime import datetime


def load_btc():
    """Загрузка BTC 1H 2024"""
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
    df = df.dropna()
    print(f"✅ BTC 1H 2024: {len(df)} свечей ({len(df)//24} дней)")
    return df


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
    
    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    
    # Bollinger
    df['bb_mid'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    
    # ATR для динамического SL
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = df['atr'] / df['close'] * 100
    
    # ТРЕНД (ключевое!)
    df['trend'] = 'SIDE'
    df.loc[(df['close'] > df['ema200']) & (df['ema50'] > df['ema200']), 'trend'] = 'UP'
    df.loc[(df['close'] < df['ema200']) & (df['ema50'] < df['ema200']), 'trend'] = 'DOWN'
    
    return df


def backtest_adaptive(df, sl_pct, tp_pct):
    """
    АДАПТИВНЫЙ бэктест:
    - UP тренд → LONG сигналы
    - DOWN тренд → SHORT сигналы
    - SIDE → осторожные сделки
    """
    trades = []
    last_exit = 0
    
    for i in range(200, len(df) - 50):
        if i - last_exit < 4:  # Cooldown 4 часа
            continue
        
        trend = df.iloc[i]['trend']
        rsi = df.iloc[i]['rsi']
        stoch = df.iloc[i]['stoch']
        close = df.iloc[i]['close']
        bb_lower = df.iloc[i]['bb_lower']
        bb_upper = df.iloc[i]['bb_upper']
        macd = df.iloc[i]['macd']
        macd_sig = df.iloc[i]['macd_signal']
        
        signal = None
        direction = None
        
        # === UPTREND: Только LONG ===
        if trend == 'UP':
            # RSI перепродан в восходящем тренде = покупка
            if rsi < 35 and stoch < 30:
                signal = "UP_RSI_LONG"
                direction = "LONG"
            # Отскок от BB lower в тренде
            elif close < bb_lower and rsi < 40:
                signal = "UP_BB_LONG"
                direction = "LONG"
            # MACD пересечение вверх
            elif i > 0 and df.iloc[i-1]['macd'] < df.iloc[i-1]['macd_signal'] and macd > macd_sig and rsi < 50:
                signal = "UP_MACD_LONG"
                direction = "LONG"
        
        # === DOWNTREND: Только SHORT ===
        elif trend == 'DOWN':
            # RSI перекуплен в нисходящем тренде = продажа
            if rsi > 65 and stoch > 70:
                signal = "DOWN_RSI_SHORT"
                direction = "SHORT"
            # Отскок от BB upper в тренде
            elif close > bb_upper and rsi > 60:
                signal = "DOWN_BB_SHORT"
                direction = "SHORT"
            # MACD пересечение вниз
            elif i > 0 and df.iloc[i-1]['macd'] > df.iloc[i-1]['macd_signal'] and macd < macd_sig and rsi > 50:
                signal = "DOWN_MACD_SHORT"
                direction = "SHORT"
        
        # === SIDEWAYS: Range торговля ===
        else:
            # Экстремальная перепроданность
            if rsi < 25 and stoch < 20:
                signal = "SIDE_EXTREME_LONG"
                direction = "LONG"
            # Экстремальная перекупленность
            elif rsi > 75 and stoch > 80:
                signal = "SIDE_EXTREME_SHORT"
                direction = "SHORT"
        
        if not signal:
            continue
        
        # Открываем сделку
        entry = close
        
        if direction == "LONG":
            sl_price = entry * (1 - sl_pct / 100)
            tp_price = entry * (1 + tp_pct / 100)
        else:
            sl_price = entry * (1 + sl_pct / 100)
            tp_price = entry * (1 - tp_pct / 100)
        
        # Ищем выход (макс 48 часов)
        result = None
        for j in range(i + 1, min(i + 48, len(df))):
            high = df.iloc[j]['high']
            low = df.iloc[j]['low']
            
            if direction == "LONG":
                if low <= sl_price:
                    result = {"signal": signal, "pnl": -sl_pct - 0.2, "won": False, "trend": trend}
                    last_exit = j
                    break
                elif high >= tp_price:
                    result = {"signal": signal, "pnl": tp_pct - 0.2, "won": True, "trend": trend}
                    last_exit = j
                    break
            else:
                if high >= sl_price:
                    result = {"signal": signal, "pnl": -sl_pct - 0.2, "won": False, "trend": trend}
                    last_exit = j
                    break
                elif low <= tp_price:
                    result = {"signal": signal, "pnl": tp_pct - 0.2, "won": True, "trend": trend}
                    last_exit = j
                    break
        
        if result:
            trades.append(result)
    
    return trades


def analyze_results(trades):
    """Детальный анализ"""
    if not trades:
        print("❌ Нет сделок!")
        return
    
    df_trades = pd.DataFrame(trades)
    
    # Общая статистика
    total = len(trades)
    wins = df_trades['won'].sum()
    total_pnl = df_trades['pnl'].sum()
    
    print(f"\n{'='*60}")
    print(f"📊 ОБЩАЯ СТАТИСТИКА")
    print(f"{'='*60}")
    print(f"   Всего сделок: {total}")
    print(f"   Выигрышей: {wins} ({wins/total*100:.1f}%)")
    print(f"   Проигрышей: {total - wins} ({(total-wins)/total*100:.1f}%)")
    print(f"   Общий PnL: {total_pnl:+.1f}%")
    print(f"   Средний PnL/сделку: {total_pnl/total:+.2f}%")
    
    # По типу рынка
    print(f"\n{'='*60}")
    print(f"📈 ПО ТИПУ РЫНКА")
    print(f"{'='*60}")
    
    for trend in ['UP', 'DOWN', 'SIDE']:
        trend_trades = df_trades[df_trades['trend'] == trend]
        if len(trend_trades) == 0:
            continue
        
        t_wins = trend_trades['won'].sum()
        t_pnl = trend_trades['pnl'].sum()
        emoji = "🟢" if t_pnl > 0 else "🔴"
        
        print(f"\n   {emoji} {trend}:")
        print(f"      Сделок: {len(trend_trades)}")
        print(f"      WinRate: {t_wins/len(trend_trades)*100:.1f}%")
        print(f"      PnL: {t_pnl:+.1f}%")
    
    # По сигналам
    print(f"\n{'='*60}")
    print(f"🎯 ПО СИГНАЛАМ")
    print(f"{'='*60}")
    
    for signal in df_trades['signal'].unique():
        sig_trades = df_trades[df_trades['signal'] == signal]
        s_wins = sig_trades['won'].sum()
        s_pnl = sig_trades['pnl'].sum()
        emoji = "✅" if s_pnl > 0 and s_wins/len(sig_trades) >= 0.5 else "❌"
        
        print(f"   {emoji} {signal:<20} | "
              f"Trades: {len(sig_trades):>3} | "
              f"WR: {s_wins/len(sig_trades)*100:>5.1f}% | "
              f"PnL: {s_pnl:>+6.1f}%")
    
    # Расчёт на месяц
    days = 365  # 2024 год
    monthly_trades = total / 12
    monthly_pnl = total_pnl / 12
    
    print(f"\n{'='*60}")
    print(f"📅 ПРОЕКЦИЯ")
    print(f"{'='*60}")
    print(f"   Сделок в месяц: ~{monthly_trades:.0f}")
    print(f"   PnL в месяц: ~{monthly_pnl:+.1f}%")
    print(f"   PnL в год: ~{total_pnl:+.1f}%")


def main():
    print("="*60)
    print("🎯 BTC АДАПТИВНАЯ СТРАТЕГИЯ")
    print("   Работает в ЛЮБОМ рынке!")
    print("="*60)
    print(f"⏰ Старт: {datetime.now().strftime('%H:%M:%S')}")
    
    # Загрузка
    df = load_btc()
    df = add_indicators(df)
    
    # Статистика трендов
    print(f"\n📊 Распределение трендов в 2024:")
    for t in ['UP', 'DOWN', 'SIDE']:
        cnt = (df['trend'] == t).sum()
        print(f"   {t}: {cnt} часов ({cnt/len(df)*100:.1f}%)")
    
    # Тест разных SL/TP
    print(f"\n🔍 Тестирую SL/TP комбинации...")
    
    best_result = None
    best_params = None
    
    for sl in [1.0, 1.2, 1.5, 2.0]:
        for tp in [2.0, 2.5, 3.0, 3.5]:
            if tp <= sl:
                continue
            
            trades = backtest_adaptive(df, sl, tp)
            
            if trades:
                wins = sum(1 for t in trades if t['won'])
                pnl = sum(t['pnl'] for t in trades)
                wr = wins / len(trades) * 100
                
                emoji = "✅" if pnl > 0 and wr >= 50 else "❌"
                print(f"   {emoji} SL={sl}% TP={tp}% | Trades: {len(trades):>3} | WR: {wr:>5.1f}% | PnL: {pnl:>+7.1f}%")
                
                if best_result is None or pnl > best_result:
                    best_result = pnl
                    best_params = (sl, tp, trades)
    
    # Лучший результат
    if best_params:
        sl, tp, trades = best_params
        print(f"\n{'='*60}")
        print(f"🏆 ЛУЧШАЯ КОМБИНАЦИЯ: SL={sl}% TP={tp}%")
        print(f"{'='*60}")
        
        analyze_results(trades)
    else:
        print("\n❌ Нет прибыльных комбинаций!")
    
    print(f"\n⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
