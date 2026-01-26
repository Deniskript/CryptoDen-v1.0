"""
Telegram Keyboards — Reply клавиатуры внизу экрана
"""
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура — ВСЕГДА внизу"""
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚀 Запустить"),
                KeyboardButton(text="🛑 Остановить")
            ],
            [
                KeyboardButton(text="📊 Статус"),
                KeyboardButton(text="📈 Сделки")
            ],
            [
                KeyboardButton(text="📰 Новости"),
                KeyboardButton(text="🪙 Монеты")
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="📋 История")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    return keyboard


def get_coins_keyboard(coins_status: dict) -> ReplyKeyboardMarkup:
    """Клавиатура выбора монет"""
    
    buttons = []
    row = []
    
    for coin, enabled in coins_status.items():
        emoji = "✅" if enabled else "❌"
        row.append(KeyboardButton(text=f"{emoji} {coin}"))
        
        if len(row) == 3:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    # Кнопка назад
    buttons.append([KeyboardButton(text="◀️ Назад")])
    
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        is_persistent=True
    )


def get_settings_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура настроек"""
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔑 API Ключи"),
                KeyboardButton(text="💰 Риски")
            ],
            [
                KeyboardButton(text="🧠 AI Настройки"),
                KeyboardButton(text="📝 Paper/Live")
            ],
            [KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def get_confirm_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура подтверждения"""
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✅ Да, подтверждаю"),
                KeyboardButton(text="❌ Отмена")
            ]
        ],
        resize_keyboard=True
    )


def get_back_keyboard() -> ReplyKeyboardMarkup:
    """Только кнопка назад"""
    
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="◀️ Назад")]],
        resize_keyboard=True
    )
