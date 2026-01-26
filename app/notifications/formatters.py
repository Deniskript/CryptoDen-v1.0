"""
Formatters - Форматирование сообщений
=====================================

Красивое форматирование для Telegram.
"""

from app.strategies.signals import TradeSignal
from app.trading.trade_manager import Trade


def format_signal(signal: TradeSignal) -> str:
    """Форматировать сигнал"""
    direction_emoji = "🟢" if signal.direction == "LONG" else "🔴"
    
    return f"""
{direction_emoji} <b>СИГНАЛ: {signal.symbol}</b>

📊 <b>Направление:</b> {signal.direction}
💰 <b>Вход:</b> ${signal.entry_price:.4f}
🛑 <b>Stop Loss:</b> ${signal.stop_loss:.4f}
🎯 <b>Take Profit:</b> ${signal.take_profit:.4f}

📈 <b>R/R:</b> {signal.risk_reward:.2f}
🎲 <b>Confidence:</b> {signal.confidence:.0%}
🤖 <b>Стратегия:</b> {signal.strategy_name}

💡 {signal.reason}
"""


def format_trade_opened(trade: Trade) -> str:
    """Форматировать открытие сделки"""
    direction_emoji = "🟢" if trade.direction == "LONG" else "🔴"
    
    return f"""
{direction_emoji} <b>СДЕЛКА ОТКРЫТА</b>

📊 <b>{trade.symbol}</b> {trade.direction}
💰 <b>Вход:</b> ${trade.entry_price:.4f}
📦 <b>Размер:</b> {trade.quantity:.4f}
🛑 <b>SL:</b> ${trade.stop_loss:.4f}
🎯 <b>TP:</b> ${trade.take_profit:.4f}

🤖 {trade.strategy_name}
🆔 {trade.id}
"""


def format_trade_closed(trade: Trade) -> str:
    """Форматировать закрытие сделки"""
    pnl_emoji = "✅" if trade.pnl > 0 else "❌"
    
    return f"""
{pnl_emoji} <b>СДЕЛКА ЗАКРЫТА</b>

📊 <b>{trade.symbol}</b>
💵 <b>PnL:</b> {trade.pnl_percent:+.2f}% (${trade.pnl:+.2f})

📍 <b>Вход:</b> ${trade.entry_price:.4f}
📍 <b>Выход:</b> ${trade.exit_price:.4f}
📝 <b>Причина:</b> {trade.exit_reason}

🆔 {trade.id}
"""


def format_status(
    is_running: bool,
    open_trades: int,
    today_pnl: float,
    win_rate: float
) -> str:
    """Форматировать статус системы"""
    status_emoji = "🟢" if is_running else "🔴"
    
    return f"""
{status_emoji} <b>СТАТУС СИСТЕМЫ</b>

🤖 <b>Бот:</b> {"Работает" if is_running else "Остановлен"}
📊 <b>Открытых сделок:</b> {open_trades}
💰 <b>PnL сегодня:</b> {today_pnl:+.2f}%
📈 <b>Win Rate:</b> {win_rate:.1f}%
"""
