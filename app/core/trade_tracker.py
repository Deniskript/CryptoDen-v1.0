"""
🎯 Трекер активных сделок DirectorBrain

Отслеживает:
- Открытые сделки
- PnL в реальном времени
- Trailing Stop Loss
- Статистику (Win Rate, Total PnL)
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
import asyncio

from app.core.logger import logger
from app.core.statistics import trading_statistics


# Lazy import для избежания циклической зависимости
def get_session_tracker():
    from app.core.session_tracker import session_tracker
    return session_tracker


@dataclass
class ActiveTrade:
    """Активная сделка"""
    id: str
    symbol: str
    direction: str  # LONG или SHORT
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    original_sl: float  # Изначальный SL
    original_tp: float  # Изначальный TP
    confidence: int
    opened_at: str
    last_update: str
    pnl_percent: float = 0.0
    pnl_usd: float = 0.0
    size_usd: float = 150.0  # Размер позиции
    sl_moves: int = 0  # Сколько раз двигали SL
    highest_price: float = 0.0  # Максимальная цена (для trailing)
    lowest_price: float = 999999.0  # Минимальная цена (для trailing)
    status: str = "ACTIVE"  # ACTIVE, CLOSED_TP, CLOSED_SL, CLOSED_MANUAL
    reasoning: str = ""  # Причина входа
    last_pnl_notification: str = ""  # Время последнего уведомления о PnL
    source: str = "brain"  # Источник сигнала (brain, momentum, listing, etc.)
    last_notified_pnl: float = 0.0  # PnL при последнем уведомлении


class TradeTracker:
    """
    🎯 Трекер сделок DirectorBrain
    
    Функции:
    - Открытие/закрытие сделок
    - Trailing Stop Loss
    - Расчёт PnL
    - Сохранение статистики
    """
    
    def __init__(self):
        self.data_file = "/root/crypto-bot/data/active_trades.json"
        self.stats_file = "/root/crypto-bot/data/trade_stats.json"
        self.active_trades: Dict[str, ActiveTrade] = {}
        self._load_trades()
        logger.info("🎯 TradeTracker initialized")
    
    def _load_trades(self):
        """Загрузить активные сделки из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    for trade_id, trade_data in data.items():
                        self.active_trades[trade_id] = ActiveTrade(**trade_data)
                logger.info(f"🎯 Loaded {len(self.active_trades)} active trades")
        except Exception as e:
            logger.error(f"Error loading trades: {e}")
            self.active_trades = {}
    
    def _save_trades(self):
        """Сохранить активные сделки в файл"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            data = {tid: asdict(t) for tid, t in self.active_trades.items()}
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving trades: {e}")
    
    def open_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        confidence: int,
        size_usd: float = 150.0,
        reasoning: str = "",
        source: str = "brain"
    ) -> ActiveTrade:
        """
        Открыть новую сделку
        
        Args:
            symbol: BTC, ETH, etc.
            direction: LONG или SHORT
            entry_price: Цена входа
            stop_loss: Stop Loss
            take_profit: Take Profit
            confidence: Уверенность AI (0-100)
            size_usd: Размер позиции в USD
            reasoning: Причина входа
            source: Источник сигнала (brain, momentum, listing, etc.)
        
        Returns:
            ActiveTrade: Созданная сделка
        """
        
        # Проверить есть ли уже активная сделка по этому символу
        existing = self.get_trade_by_symbol(symbol)
        if existing:
            logger.warning(f"🎯 Already have active trade for {symbol}")
            return existing
        
        trade_id = f"{symbol}_{direction}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        now = datetime.now().isoformat()
        
        trade = ActiveTrade(
            id=trade_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            current_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            original_sl=stop_loss,
            original_tp=take_profit,
            confidence=confidence,
            opened_at=now,
            last_update=now,
            pnl_percent=0.0,
            pnl_usd=0.0,
            size_usd=size_usd,
            source=source,
            sl_moves=0,
            highest_price=entry_price,
            lowest_price=entry_price,
            status="ACTIVE",
            reasoning=reasoning[:500] if reasoning else ""
        )
        
        self.active_trades[trade_id] = trade
        self._save_trades()
        
        # Добавить в сеанс
        try:
            session = get_session_tracker()
            session.add_signal(
                symbol=symbol,
                direction=direction,
                entry=entry_price,
                sl=stop_loss,
                tp=take_profit,
                confidence=confidence,
                size_usd=size_usd
            )
        except Exception as e:
            logger.warning(f"Failed to add signal to session: {e}")
        
        logger.info(f"🎯 Opened trade: {direction} {symbol} @ ${entry_price:,.2f} "
                   f"(SL: ${stop_loss:,.2f}, TP: ${take_profit:,.2f})")
        
        # Записать в статистику
        try:
            trading_statistics.record_trade_open(
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                source=source,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence
            )
        except Exception as e:
            logger.warning(f"Failed to record trade stats: {e}")
        
        return trade
    
    def update_trade(self, trade_id: str, current_price: float) -> Optional[dict]:
        """
        Обновить сделку и вернуть действие если нужно
        
        Args:
            trade_id: ID сделки
            current_price: Текущая цена
        
        Returns:
            None - ничего не делать
            {"action": "UPDATE_SL", "trade": ..., "old_sl": ..., "new_sl": ..., "reason": ...}
            {"action": "CLOSE_TP", "trade": ..., "pnl": ..., "reason": ...}
            {"action": "CLOSE_SL", "trade": ..., "pnl": ..., "reason": ...}
        """
        
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades[trade_id]
        trade.current_price = current_price
        trade.last_update = datetime.now().isoformat()
        
        # Обновить high/low
        if current_price > trade.highest_price:
            trade.highest_price = current_price
        if current_price < trade.lowest_price:
            trade.lowest_price = current_price
        
        # Рассчитать PnL
        if trade.direction == "LONG":
            trade.pnl_percent = (current_price - trade.entry_price) / trade.entry_price * 100
        else:  # SHORT
            trade.pnl_percent = (trade.entry_price - current_price) / trade.entry_price * 100
        
        trade.pnl_usd = trade.size_usd * (trade.pnl_percent / 100)
        
        action = None
        
        # Проверить TP
        if trade.direction == "LONG" and current_price >= trade.take_profit:
            action = {
                "action": "CLOSE_TP",
                "trade": trade,
                "pnl_percent": trade.pnl_percent,
                "pnl_usd": trade.pnl_usd,
                "reason": f"🎯 Take Profit! ${current_price:,.2f} >= ${trade.take_profit:,.2f}"
            }
            trade.status = "CLOSED_TP"
            
        elif trade.direction == "SHORT" and current_price <= trade.take_profit:
            action = {
                "action": "CLOSE_TP",
                "trade": trade,
                "pnl_percent": trade.pnl_percent,
                "pnl_usd": trade.pnl_usd,
                "reason": f"🎯 Take Profit! ${current_price:,.2f} <= ${trade.take_profit:,.2f}"
            }
            trade.status = "CLOSED_TP"
        
        # Проверить SL
        elif trade.direction == "LONG" and current_price <= trade.stop_loss:
            action = {
                "action": "CLOSE_SL",
                "trade": trade,
                "pnl_percent": trade.pnl_percent,
                "pnl_usd": trade.pnl_usd,
                "reason": f"🛑 Stop Loss! ${current_price:,.2f} <= ${trade.stop_loss:,.2f}"
            }
            trade.status = "CLOSED_SL"
            
        elif trade.direction == "SHORT" and current_price >= trade.stop_loss:
            action = {
                "action": "CLOSE_SL",
                "trade": trade,
                "pnl_percent": trade.pnl_percent,
                "pnl_usd": trade.pnl_usd,
                "reason": f"🛑 Stop Loss! ${current_price:,.2f} >= ${trade.stop_loss:,.2f}"
            }
            trade.status = "CLOSED_SL"
        
        # Проверить нужно ли двигать SL (trailing)
        elif trade.pnl_percent >= 1.0:  # Прибыль 1%+
            new_sl = self._calculate_trailing_sl(trade, current_price)
            if new_sl and new_sl != trade.stop_loss:
                old_sl = trade.stop_loss
                trade.stop_loss = new_sl
                trade.sl_moves += 1
                action = {
                    "action": "UPDATE_SL",
                    "trade": trade,
                    "old_sl": old_sl,
                    "new_sl": new_sl,
                    "pnl_percent": trade.pnl_percent,
                    "reason": self._get_sl_move_reason(trade, old_sl, new_sl)
                }
        
        # Проверить нужно ли отправить PnL update (каждые 15 мин или при изменении на 1%+)
        if action is None:
            pnl_update = self._check_pnl_notification(trade)
            if pnl_update:
                action = pnl_update
        
        self._save_trades()
        
        # Если сделка закрыта — перенести в статистику
        if trade.status.startswith("CLOSED"):
            self._save_to_stats(trade)
            
            # Записать в новую статистику
            try:
                trading_statistics.record_trade_close(
                    trade_id=trade.id,
                    exit_price=trade.current_price,
                    pnl_percent=trade.pnl_percent,
                    pnl_usd=trade.pnl_usd,
                    notes=trade.status
                )
            except Exception as e:
                logger.warning(f"Failed to record trade close stats: {e}")
            
            # Обновить сеанс
            try:
                session = get_session_tracker()
                result = "WIN" if trade.status == "CLOSED_TP" else "LOSS"
                session.close_signal(
                    symbol=trade.symbol,
                    direction=trade.direction,
                    result=result,
                    pnl_percent=trade.pnl_percent,
                    pnl_usd=trade.pnl_usd
                )
            except Exception as e:
                logger.warning(f"Failed to close signal in session: {e}")
            
            del self.active_trades[trade_id]
            self._save_trades()
            logger.info(f"🎯 Trade closed: {trade.symbol} {trade.status} PnL: {trade.pnl_percent:+.2f}%")
        
        return action
    
    def update_all_trades(self, prices: Dict[str, float]) -> List[dict]:
        """
        Обновить все активные сделки
        
        Args:
            prices: {"BTC": 81200.5, "ETH": 3200.0, ...}
        
        Returns:
            List[dict]: Список действий для уведомлений
        """
        actions = []
        
        # Копируем ключи чтобы избежать изменения dict во время итерации
        trade_ids = list(self.active_trades.keys())
        
        for trade_id in trade_ids:
            trade = self.active_trades.get(trade_id)
            if not trade:
                continue
            
            price = prices.get(trade.symbol)
            if price:
                action = self.update_trade(trade_id, price)
                if action:
                    actions.append(action)
        
        return actions
    
    def _calculate_trailing_sl(self, trade: ActiveTrade, current_price: float) -> Optional[float]:
        """
        Рассчитать новый trailing SL
        
        Логика:
        - +1% прибыли → SL на безубыток
        - +2% прибыли → SL на +1% от входа
        - +3% прибыли → SL на +2% от входа
        - и т.д.
        """
        
        if trade.direction == "LONG":
            # Минимум на безубыток после +1%
            if trade.pnl_percent >= 1.0 and trade.stop_loss < trade.entry_price:
                return round(trade.entry_price, 2)  # Безубыток
            
            # Подтягивать SL: прибыль - 1%
            if trade.pnl_percent >= 2.0:
                # SL = entry + (pnl - 1)%
                locked_profit = trade.pnl_percent - 1.0
                new_sl = trade.entry_price * (1 + locked_profit / 100)
                new_sl = round(new_sl, 2)
                
                if new_sl > trade.stop_loss:
                    return new_sl
        
        else:  # SHORT
            if trade.pnl_percent >= 1.0 and trade.stop_loss > trade.entry_price:
                return round(trade.entry_price, 2)  # Безубыток
            
            if trade.pnl_percent >= 2.0:
                locked_profit = trade.pnl_percent - 1.0
                new_sl = trade.entry_price * (1 - locked_profit / 100)
                new_sl = round(new_sl, 2)
                
                if new_sl < trade.stop_loss:
                    return new_sl
        
        return None
    
    def _get_sl_move_reason(self, trade: ActiveTrade, old_sl: float, new_sl: float) -> str:
        """Получить причину передвижения SL"""
        
        if trade.direction == "LONG":
            if new_sl == trade.entry_price:
                return "✅ SL → безубыток"
            profit_locked = (new_sl - trade.entry_price) / trade.entry_price * 100
            return f"📈 SL → +{profit_locked:.1f}% зафиксировано"
        else:
            if new_sl == trade.entry_price:
                return "✅ SL → безубыток"
            profit_locked = (trade.entry_price - new_sl) / trade.entry_price * 100
            return f"📈 SL → +{profit_locked:.1f}% зафиксировано"
    
    def _check_pnl_notification(self, trade: ActiveTrade) -> Optional[dict]:
        """
        Проверить нужно ли отправить уведомление об изменении PnL
        
        Отправляем если:
        1. Прошло 15 минут с последнего уведомления
        2. PnL изменился на 1%+ от последнего уведомления
        """
        now = datetime.now()
        
        # Проверяем время последнего уведомления
        should_notify = False
        reason = ""
        
        if trade.last_pnl_notification:
            try:
                last_notif = datetime.fromisoformat(trade.last_pnl_notification)
                elapsed_minutes = (now - last_notif).total_seconds() / 60
                
                # Прошло 15 минут?
                if elapsed_minutes >= 15:
                    pnl_change = abs(trade.pnl_percent - trade.last_notified_pnl)
                    if pnl_change >= 0.5:  # Изменение на 0.5%+
                        should_notify = True
                        if trade.pnl_percent > trade.last_notified_pnl:
                            reason = f"📈 +{pnl_change:.1f}% за 15 мин"
                        else:
                            reason = f"📉 -{pnl_change:.1f}% за 15 мин"
                
                # Значительное изменение (1%+) независимо от времени
                pnl_change = abs(trade.pnl_percent - trade.last_notified_pnl)
                if pnl_change >= 1.0 and elapsed_minutes >= 5:  # Минимум 5 мин между сообщениями
                    should_notify = True
                    if trade.pnl_percent > trade.last_notified_pnl:
                        reason = f"🚀 Быстрый рост +{pnl_change:.1f}%!"
                    else:
                        reason = f"⚠️ Быстрое падение -{pnl_change:.1f}%"
                        
            except Exception:
                # Если ошибка парсинга — отправляем первое уведомление
                should_notify = True
                reason = "📊 Первое обновление"
        else:
            # Первое уведомление после открытия (через 15 минут)
            try:
                opened_at = datetime.fromisoformat(trade.opened_at)
                elapsed_minutes = (now - opened_at).total_seconds() / 60
                if elapsed_minutes >= 15:
                    should_notify = True
                    reason = "📊 15 мин после открытия"
            except Exception:
                pass
        
        if should_notify:
            # Обновляем метки
            trade.last_pnl_notification = now.isoformat()
            trade.last_notified_pnl = trade.pnl_percent
            
            return {
                "action": "PNL_UPDATE",
                "trade": trade,
                "pnl_percent": trade.pnl_percent,
                "pnl_usd": trade.pnl_usd,
                "reason": reason
            }
        
        return None
    
    def _save_to_stats(self, trade: ActiveTrade):
        """Сохранить закрытую сделку в статистику"""
        try:
            stats = {"trades": [], "summary": {}}
            
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    stats = json.load(f)
            
            # Добавить сделку
            stats["trades"].append({
                "id": trade.id,
                "symbol": trade.symbol,
                "direction": trade.direction,
                "entry": trade.entry_price,
                "exit": trade.current_price,
                "pnl_percent": round(trade.pnl_percent, 2),
                "pnl_usd": round(trade.pnl_usd, 2),
                "size_usd": trade.size_usd,
                "result": "WIN" if trade.status == "CLOSED_TP" else "LOSS",
                "confidence": trade.confidence,
                "opened_at": trade.opened_at,
                "closed_at": datetime.now().isoformat(),
                "sl_moves": trade.sl_moves,
                "original_sl": trade.original_sl,
                "original_tp": trade.original_tp
            })
            
            # Обновить summary
            trades = stats["trades"]
            wins = len([t for t in trades if t["result"] == "WIN"])
            losses = len([t for t in trades if t["result"] == "LOSS"])
            total_pnl_percent = sum(t["pnl_percent"] for t in trades)
            total_pnl_usd = sum(t.get("pnl_usd", 0) for t in trades)
            
            stats["summary"] = {
                "total": len(trades),
                "wins": wins,
                "losses": losses,
                "win_rate": round(wins / len(trades) * 100, 1) if trades else 0,
                "total_pnl_percent": round(total_pnl_percent, 2),
                "total_pnl_usd": round(total_pnl_usd, 2),
                "avg_pnl": round(total_pnl_percent / len(trades), 2) if trades else 0,
                "last_updated": datetime.now().isoformat()
            }
            
            os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)
            with open(self.stats_file, 'w') as f:
                json.dump(stats, f, indent=2)
                
            logger.info(f"🎯 Stats updated: {stats['summary']}")
                
        except Exception as e:
            logger.error(f"Error saving stats: {e}")
    
    def get_active_trades(self) -> List[ActiveTrade]:
        """Получить все активные сделки"""
        return list(self.active_trades.values())
    
    def get_trade_by_symbol(self, symbol: str) -> Optional[ActiveTrade]:
        """Найти активную сделку по символу"""
        for trade in self.active_trades.values():
            if trade.symbol == symbol and trade.status == "ACTIVE":
                return trade
        return None
    
    def close_trade_manual(self, trade_id: str, current_price: float, reason: str = "Manual close") -> Optional[dict]:
        """Закрыть сделку вручную"""
        if trade_id not in self.active_trades:
            return None
        
        trade = self.active_trades[trade_id]
        trade.current_price = current_price
        
        # Рассчитать PnL
        if trade.direction == "LONG":
            trade.pnl_percent = (current_price - trade.entry_price) / trade.entry_price * 100
        else:
            trade.pnl_percent = (trade.entry_price - current_price) / trade.entry_price * 100
        
        trade.pnl_usd = trade.size_usd * (trade.pnl_percent / 100)
        trade.status = "CLOSED_MANUAL"
        
        self._save_to_stats(trade)
        del self.active_trades[trade_id]
        self._save_trades()
        
        return {
            "action": "CLOSE_MANUAL",
            "trade": trade,
            "pnl_percent": trade.pnl_percent,
            "pnl_usd": trade.pnl_usd,
            "reason": reason
        }
    
    def get_stats(self) -> dict:
        """Получить статистику"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {"trades": [], "summary": {}}
    
    def get_stats_by_source(self) -> dict:
        """Статистика по источникам сигналов"""
        stats = {}
        
        # Из активных сделок (пока не закрыты)
        for trade in self.active_trades.values():
            source = getattr(trade, 'source', 'brain')
            if source not in stats:
                stats[source] = {
                    "total": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0,
                    "pnl": 0.0,
                    "pnl_percent": 0.0
                }
        
        # Из закрытых сделок
        all_stats = self.get_stats()
        for trade in all_stats.get('trades', []):
            source = trade.get('source', 'brain')
            
            if source not in stats:
                stats[source] = {
                    "total": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0,
                    "pnl": 0.0,
                    "pnl_percent": 0.0
                }
            
            stats[source]["total"] += 1
            
            pnl = trade.get('pnl_usd', 0) or 0
            pnl_percent = trade.get('pnl_percent', 0) or 0
            
            stats[source]["pnl"] += pnl
            stats[source]["pnl_percent"] += pnl_percent
            
            result = trade.get('result', '')
            if result == 'WIN' or pnl > 0:
                stats[source]["wins"] += 1
            else:
                stats[source]["losses"] += 1
        
        # Рассчитать win rate
        for source in stats:
            total = stats[source]["total"]
            if total > 0:
                stats[source]["win_rate"] = (stats[source]["wins"] / total) * 100
        
        return stats
    
    def get_status_text(self) -> str:
        """Текст статуса для Telegram"""
        trades = self.get_active_trades()
        stats = self.get_stats().get("summary", {})
        
        lines = [
            "🎯 *Trade Tracker*",
            "",
            f"📊 Активных сделок: *{len(trades)}*"
        ]
        
        # Активные сделки
        if trades:
            lines.append("")
            for t in trades:
                emoji = "🟢" if t.pnl_percent >= 0 else "🔴"
                dir_emoji = "📈" if t.direction == "LONG" else "📉"
                lines.append(
                    f"{dir_emoji} *{t.symbol}* {t.direction}\n"
                    f"   Entry: ${t.entry_price:,.2f} → ${t.current_price:,.2f}\n"
                    f"   {emoji} PnL: *{t.pnl_percent:+.2f}%* (${t.pnl_usd:+.2f})"
                )
        
        # Статистика
        if stats:
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━",
                "*📈 Статистика:*",
                f"• Всего сделок: {stats.get('total', 0)}",
                f"• Win Rate: {stats.get('win_rate', 0)}%",
                f"• Общий PnL: {stats.get('total_pnl_percent', 0):+.2f}%",
                f"• Прибыль: ${stats.get('total_pnl_usd', 0):+.2f}"
            ])
        
        return "\n".join(lines)


# Глобальный экземпляр
trade_tracker = TradeTracker()
