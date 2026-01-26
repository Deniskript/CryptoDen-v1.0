"""
Status Handler - /status
========================
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from app.trading.trade_manager import trade_manager
from app.intelligence.market_state import market_state
from app.notifications.formatters import format_status

router = Router(name="status")


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Команда /status"""
    await send_status(message)


@router.message(lambda m: m.text == "📊 Статус")
async def btn_status(message: Message):
    """Кнопка Статус"""
    await send_status(message)


async def send_status(message: Message):
    """Отправить статус"""
    # Получаем данные
    open_trades = trade_manager.get_open_trades()
    stats = trade_manager.get_stats()
    state = market_state.get_state()
    
    # Статус торговли
    trading_status = "🟢 Разрешена" if not state.trading_stopped else f"🔴 {state.reason}"
    
    text = f"""
📊 <b>СТАТУС СИСТЕМЫ</b>

🤖 <b>Торговля:</b> {trading_status}

📈 <b>Открытых сделок:</b> {len(open_trades)}
💰 <b>Всего сделок:</b> {stats['total']}
✅ <b>Побед:</b> {stats['wins']}
❌ <b>Поражений:</b> {stats['losses']}
📊 <b>Win Rate:</b> {stats['win_rate']:.1f}%
💵 <b>Total PnL:</b> ${stats['total_pnl']:.2f}
"""
    
    # Добавляем открытые сделки
    if open_trades:
        text += "\n<b>Открытые позиции:</b>\n"
        for trade in open_trades[:5]:
            pnl_emoji = "📈" if trade.pnl_percent >= 0 else "📉"
            text += f"  {pnl_emoji} {trade.symbol}: {trade.pnl_percent:+.2f}%\n"
    
    await message.answer(text)
