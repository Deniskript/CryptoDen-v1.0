"""
Бэктест КОМБО SHORT стратегий — 2025 год
Цель: найти лучшие комбинации для максимального Win Rate
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass, field
from pathlib import Path

import sys
sys.path.insert(0, '/root/crypto-bot')


@dataclass
class Trade:
    """Сделка"""
    symbol: str
    combo: str
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_time: datetime = None
    exit_price: float = None
    pnl_percent: float = 0
    result: str = ""
    signals_count: int = 1


@dataclass 
class ComboResult:
    """Результат комбо"""
    name: str
    description: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0
    total_pnl: float = 0
    avg_pnl_per_trade: float = 0
    max_consecutive_losses: int = 0
    trades_per_day: float = 0
    trades: List[Trade] = field(default_factory=list)


class ComboBacktest:
    """Бэктест комбинаций стратегий"""
    
    def __init__(self):
        self.results: Dict[str, ComboResult] = {}
        self.data_dir = Path("/root/crypto-bot/data")
        self.symbols = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LINK", "AVAX"]
        
        # Определяем комбинации для тестирования
        self.combos = {
            # === STOCHASTIC КОМБО ===
            "STOCH_EMA": {
                "name": "Stoch>80 + EMA9<EMA21",
                "description": "Stoch > 80 AND EMA9 < EMA21",
                "conditions": ["stoch_overbought", "ema_bearish"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "STOCH_RSI": {
                "name": "Stoch>80 + RSI>65",
                "description": "Stoch > 80 AND RSI > 65",
                "conditions": ["stoch_overbought", "rsi_high"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "STOCH_VOLUME": {
                "name": "Stoch>80 + Volume 1.5x",
                "description": "Stoch > 80 AND Volume > 1.5x avg",
                "conditions": ["stoch_overbought", "high_volume"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "STOCH_MACD": {
                "name": "Stoch>80 + MACD<Signal",
                "description": "Stoch > 80 AND MACD < Signal",
                "conditions": ["stoch_overbought", "macd_bearish"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "STOCH_BB": {
                "name": "Stoch>80 + Price>BB",
                "description": "Stoch > 80 AND Price > BB Upper",
                "conditions": ["stoch_overbought", "price_above_bb"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            
            # === ТРОЙНЫЕ КОМБО ===
            "STOCH_EMA_RSI": {
                "name": "Stoch + EMA + RSI",
                "description": "Stoch > 80 AND EMA9 < EMA21 AND RSI > 60",
                "conditions": ["stoch_overbought", "ema_bearish", "rsi_above_60"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "STOCH_EMA_MACD": {
                "name": "Stoch + EMA + MACD",
                "description": "Stoch > 80 AND EMA bearish AND MACD bearish",
                "conditions": ["stoch_overbought", "ema_bearish", "macd_bearish"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "STOCH_RSI_VOL": {
                "name": "Stoch + RSI + Volume",
                "description": "Stoch > 80 AND RSI > 65 AND High Volume",
                "conditions": ["stoch_overbought", "rsi_high", "high_volume"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            
            # === EMA КОМБО ===
            "EMA_MACD": {
                "name": "EMA Cross + MACD",
                "description": "EMA9 < EMA21 AND MACD < Signal",
                "conditions": ["ema_bearish", "macd_bearish"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "EMA_RSI": {
                "name": "EMA Cross + RSI>60",
                "description": "EMA9 < EMA21 AND RSI > 60",
                "conditions": ["ema_bearish", "rsi_above_60"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            
            # === RSI КОМБО ===
            "RSI_BB": {
                "name": "RSI>70 + Price>BB",
                "description": "RSI > 70 AND Price > BB Upper",
                "conditions": ["rsi_overbought", "price_above_bb"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "RSI_MACD": {
                "name": "RSI>70 + MACD<Signal",
                "description": "RSI > 70 AND MACD < Signal",
                "conditions": ["rsi_overbought", "macd_bearish"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            
            # === ПОЛНОЕ ПОДТВЕРЖДЕНИЕ ===
            "FULL_4": {
                "name": "4 индикатора",
                "description": "Stoch + EMA + RSI + MACD",
                "conditions": ["stoch_overbought", "ema_bearish", "rsi_above_60", "macd_bearish"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "FULL_5": {
                "name": "5 индикаторов",
                "description": "Stoch + EMA + RSI + MACD + Volume",
                "conditions": ["stoch_overbought", "ema_bearish", "rsi_above_60", "macd_bearish", "high_volume"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            
            # === РАЗВОРОТНЫЕ ===
            "STOCH_REVERSAL": {
                "name": "Stoch Reversal",
                "description": "Stoch > 80 AND Stoch падает AND Price < EMA50",
                "conditions": ["stoch_overbought", "stoch_falling", "below_ema50"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
            "RSI_REVERSAL": {
                "name": "RSI Reversal",
                "description": "RSI > 70 AND RSI падает",
                "conditions": ["rsi_overbought", "rsi_falling"],
                "sl_percent": 0.5,
                "tp_percent": 0.3,
            },
        }
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Рассчитать все индикаторы"""
        
        df = df.copy()
        close = df['close'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        volume = df['volume'].astype(float)
        
        # RSI (14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 0.0001)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi_prev'] = df['rsi'].shift(1)
        
        # Stochastic (14)
        low_14 = low.rolling(14).min()
        high_14 = high.rolling(14).max()
        df['stoch_k'] = 100 * (close - low_14) / (high_14 - low_14 + 0.0001)
        df['stoch_k_prev'] = df['stoch_k'].shift(1)
        
        # EMA (9, 21, 50)
        df['ema_9'] = close.ewm(span=9).mean()
        df['ema_21'] = close.ewm(span=21).mean()
        df['ema_50'] = close.ewm(span=50).mean()
        
        # MACD
        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        
        # Bollinger Bands (20, 2)
        df['bb_middle'] = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        
        # Volume
        df['volume_sma'] = volume.rolling(20).mean()
        
        return df
    
    def _check_condition(self, row: pd.Series, prev_row: pd.Series, condition: str) -> bool:
        """Проверить одно условие"""
        
        try:
            if condition == "stoch_overbought":
                return row['stoch_k'] > 80
            
            elif condition == "stoch_falling":
                return row['stoch_k'] < prev_row['stoch_k']
            
            elif condition == "rsi_high":
                return row['rsi'] > 65
            
            elif condition == "rsi_above_60":
                return row['rsi'] > 60
            
            elif condition == "rsi_overbought":
                return row['rsi'] > 70
            
            elif condition == "rsi_falling":
                return row['rsi'] < prev_row['rsi']
            
            elif condition == "ema_bearish":
                return row['ema_9'] < row['ema_21']
            
            elif condition == "below_ema50":
                return row['close'] < row['ema_50']
            
            elif condition == "macd_bearish":
                return row['macd'] < row['macd_signal']
            
            elif condition == "high_volume":
                return row['volume'] > row['volume_sma'] * 1.5
            
            elif condition == "price_above_bb":
                return row['close'] > row['bb_upper']
            
        except Exception:
            return False
        
        return False
    
    def _check_combo(self, row: pd.Series, prev_row: pd.Series, combo: dict) -> bool:
        """Проверить все условия комбо"""
        
        conditions = combo.get('conditions', [])
        
        # ВСЕ условия должны быть выполнены
        for condition in conditions:
            if not self._check_condition(row, prev_row, condition):
                return False
        
        return True
    
    def _simulate_trade(self, df: pd.DataFrame, entry_idx: int, combo: dict, combo_name: str, symbol: str) -> Trade:
        """Симуляция сделки"""
        
        entry_row = df.iloc[entry_idx]
        entry_price = float(entry_row['close'])
        entry_time = entry_row['timestamp']
        
        sl_percent = combo['sl_percent']
        tp_percent = combo['tp_percent']
        
        # SHORT: SL выше, TP ниже
        stop_loss = entry_price * (1 + sl_percent / 100)
        take_profit = entry_price * (1 - tp_percent / 100)
        
        trade = Trade(
            symbol=symbol,
            combo=combo_name,
            entry_time=entry_time,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signals_count=len(combo.get('conditions', []))
        )
        
        # Симуляция: проходим по свечам (макс 50 свечей = ~4 часа на 5m)
        for i in range(entry_idx + 1, min(entry_idx + 50, len(df))):
            row = df.iloc[i]
            high_price = float(row['high'])
            low_price = float(row['low'])
            
            exit_time = row['timestamp']
            
            # SL сработал (цена пошла вверх)
            if high_price >= stop_loss:
                trade.exit_time = exit_time
                trade.exit_price = stop_loss
                trade.pnl_percent = -sl_percent
                trade.result = "LOSS"
                return trade
            
            # TP сработал (цена пошла вниз)
            if low_price <= take_profit:
                trade.exit_time = exit_time
                trade.exit_price = take_profit
                trade.pnl_percent = tp_percent
                trade.result = "WIN"
                return trade
        
        # Таймаут — закрываем по текущей
        last_row = df.iloc[min(entry_idx + 50, len(df) - 1)]
        trade.exit_price = float(last_row['close'])
        trade.pnl_percent = (entry_price - trade.exit_price) / entry_price * 100
        trade.result = "WIN" if trade.pnl_percent > 0.05 else "LOSS" if trade.pnl_percent < -0.05 else "BREAKEVEN"
        
        return trade
    
    def _load_data(self, symbol: str) -> pd.DataFrame:
        """Загрузить данные 2025 из CSV"""
        
        csv_path = self.data_dir / f"{symbol}_5m_2025_2025.csv"
        
        if not csv_path.exists():
            print(f"   ⚠️ Файл не найден: {csv_path}")
            return pd.DataFrame()
        
        try:
            df = pd.read_csv(csv_path)
            print(f"   ✅ {symbol}: {len(df):,} свечей")
            return df
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            return pd.DataFrame()
    
    def run(self):
        """Запуск бэктеста"""
        
        print("\n" + "="*80)
        print("📊 БЭКТЕСТ КОМБО SHORT СТРАТЕГИЙ — 2025")
        print("="*80)
        print(f"🎯 Тестируем {len(self.combos)} комбинаций на {len(self.symbols)} монетах")
        print("="*80)
        
        # Инициализация результатов
        for combo_id, combo in self.combos.items():
            self.results[combo_id] = ComboResult(
                name=combo['name'],
                description=combo['description']
            )
        
        total_days = 365  # 2025 год
        
        for symbol in self.symbols:
            print(f"\n🪙 {symbol}")
            print("-"*60)
            
            df = self._load_data(symbol)
            
            if df.empty or len(df) < 100:
                print("   ⚠️ Недостаточно данных")
                continue
            
            # Индикаторы
            df = self._calculate_indicators(df)
            
            # Тестируем каждую комбо
            for combo_id, combo in self.combos.items():
                trades_count = 0
                last_entry = -12  # Минимум 12 свечей между входами (1 час на 5m)
                
                for i in range(60, len(df) - 1):
                    if i - last_entry < 12:
                        continue
                    
                    row = df.iloc[i]
                    prev_row = df.iloc[i - 1]
                    
                    if self._check_combo(row, prev_row, combo):
                        trade = self._simulate_trade(df, i, combo, combo_id, symbol)
                        self.results[combo_id].trades.append(trade)
                        trades_count += 1
                        last_entry = i
                
                # Статистика по монете
                result = self.results[combo_id]
                result.total_trades += trades_count
                
                if trades_count > 0:
                    recent_trades = result.trades[-trades_count:]
                    wins = sum(1 for t in recent_trades if t.result == "WIN")
                    pnl = sum(t.pnl_percent for t in recent_trades)
                    wr = wins / trades_count * 100
                    print(f"   {combo['name']:<28} | {trades_count:>5} | WR: {wr:>5.1f}% | PnL: {pnl:>+8.2f}%")
        
        # Финальная статистика
        self._calculate_final_stats(total_days)
        self._print_results()
    
    def _calculate_final_stats(self, total_days: int):
        """Рассчитать финальную статистику"""
        
        for combo_id, result in self.results.items():
            trades = result.trades
            
            if not trades:
                continue
            
            result.wins = sum(1 for t in trades if t.result == "WIN")
            result.losses = sum(1 for t in trades if t.result == "LOSS")
            result.win_rate = (result.wins / len(trades) * 100) if trades else 0
            result.total_pnl = sum(t.pnl_percent for t in trades)
            result.avg_pnl_per_trade = result.total_pnl / len(trades) if trades else 0
            result.trades_per_day = len(trades) / max(total_days, 1)
            
            # Max consecutive losses
            max_losses = 0
            current_losses = 0
            for t in trades:
                if t.result == "LOSS":
                    current_losses += 1
                    max_losses = max(max_losses, current_losses)
                else:
                    current_losses = 0
            result.max_consecutive_losses = max_losses
    
    def _print_results(self):
        """Вывод результатов"""
        
        print("\n" + "="*80)
        print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ КОМБО СТРАТЕГИЙ")
        print("="*80)
        
        # Сортируем по Win Rate
        sorted_results = sorted(
            self.results.items(),
            key=lambda x: (x[1].win_rate, x[1].total_pnl),
            reverse=True
        )
        
        print(f"\n{'#':<3} {'Комбо':<30} {'Сделок':>8} {'WR%':>8} {'PnL%':>10} {'В день':>8} {'MaxLoss':>8}")
        print("-"*85)
        
        for i, (combo_id, result) in enumerate(sorted_results, 1):
            if result.total_trades == 0:
                continue
                
            star = "⭐" if result.win_rate >= 65 else "  "
            
            print(f"{star}{i:<2} {result.name:<30} {result.total_trades:>8} {result.win_rate:>7.1f}% "
                  f"{result.total_pnl:>+9.2f}% {result.trades_per_day:>7.1f} {result.max_consecutive_losses:>8}")
        
        # Лучшие комбо
        print("\n" + "="*80)
        print("🏆 ЛУЧШИЕ КОМБО (WR >= 65%):")
        print("="*80)
        
        best = [(k, v) for k, v in sorted_results if v.win_rate >= 65 and v.total_trades >= 100]
        
        if best:
            for combo_id, result in best[:5]:
                combo = self.combos[combo_id]
                print(f"\n✅ {result.name}")
                print(f"   📋 Условия: {combo['description']}")
                print(f"   📊 Win Rate: {result.win_rate:.1f}%")
                print(f"   💰 PnL: {result.total_pnl:+.2f}%")
                print(f"   📈 Сделок: {result.total_trades} ({result.trades_per_day:.1f}/день)")
                print(f"   🛡️ Max убыточная серия: {result.max_consecutive_losses}")
        else:
            print("\n⚠️ Нет комбо с WR >= 65% и >= 100 сделок")
            
            print("\n💡 Лучшие по WR (любое кол-во сделок):")
            for combo_id, result in sorted_results[:5]:
                if result.total_trades > 0:
                    print(f"   • {result.name}: WR={result.win_rate:.1f}%, Trades={result.total_trades}, PnL={result.total_pnl:+.2f}%")
        
        # Сохраняем результаты
        self._save_results(sorted_results)
    
    def _save_results(self, sorted_results):
        """Сохранить результаты в JSON"""
        import json
        
        results_data = {}
        for combo_id, result in sorted_results:
            if result.total_trades == 0:
                continue
                
            results_data[combo_id] = {
                "name": result.name,
                "description": self.combos[combo_id]['description'],
                "conditions": self.combos[combo_id]['conditions'],
                "total_trades": result.total_trades,
                "wins": result.wins,
                "losses": result.losses,
                "win_rate": round(result.win_rate, 2),
                "total_pnl": round(result.total_pnl, 2),
                "trades_per_day": round(result.trades_per_day, 2),
                "max_consecutive_losses": result.max_consecutive_losses,
            }
        
        output_path = self.data_dir / "combo_short_results_2025.json"
        with open(output_path, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        print(f"\n💾 Результаты сохранены: {output_path}")


def main():
    backtest = ComboBacktest()
    backtest.run()


if __name__ == "__main__":
    main()
