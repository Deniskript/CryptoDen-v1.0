"""
Бэктест SHORT стратегий — 2025 год
Цель: найти лучшие SHORT стратегии без потери Win Rate
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

import sys
sys.path.insert(0, '/root/crypto-bot')


@dataclass
class BacktestTrade:
    """Сделка бэктеста"""
    symbol: str
    direction: str
    strategy: str
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_time: datetime = None
    exit_price: float = None
    pnl_percent: float = 0
    result: str = ""  # WIN, LOSS, BREAKEVEN


@dataclass
class StrategyResult:
    """Результат стратегии"""
    name: str
    direction: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    win_rate: float = 0
    total_pnl: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    profit_factor: float = 0
    max_drawdown: float = 0
    best_month: str = ""
    worst_month: str = ""
    trades: List[BacktestTrade] = field(default_factory=list)


class ShortStrategyBacktest:
    """Бэктест SHORT стратегий"""
    
    def __init__(self):
        self.results: Dict[str, StrategyResult] = {}
        self.data_dir = Path("/root/crypto-bot/data")
        
        # SHORT стратегии для тестирования
        self.strategies = {
            "RSI_OVERBOUGHT_70": {
                "name": "RSI > 70 Short",
                "params": {"rsi_period": 14, "rsi_threshold": 70},
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "RSI_OVERBOUGHT_75": {
                "name": "RSI > 75 Short",
                "params": {"rsi_period": 14, "rsi_threshold": 75},
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "RSI_OVERBOUGHT_80": {
                "name": "RSI > 80 Short",
                "params": {"rsi_period": 14, "rsi_threshold": 80},
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "EMA_CROSS_SHORT": {
                "name": "EMA9 < EMA21 Short",
                "params": {"ema_fast": 9, "ema_slow": 21, "ema_trend": 50},
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "MACD_SHORT": {
                "name": "MACD Bearish Cross",
                "params": {"fast": 12, "slow": 26, "signal": 9},
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "STOCH_OVERBOUGHT": {
                "name": "Stoch > 80 Short",
                "params": {"period": 14, "threshold": 80},
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "BOLLINGER_UPPER": {
                "name": "Price > BB Upper",
                "params": {"period": 20, "std": 2},
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "RSI_EMA_SHORT": {
                "name": "RSI>70 + Price<EMA21",
                "params": {},
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
        }
        
        self.symbols = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LINK", "AVAX"]
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Рассчитать все индикаторы"""
        
        df = df.copy()
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        volume = df['volume'].astype(float)
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 0.0001)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi_prev'] = df['rsi'].shift(1)
        
        # EMA
        df['ema_9'] = close.ewm(span=9).mean()
        df['ema_21'] = close.ewm(span=21).mean()
        df['ema_50'] = close.ewm(span=50).mean()
        df['ema_9_prev'] = df['ema_9'].shift(1)
        df['ema_21_prev'] = df['ema_21'].shift(1)
        
        # MACD
        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_prev'] = df['macd'].shift(1)
        df['macd_signal_prev'] = df['macd_signal'].shift(1)
        
        # Stochastic
        low_min = low.rolling(14).min()
        high_max = high.rolling(14).max()
        df['stoch_k'] = 100 * (close - low_min) / (high_max - low_min + 0.0001)
        df['stoch_k_prev'] = df['stoch_k'].shift(1)
        
        # Bollinger Bands
        df['bb_mid'] = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * bb_std
        df['bb_lower'] = df['bb_mid'] - 2 * bb_std
        
        # Volume
        df['volume_sma'] = volume.rolling(20).mean()
        
        # Price change
        df['price_change'] = (close - close.shift(1)) / close.shift(1) * 100
        
        return df
    
    def _check_short_signal(self, row: pd.Series, prev_row: pd.Series, strategy_id: str) -> bool:
        """Проверить сигнал SHORT"""
        
        try:
            if strategy_id == "RSI_OVERBOUGHT_70":
                # RSI > 70 и начал падать
                return row['rsi'] > 70 and row['rsi'] < prev_row['rsi']
            
            elif strategy_id == "RSI_OVERBOUGHT_75":
                # RSI > 75 и начал падать
                return row['rsi'] > 75 and row['rsi'] < prev_row['rsi']
            
            elif strategy_id == "RSI_OVERBOUGHT_80":
                # RSI > 80 и начал падать
                return row['rsi'] > 80 and row['rsi'] < prev_row['rsi']
            
            elif strategy_id == "EMA_CROSS_SHORT":
                # EMA9 пересекает EMA21 сверху вниз, цена < EMA50
                cross = prev_row['ema_9'] > prev_row['ema_21'] and row['ema_9'] < row['ema_21']
                below_trend = row['close'] < row['ema_50']
                return cross and below_trend
            
            elif strategy_id == "MACD_SHORT":
                # MACD пересекает Signal сверху вниз
                cross = prev_row['macd'] > prev_row['macd_signal'] and row['macd'] < row['macd_signal']
                return cross
            
            elif strategy_id == "STOCH_OVERBOUGHT":
                # Stochastic > 80 и начал падать
                return row['stoch_k'] > 80 and row['stoch_k'] < prev_row['stoch_k']
            
            elif strategy_id == "BOLLINGER_UPPER":
                # Цена пробила верхнюю полосу и начала падать
                above_upper = prev_row['close'] > prev_row['bb_upper']
                returning = row['close'] < row['bb_upper']
                return above_upper and returning
            
            elif strategy_id == "RSI_EMA_SHORT":
                # Комбо: RSI > 70 + Price < EMA21
                rsi_high = row['rsi'] > 70
                below_ema = row['close'] < row['ema_21']
                return rsi_high and below_ema
            
        except Exception:
            return False
        
        return False
    
    def _simulate_trade(self, df: pd.DataFrame, entry_idx: int, strategy: dict, symbol: str) -> BacktestTrade:
        """Симуляция сделки"""
        
        entry_row = df.iloc[entry_idx]
        entry_price = float(entry_row['close'])
        entry_time = entry_row['timestamp']
        
        sl_percent = strategy['sl_percent']
        tp_percent = strategy['tp_percent']
        
        # SHORT: SL выше, TP ниже
        stop_loss = entry_price * (1 + sl_percent / 100)
        take_profit = entry_price * (1 - tp_percent / 100)
        
        trade = BacktestTrade(
            symbol=symbol,
            direction="SHORT",
            strategy=strategy['name'],
            entry_time=entry_time,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        
        # Проходим по свечам после входа (максимум 50 свечей = ~4 часа на 5m)
        for i in range(entry_idx + 1, min(entry_idx + 50, len(df))):
            row = df.iloc[i]
            high = float(row['high'])
            low = float(row['low'])
            
            exit_time = row['timestamp']
            
            # Проверяем SL (цена пошла вверх)
            if high >= stop_loss:
                trade.exit_time = exit_time
                trade.exit_price = stop_loss
                trade.pnl_percent = -sl_percent
                trade.result = "LOSS"
                return trade
            
            # Проверяем TP (цена пошла вниз)
            if low <= take_profit:
                trade.exit_time = exit_time
                trade.exit_price = take_profit
                trade.pnl_percent = tp_percent
                trade.result = "WIN"
                return trade
        
        # Если не сработал ни SL ни TP — закрываем по текущей
        last_row = df.iloc[min(entry_idx + 50, len(df) - 1)]
        trade.exit_time = last_row['timestamp']
        trade.exit_price = float(last_row['close'])
        trade.pnl_percent = (entry_price - trade.exit_price) / entry_price * 100
        trade.result = "WIN" if trade.pnl_percent > 0 else "LOSS" if trade.pnl_percent < 0 else "BREAKEVEN"
        
        return trade
    
    def _load_data_2025(self, symbol: str) -> pd.DataFrame:
        """Загрузить данные за 2025 год из CSV"""
        
        csv_path = self.data_dir / f"{symbol}_5m_2025_2025.csv"
        
        if not csv_path.exists():
            print(f"   ⚠️ Файл не найден: {csv_path}")
            return pd.DataFrame()
        
        try:
            df = pd.read_csv(csv_path)
            print(f"   ✅ {symbol}: {len(df):,} свечей (5m)")
            return df
        except Exception as e:
            print(f"   ❌ Ошибка загрузки {symbol}: {e}")
            return pd.DataFrame()
    
    def run_backtest(self):
        """Запуск бэктеста"""
        
        print("\n" + "="*70)
        print("📊 БЭКТЕСТ SHORT СТРАТЕГИЙ — 2025")
        print("="*70)
        
        for strategy_id, strategy in self.strategies.items():
            self.results[strategy_id] = StrategyResult(
                name=strategy['name'],
                direction="SHORT"
            )
        
        for symbol in self.symbols:
            print(f"\n🪙 {symbol}")
            print("-"*50)
            
            # Загружаем данные
            df = self._load_data_2025(symbol)
            
            if df.empty or len(df) < 100:
                print(f"   ⚠️ Недостаточно данных")
                continue
            
            # Рассчитываем индикаторы
            df = self._calculate_indicators(df)
            
            # Тестируем каждую стратегию
            for strategy_id, strategy in self.strategies.items():
                trades = []
                last_trade_idx = -20  # Минимум 20 свечей между сделками (~1.5 часа)
                
                for i in range(51, len(df) - 1):
                    # Защита от частых сделок
                    if i - last_trade_idx < 20:
                        continue
                    
                    row = df.iloc[i]
                    prev_row = df.iloc[i - 1]
                    
                    # Проверяем сигнал
                    if self._check_short_signal(row, prev_row, strategy_id):
                        trade = self._simulate_trade(df, i, strategy, symbol)
                        trades.append(trade)
                        self.results[strategy_id].trades.append(trade)
                        last_trade_idx = i
                
                # Обновляем статистику
                result = self.results[strategy_id]
                result.total_trades += len(trades)
                result.wins += sum(1 for t in trades if t.result == "WIN")
                result.losses += sum(1 for t in trades if t.result == "LOSS")
                
                wins = len([t for t in trades if t.result == "WIN"])
                total = len(trades)
                
                if total > 0:
                    wr = wins / total * 100
                    pnl = sum(t.pnl_percent for t in trades)
                    print(f"   {strategy['name']:<25}: {total:>4} trades, WR={wr:>5.1f}%, PnL={pnl:>+7.2f}%")
        
        # Итоговая статистика
        self._print_results()
    
    def _print_results(self):
        """Вывод результатов"""
        
        print("\n" + "="*70)
        print("📊 РЕЗУЛЬТАТЫ БЭКТЕСТА SHORT 2025")
        print("="*70)
        
        # Сортируем по Win Rate
        sorted_results = sorted(
            self.results.items(),
            key=lambda x: x[1].wins / max(x[1].total_trades, 1),
            reverse=True
        )
        
        print("\n📈 РЕЙТИНГ СТРАТЕГИЙ:\n")
        print(f"{'Стратегия':<28} {'Сделок':>8} {'Win':>6} {'Loss':>6} {'WR%':>8} {'PnL%':>10}")
        print("-"*75)
        
        best_strategies = []
        
        for strategy_id, result in sorted_results:
            total = result.total_trades
            wins = result.wins
            losses = result.losses
            wr = (wins / total * 100) if total > 0 else 0
            pnl = sum(t.pnl_percent for t in result.trades)
            
            # Отмечаем лучшие (WR > 55% и больше 50 сделок)
            star = "⭐" if wr > 55 and total > 50 else "  "
            
            print(f"{star}{result.name:<26} {total:>8} {wins:>6} {losses:>6} {wr:>7.1f}% {pnl:>+9.2f}%")
            
            if wr > 55 and total > 50:
                best_strategies.append({
                    "id": strategy_id,
                    "name": result.name,
                    "win_rate": wr,
                    "total_pnl": pnl,
                    "trades": total
                })
        
        print("\n" + "="*70)
        print("🏆 ЛУЧШИЕ SHORT СТРАТЕГИИ ДЛЯ ДОБАВЛЕНИЯ:")
        print("="*70)
        
        if best_strategies:
            for s in best_strategies:
                print(f"\n✅ {s['name']}")
                print(f"   Win Rate: {s['win_rate']:.1f}%")
                print(f"   PnL: {s['total_pnl']:+.2f}%")
                print(f"   Сделок: {s['trades']}")
        else:
            print("\n⚠️ Нет стратегий с WR > 55% и > 50 сделок")
            print("\n💡 Стратегии с WR > 50%:")
            for strategy_id, result in sorted_results:
                total = result.total_trades
                if total > 20:
                    wr = (result.wins / total * 100)
                    if wr > 50:
                        pnl = sum(t.pnl_percent for t in result.trades)
                        print(f"   • {result.name}: WR={wr:.1f}%, Trades={total}, PnL={pnl:+.2f}%")
        
        print("\n" + "="*70)
        
        # Сохраняем результаты в файл
        self._save_results()
    
    def _save_results(self):
        """Сохранить результаты в JSON"""
        import json
        
        results_data = {}
        for strategy_id, result in self.results.items():
            total = result.total_trades
            wr = (result.wins / total * 100) if total > 0 else 0
            pnl = sum(t.pnl_percent for t in result.trades)
            
            results_data[strategy_id] = {
                "name": result.name,
                "total_trades": total,
                "wins": result.wins,
                "losses": result.losses,
                "win_rate": round(wr, 2),
                "total_pnl": round(pnl, 2),
            }
        
        output_path = self.data_dir / "short_backtest_results_2025.json"
        with open(output_path, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        print(f"\n💾 Результаты сохранены: {output_path}")


def main():
    backtest = ShortStrategyBacktest()
    backtest.run_backtest()


if __name__ == "__main__":
    main()
