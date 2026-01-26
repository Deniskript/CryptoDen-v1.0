"""
Settings Handler - /settings
============================
"""

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from app.core.config import settings
from app.core.constants import COINS
from app.bot.keyboards import get_settings_keyboard

router = Router(name="settings")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Команда /settings"""
    await send_settings(message)


@router.message(lambda m: m.text == "⚙️ Настройки")
async def btn_settings(message: Message):
    """Кнопка Настройки"""
    await send_settings(message)


async def send_settings(message: Message):
    """Отправить настройки"""
    auto_status = "🟢 ON" if settings.auto_trading_enabled else "🔴 OFF"
    testnet_status = "🧪 TESTNET" if settings.bybit_testnet else "💰 MAINNET"
    
    text = f"""
⚙️ <b>НАСТРОЙКИ</b>

🤖 <b>Auto Trading:</b> {auto_status}
🏦 <b>Биржа:</b> {testnet_status}
💰 <b>Размер позиции:</b> ${settings.default_position_size_usdt:.0f}

📊 <b>Монеты:</b>
{', '.join(COINS)}

<i>Нажми кнопку для изменения:</i>
"""
    
    await message.answer(text, reply_markup=get_settings_keyboard())


@router.callback_query(lambda c: c.data == "toggle_auto")
async def toggle_auto_trading(callback: CallbackQuery):
    """Переключить авто-торговлю"""
    # TODO: Реализовать переключение
    await callback.answer("Auto Trading toggle (coming soon)", show_alert=True)


@router.callback_query(lambda c: c.data == "select_coins")
async def select_coins(callback: CallbackQuery):
    """Выбрать монеты"""
    await callback.answer("Coin selection (coming soon)", show_alert=True)


@router.callback_query(lambda c: c.data == "set_position")
async def set_position_size(callback: CallbackQuery):
    """Установить размер позиции"""
    await callback.answer("Position size setting (coming soon)", show_alert=True)


@router.callback_query(lambda c: c.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    """Вернуться в главное меню"""
    await callback.message.delete()
    await callback.answer()
