"""
Optimizer - Оптимизатор стратегий
=================================

Перебирает 140+ комбинаций стратегий и параметров
для поиска лучших настроек.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import asdict

from app.core.logger import logger
from app.core.constants import COINS
from app.backtesting.backtest_engine import BacktestEngine, BacktestResult


class Optimizer:
    """Оптимизатор стратегий"""
    
    REPORTS_DIR = Path("/root/crypto-bot/reports")
    
    # Все комбинации для тестирования
    STRATEGY_CONFIGS = [
        # RSI Oversold (LONG)
        {"name": "RSI_OVERSOLD", "params": {"rsi_period": 7, "rsi_level": 30, "ema_period": 21}},
        {"name": "RSI_OVERSOLD", "params": {"rsi_period": 7, "rsi_level": 35, "ema_period": 21}},
        {"name": "RSI_OVERSOLD", "params": {"rsi_period": 7, "rsi_level": 40, "ema_period": 21}},
        {"name": "RSI_OVERSOLD", "params": {"rsi_period": 14, "rsi_level": 30, "ema_period": 50}},
        {"name": "RSI_OVERSOLD", "params": {"rsi_period": 14, "rsi_level": 35, "ema_period": 50}},
        {"name": "RSI_OVERSOLD", "params": {"rsi_period": 21, "rsi_level": 30, "ema_period": 50}},
        
        # RSI Overbought (SHORT)
        {"name": "RSI_OVERBOUGHT", "params": {"rsi_period": 7, "rsi_level": 70}},
        {"name": "RSI_OVERBOUGHT", "params": {"rsi_period": 7, "rsi_level": 75}},
        {"name": "RSI_OVERBOUGHT", "params": {"rsi_period": 14, "rsi_level": 70}},
        {"name": "RSI_OVERBOUGHT", "params": {"rsi_period": 14, "rsi_level": 75}},
        {"name": "RSI_OVERBOUGHT", "params": {"rsi_period": 21, "rsi_level": 75}},
        {"name": "RSI_OVERBOUGHT", "params": {"rsi_period": 21, "rsi_level": 80}},
        
        # Stochastic + MACD (LONG)
        {"name": "STOCH_MACD", "params": {"stoch_period": 9, "stoch_level": 20}},
        {"name": "STOCH_MACD", "params": {"stoch_period": 9, "stoch_level": 25}},
        {"name": "STOCH_MACD", "params": {"stoch_period": 14, "stoch_level": 20}},
        {"name": "STOCH_MACD", "params": {"stoch_period": 14, "stoch_level": 25}},
        {"name": "STOCH_MACD", "params": {"stoch_period": 14, "stoch_level": 30}},
        
        # Double Bottom (LONG)
        {"name": "DOUBLE_BOTTOM", "params": {"lookback": 15}},
        {"name": "DOUBLE_BOTTOM", "params": {"lookback": 20}},
        {"name": "DOUBLE_BOTTOM", "params": {"lookback": 25}},
    ]
    
    # Варианты TP/SL
    TP_SL_VARIANTS = [
        {"tp_percent": 0.3, "sl_percent": 0.5},
        {"tp_percent": 0.5, "sl_percent": 0.5},
        {"tp_percent": 0.5, "sl_percent": 0.8},
        {"tp_percent": 0.8, "sl_percent": 1.0},
    ]
    
    def __init__(self):
        self.engine = BacktestEngine()
        self.REPORTS_DIR.mkdir(exist_ok=True)
    
    async def optimize_coin(
        self,
        symbol: str,
        year: int = 2024,
        min_win_rate: float = 60.0
    ) -> Dict[str, Any]:
        """
        Оптимизировать стратегии для одной монеты
        
        Returns:
            Лучшая стратегия с параметрами
        """
        logger.info(f"🔍 Optimizing {symbol}...")
        
        best_result: BacktestResult = None
        all_results: List[BacktestResult] = []
        
        # Перебираем все комбинации
        for strategy_config in self.STRATEGY_CONFIGS:
            for tp_sl in self.TP_SL_VARIANTS:
                params = {**strategy_config["params"], **tp_sl}
                
                result = await self.engine.run(
                    symbol=symbol,
                    strategy_name=strategy_config["name"],
                    params=params,
                    year=year
                )
                
                if result.total_trades >= 50:  # Минимум 50 сделок
                    all_results.append(result)
                    
                    if result.win_rate >= min_win_rate:
                        if not best_result or result.win_rate > best_result.win_rate:
                            best_result = result
                
                await asyncio.sleep(0.01)  # Небольшая пауза
        
        if best_result:
            logger.info(
                f"🏆 Best for {symbol}: {best_result.strategy_name} "
                f"WR={best_result.win_rate:.1f}%, PnL={best_result.total_pnl:.2f}%"
            )
            return {
                "symbol": symbol,
                "strategy": best_result.strategy_name,
                "direction": best_result.direction,
                "win_rate": best_result.win_rate,
                "total_pnl": best_result.total_pnl,
                "total_trades": best_result.total_trades,
                "profit_factor": best_result.profit_factor,
                "params": best_result.params
            }
        
        logger.warning(f"⚠️ No good strategy for {symbol} (min WR: {min_win_rate}%)")
        return None
    
    async def optimize_all(
        self,
        coins: List[str] = None,
        year: int = 2024,
        min_win_rate: float = 60.0
    ) -> Dict[str, Any]:
        """
        Оптимизировать все монеты
        
        Returns:
            Словарь с лучшими стратегиями для каждой монеты
        """
        coins = coins or COINS
        results = {}
        
        for coin in coins:
            best = await self.optimize_coin(coin, year, min_win_rate)
            if best:
                results[coin] = best
        
        # Сохраняем отчёт
        report = {
            "generated_at": datetime.now().isoformat(),
            "year": year,
            "min_win_rate": min_win_rate,
            "total_coins": len(results),
            "results": results
        }
        
        report_file = self.REPORTS_DIR / f"optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📊 Optimization report saved: {report_file}")
        
        return results


# Глобальный экземпляр
optimizer = Optimizer()
