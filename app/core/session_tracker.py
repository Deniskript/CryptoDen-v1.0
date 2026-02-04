"""
📊 Трекер сеансов работы бота

Отслеживает:
- Сеансы работы бота (старт/стоп)
- Сигналы за каждый сеанс
- Win Rate и PnL по сеансам
- Общую статистику за всё время
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field

from app.core.logger import logger


@dataclass
class Session:
    """Сеанс работы бота"""
    id: str
    started_at: str
    ended_at: Optional[str] = None
    duration_minutes: int = 0
    signals_count: int = 0
    wins: int = 0
    losses: int = 0
    active: int = 0
    total_pnl_percent: float = 0.0
    total_pnl_usd: float = 0.0
    trades: List[dict] = field(default_factory=list)
    status: str = "ACTIVE"  # ACTIVE или CLOSED


class SessionTracker:
    """
    📊 Трекер сеансов работы бота
    
    Функции:
    - start_session() — начать новый сеанс
    - end_session() — завершить текущий сеанс
    - add_signal() — добавить сигнал
    - close_signal() — закрыть сигнал (WIN/LOSS)
    - get_current_session() — текущий сеанс
    - get_all_sessions() — история сеансов
    - get_total_stats() — общая статистика
    """
    
    def __init__(self):
        self.data_file = "/root/crypto-bot/data/sessions.json"
        self.sessions: List[Session] = []
        self.current_session: Optional[Session] = None
        self._load()
        logger.info("📊 SessionTracker initialized")
    
    def _load(self):
        """Загрузить сеансы из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    
                    for s_data in data.get("sessions", []):
                        # Убираем trades при загрузке чтобы не раздувать память
                        s_data.setdefault("trades", [])
                        s_data.setdefault("total_pnl_usd", 0.0)
                        s_data.setdefault("total_pnl_percent", s_data.get("total_pnl", 0.0))
                        if "total_pnl" in s_data and "total_pnl_percent" not in s_data:
                            s_data["total_pnl_percent"] = s_data.pop("total_pnl")
                        
                        session = Session(**{k: v for k, v in s_data.items() if k != "total_pnl"})
                        self.sessions.append(session)
                    
                    # Найти активный сеанс
                    for s in self.sessions:
                        if s.status == "ACTIVE":
                            self.current_session = s
                            break
                    
                    logger.info(f"📊 Loaded {len(self.sessions)} sessions")
        except Exception as e:
            logger.error(f"Error loading sessions: {e}")
            self.sessions = []
    
    def _save(self):
        """Сохранить сеансы в файл"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            # Сохраняем только последние 50 сеансов (для экономии места)
            sessions_to_save = self.sessions[-50:]
            
            data = {
                "sessions": [asdict(s) for s in sessions_to_save],
                "last_updated": datetime.now().isoformat()
            }
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error saving sessions: {e}")
    
    def start_session(self) -> Session:
        """
        Начать новый сеанс работы бота
        
        Returns:
            Session: Созданный сеанс
        """
        
        # Закрыть предыдущий если есть
        if self.current_session and self.current_session.status == "ACTIVE":
            logger.info("📊 Closing previous session before starting new one")
            self.end_session()
        
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.current_session = Session(
            id=session_id,
            started_at=datetime.now().isoformat(),
            status="ACTIVE"
        )
        
        self.sessions.append(self.current_session)
        self._save()
        
        logger.info(f"📊 Session started: {session_id}")
        
        return self.current_session
    
    def end_session(self) -> Optional[Session]:
        """
        Завершить текущий сеанс
        
        Returns:
            Session: Завершённый сеанс или None
        """
        
        if not self.current_session:
            return None
        
        self.current_session.ended_at = datetime.now().isoformat()
        self.current_session.status = "CLOSED"
        
        # Рассчитать длительность
        try:
            started = datetime.fromisoformat(self.current_session.started_at)
            ended = datetime.fromisoformat(self.current_session.ended_at)
            self.current_session.duration_minutes = int((ended - started).total_seconds() / 60)
        except Exception:
            self.current_session.duration_minutes = 0
        
        self._save()
        
        logger.info(f"📊 Session ended: {self.current_session.id} "
                   f"(signals: {self.current_session.signals_count}, "
                   f"PnL: {self.current_session.total_pnl_percent:+.2f}%)")
        
        closed_session = self.current_session
        self.current_session = None
        
        return closed_session
    
    def add_signal(
        self,
        symbol: str,
        direction: str,
        entry: float,
        sl: float,
        tp: float,
        confidence: int,
        size_usd: float = 150.0
    ):
        """
        Добавить сигнал в текущий сеанс
        
        Args:
            symbol: BTC, ETH, etc.
            direction: LONG или SHORT
            entry: Цена входа
            sl: Stop Loss
            tp: Take Profit
            confidence: Уверенность AI
            size_usd: Размер позиции
        """
        
        if not self.current_session:
            self.start_session()
        
        trade = {
            "symbol": symbol,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "confidence": confidence,
            "size_usd": size_usd,
            "opened_at": datetime.now().isoformat(),
            "result": "ACTIVE",
            "pnl_percent": 0,
            "pnl_usd": 0
        }
        
        self.current_session.trades.append(trade)
        self.current_session.signals_count += 1
        self.current_session.active += 1
        
        self._save()
        
        logger.debug(f"📊 Signal added to session: {direction} {symbol}")
    
    def close_signal(
        self,
        symbol: str,
        direction: str,
        result: str,
        pnl_percent: float,
        pnl_usd: float = 0.0
    ):
        """
        Закрыть сигнал (WIN/LOSS)
        
        Args:
            symbol: BTC, ETH, etc.
            direction: LONG или SHORT
            result: WIN или LOSS
            pnl_percent: PnL в процентах
            pnl_usd: PnL в долларах
        """
        
        if not self.current_session:
            return
        
        # Найти сигнал (последний активный по этому символу)
        for trade in reversed(self.current_session.trades):
            if (trade["symbol"] == symbol and 
                trade["direction"] == direction and 
                trade["result"] == "ACTIVE"):
                
                trade["result"] = result
                trade["pnl_percent"] = pnl_percent
                trade["pnl_usd"] = pnl_usd
                trade["closed_at"] = datetime.now().isoformat()
                break
        
        # Обновить счётчики
        self.current_session.active = max(0, self.current_session.active - 1)
        
        if result == "WIN":
            self.current_session.wins += 1
        else:
            self.current_session.losses += 1
        
        self.current_session.total_pnl_percent += pnl_percent
        self.current_session.total_pnl_usd += pnl_usd
        
        self._save()
        
        logger.info(f"📊 Signal closed in session: {symbol} {result} ({pnl_percent:+.2f}%)")
    
    def get_current_session(self) -> Optional[dict]:
        """
        Получить текущий сеанс
        
        Returns:
            dict: Данные текущего сеанса или None
        """
        
        if not self.current_session:
            return None
        
        # Рассчитать текущую длительность
        try:
            started = datetime.fromisoformat(self.current_session.started_at)
            duration = int((datetime.now() - started).total_seconds() / 60)
        except Exception:
            duration = 0
        
        total = self.current_session.wins + self.current_session.losses
        win_rate = (self.current_session.wins / total * 100) if total > 0 else 0
        
        return {
            "id": self.current_session.id,
            "started_at": self.current_session.started_at,
            "duration_minutes": duration,
            "duration_formatted": self._format_duration(duration),
            "signals_count": self.current_session.signals_count,
            "wins": self.current_session.wins,
            "losses": self.current_session.losses,
            "active": self.current_session.active,
            "win_rate": round(win_rate, 1),
            "total_pnl_percent": round(self.current_session.total_pnl_percent, 2),
            "total_pnl_usd": round(self.current_session.total_pnl_usd, 2),
            "status": "ACTIVE"
        }
    
    def get_all_sessions(self, limit: int = 10) -> List[dict]:
        """
        Получить все сеансы
        
        Args:
            limit: Максимальное количество
        
        Returns:
            List[dict]: Список сеансов (новые сначала)
        """
        
        result = []
        
        for s in reversed(self.sessions[-limit:]):
            total = s.wins + s.losses
            win_rate = (s.wins / total * 100) if total > 0 else 0
            
            result.append({
                "id": s.id,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "duration_minutes": s.duration_minutes,
                "duration_formatted": self._format_duration(s.duration_minutes),
                "signals_count": s.signals_count,
                "wins": s.wins,
                "losses": s.losses,
                "win_rate": round(win_rate, 1),
                "total_pnl_percent": round(s.total_pnl_percent, 2),
                "total_pnl_usd": round(s.total_pnl_usd, 2),
                "status": s.status
            })
        
        return result
    
    def get_total_stats(self) -> dict:
        """
        Общая статистика за всё время
        
        Returns:
            dict: Общая статистика
        """
        
        total_sessions = len(self.sessions)
        total_signals = sum(s.signals_count for s in self.sessions)
        total_wins = sum(s.wins for s in self.sessions)
        total_losses = sum(s.losses for s in self.sessions)
        total_pnl_percent = sum(s.total_pnl_percent for s in self.sessions)
        total_pnl_usd = sum(s.total_pnl_usd for s in self.sessions)
        
        total_closed = total_wins + total_losses
        win_rate = (total_wins / total_closed * 100) if total_closed > 0 else 0
        
        # Средняя длительность сеанса
        closed_sessions = [s for s in self.sessions if s.status == "CLOSED"]
        avg_duration = 0
        if closed_sessions:
            avg_duration = sum(s.duration_minutes for s in closed_sessions) / len(closed_sessions)
        
        return {
            "total_sessions": total_sessions,
            "total_signals": total_signals,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "win_rate": round(win_rate, 1),
            "total_pnl_percent": round(total_pnl_percent, 2),
            "total_pnl_usd": round(total_pnl_usd, 2),
            "avg_session_duration": round(avg_duration),
            "avg_duration_formatted": self._format_duration(int(avg_duration))
        }
    
    def _format_duration(self, minutes: int) -> str:
        """Форматировать длительность"""
        if minutes < 60:
            return f"{minutes}мин"
        hours = minutes // 60
        mins = minutes % 60
        if hours < 24:
            return f"{hours}ч {mins}мин"
        days = hours // 24
        hours = hours % 24
        return f"{days}д {hours}ч"
    
    def get_status_text(self) -> str:
        """Текст статуса для Telegram"""
        
        current = self.get_current_session()
        total = self.get_total_stats()
        
        lines = ["📊 *Session Tracker*", ""]
        
        # Текущий сеанс
        if current:
            pnl_emoji = "🟢" if current["total_pnl_percent"] >= 0 else "🔴"
            lines.extend([
                "🔴 *Текущий сеанс:*",
                f"• Время: {current['duration_formatted']}",
                f"• Сигналов: {current['signals_count']}",
                f"• Активных: {current['active']}",
                f"• Win/Loss: {current['wins']}/{current['losses']}",
                f"• Win Rate: {current['win_rate']}%",
                f"• {pnl_emoji} PnL: *{current['total_pnl_percent']:+.2f}%* (${current['total_pnl_usd']:+.2f})",
                ""
            ])
        else:
            lines.extend([
                "⏹ *Бот не запущен*",
                ""
            ])
        
        # Общая статистика
        total_emoji = "🟢" if total["total_pnl_percent"] >= 0 else "🔴"
        lines.extend([
            "━━━━━━━━━━━━━━━━━━",
            "*📈 Общая статистика:*",
            f"• Сеансов: {total['total_sessions']}",
            f"• Всего сигналов: {total['total_signals']}",
            f"• Win/Loss: {total['total_wins']}/{total['total_losses']}",
            f"• Win Rate: {total['win_rate']}%",
            f"• {total_emoji} Общий PnL: *{total['total_pnl_percent']:+.2f}%* (${total['total_pnl_usd']:+.2f})",
            f"• Средний сеанс: {total['avg_duration_formatted']}"
        ])
        
        return "\n".join(lines)


# Глобальный экземпляр
session_tracker = SessionTracker()
