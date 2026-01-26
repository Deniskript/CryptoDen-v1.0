"""
Backtest Engine — Движок бэктестинга
Тестирование стратегий на исторических данных
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

from app.core.logger import logger
from app.backtesting.strategies import strategy_library, Strategy


@dataclass
class Trade:
    """Результат сделки"""
    entry_idx: int
    entry_time: datetime
    entry_price: float
    direction: str
    exit_idx: int = 0
    exit_time: Optional[datetime] = None
    exit_price: float = 0.0
    pnl_percent: float = 0.0
    exit_reason: str = ""  # TP, SL, TIMEOUT


@dataclass
class BacktestResult:
    """Результат бэктеста одной стратегии"""
    strategy_id: str
    strategy_name: str
    direction: str
    symbol: str
    
    # Статистика
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    trades_per_day: float = 0.0
    
    # Детали
    trades: List[Trade] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "strategy": self.strategy_name,
            "strategy_id": self.strategy_id,
            "direction": self.direction,
            "symbol": self.symbol,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 2),
            "total_pnl": round(self.total_pnl, 2),
            "avg_pnl": round(self.avg_pnl, 4),
            "profit_factor": round(self.profit_factor, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "trades_per_day": round(self.trades_per_day, 2)
        }


class BacktestEngine:
    """Движок бэктестинга"""
    
    def __init__(
        self,
        tp_percent: float = 0.5,
        sl_percent: float = 0.5,
        max_hold_candles: int = 100,
        min_trades: int = 30
    ):
        """
        Args:
            tp_percent: Take Profit в процентах
            sl_percent: Stop Loss в процентах
            max_hold_candles: Максимум свечей в позиции
            min_trades: Минимум сделок для валидного результата
        """
        self.tp_percent = tp_percent
        self.sl_percent = sl_percent
        self.max_hold_candles = max_hold_candles
        self.min_trades = min_trades
    
    def test_strategy(
        self,
        df: pd.DataFrame,
        strategy: Strategy,
        symbol: str = "UNKNOWN"
    ) -> BacktestResult:
        """
        Тестировать одну стратегию
        
        Args:
            df: DataFrame с OHLCV данными
            strategy: Стратегия для тестирования
            symbol: Символ для отчёта
        
        Returns:
            BacktestResult
        """
        if len(df) < 100:
            return BacktestResult(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                direction=strategy.direction,
                symbol=symbol
            )
        
        # Получаем сигналы
        try:
            signals = strategy.condition(df)
        except Exception as e:
            logger.debug(f"Strategy {strategy.id} error: {e}")
            return BacktestResult(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                direction=strategy.direction,
                symbol=symbol
            )
        
        # Убеждаемся что signals - это Series
        if not isinstance(signals, pd.Series):
            signals = pd.Series(signals, index=df.index)
        
        # Заполняем NaN
        signals = signals.fillna(False).astype(bool)
        
        # Симулируем сделки
        trades = self._simulate_trades(df, signals, strategy.direction)
        
        # Рассчитываем статистику
        result = self._calculate_stats(trades, strategy, symbol, df)
        
        return result
    
    def _simulate_trades(
        self,
        df: pd.DataFrame,
        signals: pd.Series,
        direction: str
    ) -> List[Trade]:
        """Симуляция сделок"""
        trades = []
        in_position = False
        entry_idx = 0
        entry_price = 0.0
        
        # Пропускаем первые 50 свечей для прогрева индикаторов
        start_idx = 50
        
        for i in range(start_idx, len(df)):
            if not in_position:
                # Ищем сигнал входа
                if signals.iloc[i]:
                    in_position = True
                    entry_idx = i
                    entry_price = df['close'].iloc[i]
            else:
                # Проверяем выход
                current_high = df['high'].iloc[i]
                current_low = df['low'].iloc[i]
                current_close = df['close'].iloc[i]
                
                exit_reason = None
                exit_price = current_close
                
                if direction == "LONG":
                    # Take Profit
                    tp_price = entry_price * (1 + self.tp_percent / 100)
                    if current_high >= tp_price:
                        exit_reason = "TP"
                        exit_price = tp_price
                    
                    # Stop Loss
                    sl_price = entry_price * (1 - self.sl_percent / 100)
                    if current_low <= sl_price:
                        exit_reason = "SL"
                        exit_price = sl_price
                
                else:  # SHORT
                    # Take Profit
                    tp_price = entry_price * (1 - self.tp_percent / 100)
                    if current_low <= tp_price:
                        exit_reason = "TP"
                        exit_price = tp_price
                    
                    # Stop Loss
                    sl_price = entry_price * (1 + self.sl_percent / 100)
                    if current_high >= sl_price:
                        exit_reason = "SL"
                        exit_price = sl_price
                
                # Таймаут
                if not exit_reason and (i - entry_idx) >= self.max_hold_candles:
                    exit_reason = "TIMEOUT"
                    exit_price = current_close
                
                if exit_reason:
                    # Рассчитываем PnL
                    if direction == "LONG":
                        pnl = (exit_price - entry_price) / entry_price * 100
                    else:
                        pnl = (entry_price - exit_price) / entry_price * 100
                    
                    trades.append(Trade(
                        entry_idx=entry_idx,
                        entry_time=df['timestamp'].iloc[entry_idx],
                        entry_price=entry_price,
                        direction=direction,
                        exit_idx=i,
                        exit_time=df['timestamp'].iloc[i],
                        exit_price=exit_price,
                        pnl_percent=pnl,
                        exit_reason=exit_reason
                    ))
                    
                    in_position = False
        
        return trades
    
    def _calculate_stats(
        self,
        trades: List[Trade],
        strategy: Strategy,
        symbol: str,
        df: pd.DataFrame
    ) -> BacktestResult:
        """Рассчитать статистику"""
        
        result = BacktestResult(
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            direction=strategy.direction,
            symbol=symbol,
            trades=trades
        )
        
        if not trades:
            return result
        
        result.total_trades = len(trades)
        
        # Wins/Losses
        wins = [t for t in trades if t.pnl_percent > 0]
        losses = [t for t in trades if t.pnl_percent <= 0]
        
        result.wins = len(wins)
        result.losses = len(losses)
        result.win_rate = len(wins) / len(trades) * 100 if trades else 0
        
        # PnL
        result.total_pnl = sum(t.pnl_percent for t in trades)
        result.avg_pnl = result.total_pnl / len(trades) if trades else 0
        
        # Profit Factor
        total_profit = sum(t.pnl_percent for t in wins) if wins else 0
        total_loss = abs(sum(t.pnl_percent for t in losses)) if losses else 0
        result.profit_factor = total_profit / total_loss if total_loss > 0 else total_profit
        
        # Max Drawdown
        cumulative = 0
        max_cumulative = 0
        max_dd = 0
        
        for trade in trades:
            cumulative += trade.pnl_percent
            max_cumulative = max(max_cumulative, cumulative)
            dd = max_cumulative - cumulative
            max_dd = max(max_dd, dd)
        
        result.max_drawdown = max_dd
        
        # Trades per day
        if len(df) > 0:
            total_days = (df['timestamp'].iloc[-1] - df['timestamp'].iloc[0]).days or 1
            result.trades_per_day = len(trades) / total_days
        
        return result
    
    async def test_all_strategies(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        categories: List[str] = None,
        direction: str = None
    ) -> List[Dict]:
        """
        Тестировать все стратегии
        
        Args:
            df: DataFrame с OHLCV данными
            symbol: Символ для отчёта
            categories: Фильтр по категориям
            direction: Фильтр по направлению
        
        Returns:
            Список результатов (dict)
        """
        results = []
        strategies = strategy_library.get_all_strategies()
        
        # Фильтруем
        if categories:
            strategies = {k: v for k, v in strategies.items() if v.category in categories}
        if direction:
            strategies = {k: v for k, v in strategies.items() if v.direction == direction}
        
        total = len(strategies)
        logger.info(f"Testing {total} strategies on {symbol}...")
        
        for idx, (sid, strategy) in enumerate(strategies.items()):
            if (idx + 1) % 20 == 0:
                logger.info(f"  Progress: {idx + 1}/{total}")
            
            result = self.test_strategy(df, strategy, symbol)
            
            # Фильтруем по минимуму сделок
            if result.total_trades >= self.min_trades:
                results.append(result.to_dict())
        
        # Сортируем по win rate
        results.sort(key=lambda x: x['win_rate'], reverse=True)
        
        return results
    
    def find_best_strategies(
        self,
        df: pd.DataFrame,
        symbol: str,
        min_win_rate: float = 55.0,
        min_trades: int = 50,
        top_n: int = 10
    ) -> List[Dict]:
        """
        Найти лучшие стратегии
        
        Returns:
            Топ-N стратегий с WR >= min_win_rate
        """
        import asyncio
        
        # Запускаем тест
        all_results = asyncio.get_event_loop().run_until_complete(
            self.test_all_strategies(df, symbol)
        )
        
        # Фильтруем
        good_results = [
            r for r in all_results
            if r['win_rate'] >= min_win_rate and r['total_trades'] >= min_trades
        ]
        
        # Сортируем по комбинации win_rate и profit_factor
        good_results.sort(
            key=lambda x: x['win_rate'] * 0.7 + x['profit_factor'] * 10,
            reverse=True
        )
        
        return good_results[:top_n]
