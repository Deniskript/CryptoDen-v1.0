"""
🎯 ГЛУБОКИЙ АНАЛИЗ BTC
Цель: найти идеальную стратегию для BTC
"""
import pandas as pd
import numpy as np
from datetime import datetime
import sys
sys.path.insert(0, '/root/crypto-bot')


def load_data():
    """Загрузка данных BTC"""
    # Пробуем разные пути
    paths = [
        "data/BTC_5m_2025_2025.csv",
        "data/BTC_2024_5m.json",
        "data/BTCUSDT_5m.csv"
    ]
    
    for path in paths:
        try:
            if path.endswith('.csv'):
                df = pd.read_csv(path)
            elif path.endswith('.json'):
                df = pd.read_json(path)
            
            print(f"✅ Загружен: {path} ({len(df)} свечей)")
            
            # Нормализуем названия колонок
            if 'open' not in df.columns and 'Open' in df.columns:
                df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 
                                   'Close': 'close', 'Volume': 'volume'}, inplace=True)
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna()
            
            # Добавляем дату если есть timestamp
            if 'timestamp' in df.columns:
                df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            return df
        except Exception as e:
            continue
    
    print("❌ Данные не найдены!")
    print("   Попробуйте загрузить данные с Bybit сначала")
    return pd.DataFrame()


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Добавить ВСЕ индикаторы для анализа"""
    df = df.copy()
    
    # === RSI (разные периоды) ===
    for period in [7, 14, 21]:
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        df[f'rsi_{period}'] = 100 - (100 / (1 + gain / (loss + 1e-10)))
    
    # === EMA (разные периоды) ===
    for period in [9, 21, 50, 100, 200]:
        df[f'ema_{period}'] = df['close'].ewm(span=period).mean()
    
    # === SMA ===
    for period in [20, 50, 200]:
        df[f'sma_{period}'] = df['close'].rolling(period).mean()
    
    # === Stochastic ===
    for period in [14, 21]:
        low_n = df['low'].rolling(period).min()
        high_n = df['high'].rolling(period).max()
        df[f'stoch_{period}'] = ((df['close'] - low_n) / (high_n - low_n + 1e-10)) * 100
        df[f'stoch_{period}_d'] = df[f'stoch_{period}'].rolling(3).mean()
    
    # === MACD ===
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # === Bollinger Bands ===
    df['bb_mid'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid'] * 100
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)
    
    # === ATR (волатильность) ===
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(14).mean()
    df['atr_percent'] = df['atr_14'] / df['close'] * 100
    
    # === Тренд (EMA200) ===
    df['trend'] = 'SIDEWAYS'
    df.loc[(df['close'] > df['ema_200']) & (df['ema_50'] > df['ema_200']), 'trend'] = 'UPTREND'
    df.loc[(df['close'] < df['ema_200']) & (df['ema_50'] < df['ema_200']), 'trend'] = 'DOWNTREND'
    
    # === Volume ===
    df['volume_sma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / (df['volume_sma'] + 1e-10)
    
    return df


def analyze_trends(df: pd.DataFrame):
    """Анализ распределения трендов"""
    print("\n" + "=" * 60)
    print("📊 АНАЛИЗ ТРЕНДОВ BTC")
    print("=" * 60)
    
    trend_counts = df['trend'].value_counts()
    total = len(df)
    
    for trend, count in trend_counts.items():
        pct = count / total * 100
        print(f"   {trend}: {count} свечей ({pct:.1f}%)")
    
    return trend_counts


def backtest_strategy(df: pd.DataFrame, name: str, condition_func, 
                      direction: str, sl_pct: float, tp_pct: float,
                      trend_filter: str = None) -> dict:
    """Бэктест одной стратегии"""
    trades = []
    last_exit = 0
    commission = 0.001
    
    for i in range(200, len(df) - 100):
        # Cooldown
        if i - last_exit < 12:
            continue
        
        # Фильтр тренда
        if trend_filter and df.iloc[i]['trend'] != trend_filter:
            continue
        
        # Проверка условия
        try:
            if not condition_func(df, i):
                continue
        except:
            continue
        
        entry_price = df.iloc[i]['close']
        
        # SL/TP
        if direction == "LONG":
            sl_price = entry_price * (1 - sl_pct / 100)
            tp_price = entry_price * (1 + tp_pct / 100)
        else:
            sl_price = entry_price * (1 + sl_pct / 100)
            tp_price = entry_price * (1 - tp_pct / 100)
        
        # Поиск выхода
        for j in range(i + 1, min(i + 576, len(df))):
            high = df.iloc[j]['high']
            low = df.iloc[j]['low']
            
            if direction == "LONG":
                if low <= sl_price:
                    trades.append({"pnl": -sl_pct - commission * 200, "won": False})
                    last_exit = j
                    break
                elif high >= tp_price:
                    trades.append({"pnl": tp_pct - commission * 200, "won": True})
                    last_exit = j
                    break
            else:
                if high >= sl_price:
                    trades.append({"pnl": -sl_pct - commission * 200, "won": False})
                    last_exit = j
                    break
                elif low <= tp_price:
                    trades.append({"pnl": tp_pct - commission * 200, "won": True})
                    last_exit = j
                    break
    
    if not trades:
        return {"name": name, "trades": 0, "wr": 0, "pnl": 0, "avg": 0}
    
    wins = sum(1 for t in trades if t["won"])
    total_pnl = sum(t["pnl"] for t in trades)
    
    return {
        "name": name,
        "direction": direction,
        "trend_filter": trend_filter,
        "sl": sl_pct,
        "tp": tp_pct,
        "trades": len(trades),
        "wr": wins / len(trades) * 100,
        "pnl": total_pnl,
        "avg": total_pnl / len(trades)
    }


# === СТРАТЕГИИ ДЛЯ ТЕСТА ===

def rsi_oversold(df, i):
    return df.iloc[i]['rsi_14'] < 30

def rsi_oversold_35(df, i):
    return df.iloc[i]['rsi_14'] < 35

def rsi_oversold_40(df, i):
    return df.iloc[i]['rsi_14'] < 40

def rsi_overbought(df, i):
    return df.iloc[i]['rsi_14'] > 70

def rsi_overbought_65(df, i):
    return df.iloc[i]['rsi_14'] > 65

def rsi_ema_long(df, i):
    return df.iloc[i]['rsi_14'] < 35 and df.iloc[i]['close'] > df.iloc[i]['ema_21']

def rsi_ema_short(df, i):
    return df.iloc[i]['rsi_14'] > 65 and df.iloc[i]['close'] < df.iloc[i]['ema_21']

def stoch_oversold(df, i):
    return df.iloc[i]['stoch_14'] < 20

def stoch_overbought(df, i):
    return df.iloc[i]['stoch_14'] > 80

def bb_lower_touch(df, i):
    return df.iloc[i]['close'] < df.iloc[i]['bb_lower']

def bb_upper_touch(df, i):
    return df.iloc[i]['close'] > df.iloc[i]['bb_upper']

def macd_cross_up(df, i):
    if i < 1:
        return False
    return df.iloc[i-1]['macd'] < df.iloc[i-1]['macd_signal'] and \
           df.iloc[i]['macd'] > df.iloc[i]['macd_signal']

def macd_cross_down(df, i):
    if i < 1:
        return False
    return df.iloc[i-1]['macd'] > df.iloc[i-1]['macd_signal'] and \
           df.iloc[i]['macd'] < df.iloc[i]['macd_signal']

def rsi_stoch_long(df, i):
    return df.iloc[i]['rsi_14'] < 35 and df.iloc[i]['stoch_14'] < 25

def rsi_stoch_short(df, i):
    return df.iloc[i]['rsi_14'] > 65 and df.iloc[i]['stoch_14'] > 75


def main():
    print("=" * 60)
    print("🎯 ГЛУБОКИЙ АНАЛИЗ BTC")
    print("=" * 60)
    print(f"⏰ Старт: {datetime.now().strftime('%H:%M:%S')}")
    
    # Загрузка данных
    df = load_data()
    if df.empty:
        return
    
    # Добавляем индикаторы
    print("\n📊 Добавляю индикаторы...")
    df = add_all_indicators(df)
    print(f"   Готово! {len(df)} свечей с индикаторами")
    
    # Анализ трендов
    analyze_trends(df)
    
    # === ТЕСТ СТРАТЕГИЙ ===
    print("\n" + "=" * 60)
    print("🔍 ТЕСТ СТРАТЕГИЙ")
    print("=" * 60)
    
    # SL/TP комбинации
    sltp_combos = [
        (0.8, 2.0), (0.8, 2.5), (1.0, 2.0), (1.0, 2.5), (1.0, 3.0),
        (1.2, 2.5), (1.2, 3.0), (1.5, 3.0), (1.5, 3.5)
    ]
    
    # Стратегии для теста
    strategies = [
        # LONG без фильтра
        ("RSI<30 LONG", rsi_oversold, "LONG", None),
        ("RSI<35 LONG", rsi_oversold_35, "LONG", None),
        ("RSI<35+EMA LONG", rsi_ema_long, "LONG", None),
        ("STOCH<20 LONG", stoch_oversold, "LONG", None),
        ("BB_LOW LONG", bb_lower_touch, "LONG", None),
        ("RSI+STOCH LONG", rsi_stoch_long, "LONG", None),
        ("MACD_CROSS LONG", macd_cross_up, "LONG", None),
        
        # LONG с фильтром UPTREND
        ("RSI<30 LONG [UP]", rsi_oversold, "LONG", "UPTREND"),
        ("RSI<35 LONG [UP]", rsi_oversold_35, "LONG", "UPTREND"),
        ("RSI<35+EMA LONG [UP]", rsi_ema_long, "LONG", "UPTREND"),
        ("STOCH<20 LONG [UP]", stoch_oversold, "LONG", "UPTREND"),
        ("MACD_CROSS LONG [UP]", macd_cross_up, "LONG", "UPTREND"),
        
        # SHORT без фильтра
        ("RSI>70 SHORT", rsi_overbought, "SHORT", None),
        ("RSI>65 SHORT", rsi_overbought_65, "SHORT", None),
        ("RSI>65+EMA SHORT", rsi_ema_short, "SHORT", None),
        ("STOCH>80 SHORT", stoch_overbought, "SHORT", None),
        ("BB_HIGH SHORT", bb_upper_touch, "SHORT", None),
        ("RSI+STOCH SHORT", rsi_stoch_short, "SHORT", None),
        ("MACD_CROSS SHORT", macd_cross_down, "SHORT", None),
        
        # SHORT с фильтром DOWNTREND
        ("RSI>70 SHORT [DOWN]", rsi_overbought, "SHORT", "DOWNTREND"),
        ("RSI>65 SHORT [DOWN]", rsi_overbought_65, "SHORT", "DOWNTREND"),
        ("RSI>65+EMA SHORT [DOWN]", rsi_ema_short, "SHORT", "DOWNTREND"),
        ("STOCH>80 SHORT [DOWN]", stoch_overbought, "SHORT", "DOWNTREND"),
        ("MACD_CROSS SHORT [DOWN]", macd_cross_down, "SHORT", "DOWNTREND"),
    ]
    
    print(f"   Тестирую {len(strategies)} стратегий...")
    print(f"   Комбинаций SL/TP: {len(sltp_combos)}")
    print(f"   Всего тестов: {len(strategies) * len(sltp_combos)}")
    
    all_results = []
    
    for strat_name, condition, direction, trend_filter in strategies:
        best_result = None
        
        for sl, tp in sltp_combos:
            result = backtest_strategy(df, strat_name, condition, direction, sl, tp, trend_filter)
            
            if result["trades"] > 10:  # Минимум 10 сделок
                if best_result is None or result["pnl"] > best_result["pnl"]:
                    best_result = result
        
        if best_result and best_result["trades"] > 10:
            all_results.append(best_result)
    
    # Сортируем по PnL
    all_results.sort(key=lambda x: x["pnl"], reverse=True)
    
    # Вывод результатов
    print("\n" + "=" * 80)
    print("📋 РЕЗУЛЬТАТЫ (отсортировано по PnL)")
    print("=" * 80)
    print(f"{'Стратегия':<25} | {'SL':>5} | {'TP':>5} | {'Trades':>6} | {'WR':>6} | {'PnL':>8}")
    print("-" * 80)
    
    profitable = []
    
    for r in all_results:
        emoji = "✅" if r["pnl"] > 0 and r["wr"] >= 50 else "⚠️" if r["pnl"] > 0 else "❌"
        print(f"{emoji} {r['name']:<23} | {r['sl']:>4}% | {r['tp']:>4}% | "
              f"{r['trades']:>6} | {r['wr']:>5.1f}% | {r['pnl']:>+7.1f}%")
        
        if r["pnl"] > 0 and r["wr"] >= 50:
            profitable.append(r)
    
    # Лучшие стратегии
    print("\n" + "=" * 80)
    print(f"🏆 ПРИБЫЛЬНЫХ СТРАТЕГИЙ: {len(profitable)}")
    print("=" * 80)
    
    if profitable:
        print("\n🎯 ТОП-5 ЛУЧШИХ ДЛЯ BTC:")
        for i, r in enumerate(profitable[:5], 1):
            print(f"\n   #{i} {r['name']}")
            print(f"      Direction: {r['direction']}")
            print(f"      Trend Filter: {r['trend_filter'] or 'None'}")
            print(f"      SL: {r['sl']}% | TP: {r['tp']}%")
            print(f"      Trades: {r['trades']} | WR: {r['wr']:.1f}%")
            print(f"      PnL: {r['pnl']:+.1f}%")
            
            # Расчёт в месяц
            days = len(df) / 288  # 288 свечей в день (5m)
            monthly_trades = r['trades'] / days * 30
            monthly_pnl = r['pnl'] / days * 30
            print(f"      📅 ~{monthly_trades:.0f} trades/month | ~{monthly_pnl:+.1f}%/month")
        
        # Итоговая статистика
        print("\n📊 ОБЩАЯ СТАТИСТИКА ПРИБЫЛЬНЫХ:")
        total_pnl = sum(r['pnl'] for r in profitable)
        avg_wr = sum(r['wr'] for r in profitable) / len(profitable)
        total_trades = sum(r['trades'] for r in profitable)
        
        print(f"   • Всего PnL: {total_pnl:+.1f}%")
        print(f"   • Средний WR: {avg_wr:.1f}%")
        print(f"   • Всего сделок: {total_trades}")
    else:
        print("\n❌ Нет прибыльных стратегий!")
        print("\n💡 ПОПРОБУЙТЕ:")
        print("   1. Другой таймфрейм (1H, 4H)")
        print("   2. Комбинированные стратегии")
        print("   3. Более широкие SL/TP")
    
    print("\n" + "=" * 80)
    print(f"⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    main()
