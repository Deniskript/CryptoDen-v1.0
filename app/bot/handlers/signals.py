"""
Signals Handler - /signals
==========================
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from app.strategies.signals import signal_generator
from app.brain.decision_engine import decision_engine

router = Router(name="signals")


@router.message(Command("signals"))
async def cmd_signals(message: Message):
    """Команда /signals"""
    await send_signals(message)


@router.message(lambda m: m.text == "📈 Сигналы")
async def btn_signals(message: Message):
    """Кнопка Сигналы"""
    await send_signals(message)


async def send_signals(message: Message):
    """Отправить текущие сигналы"""
    await message.answer("🔍 Анализирую рынок...")
    
    # Анализируем все монеты
    decisions = await decision_engine.analyze_all()
    
    # Фильтруем торговые сигналы
    trade_decisions = [d for d in decisions if d.action.value == "trade"]
    
    if not trade_decisions:
        text = """
📈 <b>СИГНАЛЫ</b>

Сейчас нет активных сигналов.
Бот анализирует рынок каждую минуту.
"""
    else:
        text = "📈 <b>ТЕКУЩИЕ СИГНАЛЫ</b>\n\n"
        
        for decision in trade_decisions[:5]:
            signal = decision.signal
            direction_emoji = "🟢" if signal.direction == "LONG" else "🔴"
            
            text += f"{direction_emoji} <b>{signal.symbol}</b> {signal.direction}\n"
            text += f"   💰 Entry: ${signal.entry_price:.4f}\n"
            text += f"   🎯 TP: ${signal.take_profit:.4f}\n"
            text += f"   🛑 SL: ${signal.stop_loss:.4f}\n"
            text += f"   📊 Confidence: {signal.confidence:.0%}\n\n"
    
    await message.answer(text)
