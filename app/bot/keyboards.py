"""
Keyboards - Клавиатуры Telegram
===============================

Reply и Inline клавиатуры.
"""

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📊 Статус"),
                KeyboardButton(text="📈 Сигналы"),
            ],
            [
                KeyboardButton(text="📰 Новости"),
                KeyboardButton(text="💼 Сделки"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="❓ Помощь"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Auto Trading", callback_data="toggle_auto"),
        ],
        [
            InlineKeyboardButton(text="📊 Монеты", callback_data="select_coins"),
        ],
        [
            InlineKeyboardButton(text="💰 Размер позиции", callback_data="set_position"),
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_main"),
        ],
    ])


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no"),
        ],
    ])
