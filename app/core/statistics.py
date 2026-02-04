"""
📊 Statistics Module — Сбор и анализ статистики торговли

Отслеживает:
- Win Rate по источникам (Brain, Momentum, Listing)
- Средний профит/убыток
- Лучшие/худшие сделки
- Статистику по монетам
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

from app.core.logger import logger


class TradeResult(Enum):
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    OPEN = "open"


@dataclass
class TradeRecord:
    """Запись о сделке"""
    id: str
    symbol: str
    direction: str  # LONG / SHORT
    source: str     # brain / momentum / listing
    
    entry_price: float
    entry_time: datetime
    
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    
    stop_loss: float = 0.0
    take_profit: float = 0.0
    
    pnl_percent: float = 0.0
    pnl_usd: float = 0.0
    
    result: TradeResult = TradeResult.OPEN
    confidence: int = 0
    
    notes: str = ""


@dataclass
class SourceStats:
    """Статистика по источнику сигналов"""
    source: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    
    total_pnl_percent: float = 0.0
    total_pnl_usd: float = 0.0
    
    avg_win_percent: float = 0.0
    avg_loss_percent: float = 0.0
    
    best_trade_percent: float = 0.0
    worst_trade_percent: float = 0.0
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.wins / self.total_trades) * 100
    
    @property
    def profit_factor(self) -> float:
        if self.avg_loss_percent == 0:
            return 0.0
        return abs(self.avg_win_percent / self.avg_loss_percent)


class TradingStatistics:
    """Главный класс статистики"""
    
    STATS_FILE = "/root/crypto-bot/data/trading_statistics.json"
    
    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.source_stats: Dict[str, SourceStats] = {}
        self._load()
        logger.info("📊 Trading Statistics initialized")
    
    def _load(self):
        """Загрузить статистику из файла"""
        try:
            if os.path.exists(self.STATS_FILE):
                with open(self.STATS_FILE, 'r') as f:
                    data = json.load(f)
                
                # Восстановить trades
                for t in data.get('trades', []):
                    t['entry_time'] = datetime.fromisoformat(t['entry_time'])
                    if t.get('exit_time'):
                        t['exit_time'] = datetime.fromisoformat(t['exit_time'])
                    t['result'] = TradeResult(t['result'])
                    self.trades.append(TradeRecord(**t))
                
                logger.info(f"📊 Loaded {len(self.trades)} trade records")
        except Exception as e:
            logger.error(f"Failed to load statistics: {e}")
    
    def _save(self):
        """Сохранить статистику в файл"""
        try:
            os.makedirs(os.path.dirname(self.STATS_FILE), exist_ok=True)
            
            data = {
                'trades': [],
                'last_updated': datetime.utcnow().isoformat()
            }
            
            for t in self.trades:
                record = {
                    'id': t.id,
                    'symbol': t.symbol,
                    'direction': t.direction,
                    'source': t.source,
                    'entry_price': t.entry_price,
                    'entry_time': t.entry_time.isoformat(),
                    'exit_price': t.exit_price,
                    'exit_time': t.exit_time.isoformat() if t.exit_time else None,
                    'stop_loss': t.stop_loss,
                    'take_profit': t.take_profit,
                    'pnl_percent': t.pnl_percent,
                    'pnl_usd': t.pnl_usd,
                    'result': t.result.value,
                    'confidence': t.confidence,
                    'notes': t.notes
                }
                data['trades'].append(record)
            
            with open(self.STATS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save statistics: {e}")
    
    def record_trade_open(
        self,
        trade_id: str,
        symbol: str,
        direction: str,
        source: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        confidence: int = 0
    ) -> TradeRecord:
        """Записать открытие сделки"""
        
        record = TradeRecord(
            id=trade_id,
            symbol=symbol,
            direction=direction,
            source=source,
            entry_price=entry_price,
            entry_time=datetime.utcnow(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            result=TradeResult.OPEN
        )
        
        self.trades.append(record)
        self._save()
        
        logger.info(f"📊 Trade recorded: {direction} {symbol} @ ${entry_price:.4f} (source: {source})")
        
        return record
    
    def record_trade_close(
        self,
        trade_id: str,
        exit_price: float,
        pnl_percent: float,
        pnl_usd: float,
        notes: str = ""
    ):
        """Записать закрытие сделки"""
        
        # Найти сделку
        trade = None
        for t in self.trades:
            if t.id == trade_id:
                trade = t
                break
        
        if not trade:
            logger.warning(f"Trade {trade_id} not found for closing")
            return
        
        # Обновить
        trade.exit_price = exit_price
        trade.exit_time = datetime.utcnow()
        trade.pnl_percent = pnl_percent
        trade.pnl_usd = pnl_usd
        trade.notes = notes
        
        # Определить результат
        if pnl_percent > 0.5:
            trade.result = TradeResult.WIN
        elif pnl_percent < -0.5:
            trade.result = TradeResult.LOSS
        else:
            trade.result = TradeResult.BREAKEVEN
        
        self._save()
        self._recalculate_stats()
        
        emoji = "✅" if trade.result == TradeResult.WIN else "❌"
        logger.info(f"📊 Trade closed: {emoji} {trade.symbol} {trade.pnl_percent:+.2f}%")
    
    def _recalculate_stats(self):
        """Пересчитать статистику по источникам"""
        self.source_stats = {}
        
        # Группируем по источникам
        by_source: Dict[str, List[TradeRecord]] = {}
        for t in self.trades:
            if t.result == TradeResult.OPEN:
                continue
            if t.source not in by_source:
                by_source[t.source] = []
            by_source[t.source].append(t)
        
        # Рассчитываем статистику
        for source, trades in by_source.items():
            stats = SourceStats(source=source)
            
            wins = [t for t in trades if t.result == TradeResult.WIN]
            losses = [t for t in trades if t.result == TradeResult.LOSS]
            
            stats.total_trades = len(trades)
            stats.wins = len(wins)
            stats.losses = len(losses)
            stats.breakeven = len(trades) - len(wins) - len(losses)
            
            stats.total_pnl_percent = sum(t.pnl_percent for t in trades)
            stats.total_pnl_usd = sum(t.pnl_usd for t in trades)
            
            if wins:
                stats.avg_win_percent = sum(t.pnl_percent for t in wins) / len(wins)
                stats.best_trade_percent = max(t.pnl_percent for t in wins)
            
            if losses:
                stats.avg_loss_percent = sum(t.pnl_percent for t in losses) / len(losses)
                stats.worst_trade_percent = min(t.pnl_percent for t in losses)
            
            self.source_stats[source] = stats
    
    def get_stats_by_source(self, source: str) -> Optional[SourceStats]:
        """Получить статистику по источнику"""
        self._recalculate_stats()
        return self.source_stats.get(source)
    
    def get_overall_stats(self) -> dict:
        """Получить общую статистику"""
        self._recalculate_stats()
        
        closed_trades = [t for t in self.trades if t.result != TradeResult.OPEN]
        
        if not closed_trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "total_pnl_percent": 0,
                "total_pnl_usd": 0,
                "by_source": {}
            }
        
        wins = [t for t in closed_trades if t.result == TradeResult.WIN]
        
        return {
            "total_trades": len(closed_trades),
            "wins": len(wins),
            "losses": len(closed_trades) - len(wins),
            "win_rate": (len(wins) / len(closed_trades)) * 100 if closed_trades else 0,
            "total_pnl_percent": sum(t.pnl_percent for t in closed_trades),
            "total_pnl_usd": sum(t.pnl_usd for t in closed_trades),
            "by_source": {
                source: {
                    "trades": stats.total_trades,
                    "win_rate": stats.win_rate,
                    "pnl": stats.total_pnl_percent
                }
                for source, stats in self.source_stats.items()
            }
        }
    
    def get_recent_trades(self, days: int = 7) -> List[TradeRecord]:
        """Получить сделки за последние N дней"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        return [t for t in self.trades if t.entry_time > cutoff]
    
    def format_stats_message(self) -> str:
        """Форматировать статистику для Telegram"""
        stats = self.get_overall_stats()
        
        if stats["total_trades"] == 0:
            return "📊 *Статистика*\n\nПока нет закрытых сделок."
        
        # Общая статистика
        lines = [
            "📊 *Статистика торговли*",
            "",
            f"📈 Всего сделок: {stats['total_trades']}",
            f"✅ Выигрышей: {stats['wins']}",
            f"❌ Проигрышей: {stats['losses']}",
            f"🎯 Win Rate: *{stats['win_rate']:.1f}%*",
            "",
            f"💰 Общий PnL: *{stats['total_pnl_percent']:+.2f}%*",
            f"💵 В USD: *${stats['total_pnl_usd']:+.2f}*",
            "",
            "━━━━━━━━━━━━━━━━━━",
            "*По источникам:*"
        ]
        
        for source, source_stats in stats['by_source'].items():
            emoji = "🧠" if source == "brain" else "⚡" if source == "momentum" else "🆕"
            lines.append(f"{emoji} {source}: {source_stats['win_rate']:.0f}% WR ({source_stats['trades']} сделок)")
        
        return "\n".join(lines)


# Глобальный экземпляр
trading_statistics = TradingStatistics()
