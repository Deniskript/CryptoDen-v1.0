"""
Trades Handler - /trades
========================
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from app.trading.trade_manager import trade_manager

router = Router(name="trades")


@router.message(Command("trades"))
async def cmd_trades(message: Message):
    """Команда /trades"""
    await send_trades(message)


@router.message(lambda m: m.text == "💼 Сделки")
async def btn_trades(message: Message):
    """Кнопка Сделки"""
    await send_trades(message)


async def send_trades(message: Message):
    """Отправить список сделок"""
    open_trades = trade_manager.get_open_trades()
    
    if not open_trades:
        text = """
💼 <b>СДЕЛКИ</b>

Нет активных сделок.
"""
    else:
        text = "💼 <b>АКТИВНЫЕ СДЕЛКИ</b>\n\n"
        
        for trade in open_trades:
            direction_emoji = "🟢" if trade.direction == "LONG" else "🔴"
            pnl_emoji = "📈" if trade.pnl_percent >= 0 else "📉"
            
            text += f"{direction_emoji} <b>{trade.symbol}</b>\n"
            text += f"   💰 Entry: ${trade.entry_price:.4f}\n"
            text += f"   📍 Current: ${trade.current_price:.4f}\n"
            text += f"   {pnl_emoji} PnL: {trade.pnl_percent:+.2f}%\n"
            text += f"   🛑 SL: ${trade.stop_loss:.4f}\n"
            text += f"   🎯 TP: ${trade.take_profit:.4f}\n"
            text += f"   🆔 {trade.id}\n\n"
    
    # Статистика
    stats = trade_manager.get_stats()
    text += f"\n<b>Статистика:</b>\n"
    text += f"📊 Всего: {stats['total']} | ✅ {stats['wins']} | ❌ {stats['losses']}\n"
    text += f"📈 Win Rate: {stats['win_rate']:.1f}%\n"
    
    await message.answer(text)
