"""
Оптимизация SL/TP для 16 рабочих стратегий
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime
import sys
sys.path.insert(0, '/root/crypto-bot')


# 16 рабочих стратегий
STRATEGIES = {
    # LONG
    "BTC_LONG": {"rsi": 30, "ema": 21, "dir": "LONG"},
    "ETH_LONG": {"rsi": 35, "ema": 50, "dir": "LONG"},
    "BNB_LONG": {"rsi": 30, "ema": 50, "dir": "LONG"},
    "ADA_LONG": {"rsi": 30, "ema": 21, "dir": "LONG"},
    "DOGE_LONG": {"stoch": 25, "dir": "LONG"},
    "LINK_LONG": {"rsi": 30, "ema": 50, "dir": "LONG"},
    "AVAX_LONG": {"rsi": 30, "ema": 21, "dir": "LONG"},
    # SHORT
    "BTC_SHORT": {"stoch": 75, "dir": "SHORT"},
    "ETH_SHORT": {"stoch": 75, "dir": "SHORT"},
    "SOL_SHORT": {"rsi": 80, "dir": "SHORT"},
    "XRP_SHORT": {"rsi": 80, "dir": "SHORT"},
    "ADA_SHORT": {"stoch": 75, "dir": "SHORT"},
    "LINK_SHORT": {"stoch": 75, "dir": "SHORT"},
    "AVAX_SHORT": {"stoch": 75, "dir": "SHORT"},
    "BNB_SHORT": {"rsi": 70, "dir": "SHORT"},
    "SOL_LONG": {"rsi": 80, "dir": "SHORT"},
}

# SL/TP комбинации для теста
SL_OPTIONS = [0.8, 1.0, 1.2, 1.5]
TP_OPTIONS = [1.5, 2.0, 2.5, 3.0]

SYMBOLS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LINK", "AVAX", "BNB"]


def load_cached_data(symbol: str) -> pd.DataFrame:
    """Загрузить данные из кэша"""
    path = f"data/{symbol}_5m_2025_2025.csv"
    try:
        df = pd.read_csv(path)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna()
    except Exception:
        return pd.DataFrame()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Добавить индикаторы"""
    df = df.copy()

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / (loss + 1e-10)))

    # RSI 21
    gain21 = delta.where(delta > 0, 0).rolling(21).mean()
    loss21 = (-delta.where(delta < 0, 0)).rolling(21).mean()
    df['rsi21'] = 100 - (100 / (1 + gain21 / (loss21 + 1e-10)))

    # EMA
    df['ema21'] = df['close'].ewm(span=21).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    # Stochastic
    low14 = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch'] = ((df['close'] - low14) / (high14 - low14 + 1e-10)) * 100

    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()

    return df


def check_signal(df: pd.DataFrame, idx: int, strategy: dict) -> bool:
    """Проверить сигнал стратегии"""
    try:
        row = df.iloc[idx]

        if strategy["dir"] == "LONG":
            if "rsi" in strategy:
                rsi_val = row['rsi21'] if strategy.get("rsi") == 80 else row['rsi']
                if rsi_val >= strategy["rsi"]:
                    return False
                if "ema" in strategy:
                    ema_col = f"ema{strategy['ema']}"
                    if row['close'] <= row[ema_col]:
                        return False
                return True
            elif "stoch" in strategy:
                if row['stoch'] >= strategy["stoch"]:
                    return False
                if row['macd'] <= row['macd_signal']:
                    return False
                return True

        else:  # SHORT
            if "rsi" in strategy:
                rsi_val = row['rsi21'] if strategy.get("rsi") == 80 else row['rsi']
                return rsi_val >= strategy["rsi"]
            elif "stoch" in strategy:
                return row['stoch'] >= strategy["stoch"]

        return False
    except Exception:
        return False


