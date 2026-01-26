"""
Backtesting Module - Бэктестинг и оптимизация
=============================================

Компоненты:
- data_loader: Загрузка исторических данных (Bybit API)
- backtest_engine: Движок бэктестинга
- optimizer: Оптимизатор 140+ стратегий
- strategies: Определения всех стратегий
- reports: Генерация отчётов

Использование:
    from app.backtesting import BacktestEngine, Optimizer
    
    engine = BacktestEngine()
    results = await engine.run("BTC", strategy="RSI_OVERBOUGHT")
"""

from app.backtesting.backtest_engine import BacktestEngine
from app.backtesting.optimizer import Optimizer

__all__ = ["BacktestEngine", "Optimizer"]
