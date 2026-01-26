"""
Reports - Генерация отчётов
===========================

Создаёт отчёты по результатам бэктестинга.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from app.core.logger import logger
from app.backtesting.backtest_engine import BacktestResult


class ReportGenerator:
    """Генератор отчётов"""
    
    REPORTS_DIR = Path("/root/crypto-bot/reports")
    
    def __init__(self):
        self.REPORTS_DIR.mkdir(exist_ok=True)
    
    def generate_json(self, result: BacktestResult) -> Path:
        """Сохранить результат в JSON"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{result.symbol}_{result.strategy_name}_{timestamp}.json"
        filepath = self.REPORTS_DIR / filename
        
        data = {
            "symbol": result.symbol,
            "strategy": result.strategy_name,
            "direction": result.direction,
            "params": result.params,
            "stats": {
                "total_trades": result.total_trades,
                "wins": result.wins,
                "losses": result.losses,
                "win_rate": result.win_rate,
                "total_pnl": result.total_pnl,
                "profit_factor": result.profit_factor,
                "max_drawdown": result.max_drawdown,
                "trades_per_day": result.trades_per_day
            },
            "trades": [
                {
                    "entry_time": str(t.entry_time),
                    "exit_time": str(t.exit_time),
                    "direction": t.direction.value,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl_percent": t.pnl_percent,
                    "exit_reason": t.exit_reason
                }
                for t in result.trades
            ],
            "generated_at": datetime.now().isoformat()
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"📄 Report saved: {filepath}")
        return filepath
    
    def generate_summary(self, results: Dict[str, BacktestResult]) -> str:
        """Создать текстовый саммари"""
        lines = [
            "=" * 60,
            "BACKTEST SUMMARY",
            "=" * 60,
            ""
        ]
        
        for symbol, result in results.items():
            lines.append(f"📊 {symbol}")
            lines.append(f"   Strategy: {result.strategy_name}")
            lines.append(f"   Direction: {result.direction}")
            lines.append(f"   Win Rate: {result.win_rate:.1f}%")
            lines.append(f"   Total PnL: {result.total_pnl:.2f}%")
            lines.append(f"   Trades: {result.total_trades}")
            lines.append(f"   Profit Factor: {result.profit_factor:.2f}")
            lines.append("")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def load_best_strategies(self) -> Dict[str, Any]:
        """Загрузить последний отчёт оптимизации"""
        reports = list(self.REPORTS_DIR.glob("optimization_*.json"))
        
        if not reports:
            return {}
        
        latest = max(reports, key=lambda p: p.stat().st_mtime)
        
        with open(latest, "r") as f:
            data = json.load(f)
        
        return data.get("results", {})


# Глобальный экземпляр
report_generator = ReportGenerator()