def backtest_with_sltp(df: pd.DataFrame, strategy: dict, sl_pct: float, tp_pct: float) -> dict:
    """Бэктест с заданными SL/TP"""
    trades = []
    last_trade = 0
    commission = 0.001  # 0.1%

    for i in range(100, len(df) - 50):
        if i - last_trade < 12:  # 1 час минимум (12 свечей по 5 мин)
            continue

        if check_signal(df, i, strategy):
            entry = df.iloc[i]['close']
            direction = strategy["dir"]

            if direction == "LONG":
                sl_price = entry * (1 - sl_pct / 100)
                tp_price = entry * (1 + tp_pct / 100)
            else:
                sl_price = entry * (1 + sl_pct / 100)
                tp_price = entry * (1 - tp_pct / 100)

            # Ищем выход (макс 576 свечей = 48 часов)
            for j in range(i + 1, min(i + 576, len(df))):
                high = df.iloc[j]['high']
                low = df.iloc[j]['low']

                if direction == "LONG":
                    if low <= sl_price:
                        pnl = -sl_pct - (commission * 200)
                        trades.append({"pnl": pnl, "won": False})
                        last_trade = j
                        break
                    elif high >= tp_price:
                        pnl = tp_pct - (commission * 200)
                        trades.append({"pnl": pnl, "won": True})
                        last_trade = j
                        break
                else:  # SHORT
                    if high >= sl_price:
                        pnl = -sl_pct - (commission * 200)
                        trades.append({"pnl": pnl, "won": False})
                        last_trade = j
                        break
                    elif low <= tp_price:
                        pnl = tp_pct - (commission * 200)
                        trades.append({"pnl": pnl, "won": True})
                        last_trade = j
                        break

    if not trades:
        return {"trades": 0, "wr": 0, "pnl": 0}

    wins = sum(1 for t in trades if t["won"])
    total_pnl = sum(t["pnl"] for t in trades)

    return {
        "trades": len(trades),
        "wr": wins / len(trades) * 100,
        "pnl": total_pnl
    }


async def main():
    print("=" * 80)
    print("📊 ОПТИМИЗАЦИЯ SL/TP ДЛЯ 16 СТРАТЕГИЙ")
    print("=" * 80)
    print(f"SL варианты: {SL_OPTIONS}")
    print(f"TP варианты: {TP_OPTIONS}")
    print("=" * 80)

    # Загружаем данные
    data = {}
    for symbol in SYMBOLS:
        df = load_cached_data(symbol)
        if not df.empty:
            data[symbol] = add_indicators(df)
            print(f"✅ {symbol}: {len(df)} свечей")

    # Тест всех комбинаций
    results = []

    for sl in SL_OPTIONS:
        for tp in TP_OPTIONS:
            combo_trades = 0
            combo_wins = 0
            combo_pnl = 0

            for strat_name, strat in STRATEGIES.items():
                symbol = strat_name.split("_")[0]
                if symbol not in data:
                    continue

                result = backtest_with_sltp(data[symbol], strat, sl, tp)
                combo_trades += result["trades"]
                combo_wins += int(result["trades"] * result["wr"] / 100)
                combo_pnl += result["pnl"]

            if combo_trades > 0:
                combo_wr = combo_wins / combo_trades * 100
                results.append({
                    "sl": sl, "tp": tp,
                    "trades": combo_trades,
                    "wr": combo_wr,
                    "pnl": combo_pnl,
                    "rr": tp / sl
                })

    # Сортируем по PnL
    results.sort(key=lambda x: x["pnl"], reverse=True)

    print("\n" + "=" * 80)
    print("📋 РЕЗУЛЬТАТЫ (сортировка по PnL)")
    print("=" * 80)
    print(f"{'SL':>5} | {'TP':>5} | {'R/R':>5} | {'Trades':>7} | {'WR':>6} | {'PnL':>10}")
    print("-" * 80)

    for r in results:
        emoji = "✅" if r["pnl"] > 0 and r["wr"] >= 55 else "⚠️" if r["pnl"] > 0 else "❌"
        print(f"{emoji} {r['sl']:>4}% | {r['tp']:>4}% | {r['rr']:>5.2f} | "
              f"{r['trades']:>7} | {r['wr']:>5.1f}% | {r['pnl']:>+9.1f}%")

    # Лучшая комбинация
    if results and results[0]["pnl"] > 0:
        best = results[0]
        print("\n" + "=" * 80)
        print("🏆 ЛУЧШАЯ КОМБИНАЦИЯ:")
        print("=" * 80)
        print(f"   SL: {best['sl']}%")
        print(f"   TP: {best['tp']}%")
        print(f"   Risk/Reward: {best['rr']:.2f}")
        print(f"   Win Rate: {best['wr']:.1f}%")
        print(f"   Сделок: {best['trades']}")
        print(f"   PnL: {best['pnl']:+.1f}%")
        print(f"\n   📅 PnL в месяц: ~{best['pnl']:.1f}%")
        print(f"   📅 PnL в год: ~{best['pnl'] * 12:.0f}%")
    else:
        print("\n❌ Нет прибыльных комбинаций. Нужны новые стратегии!")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
