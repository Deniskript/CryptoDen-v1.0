"""
Telegram Keyboards — минимум кнопок + WebApp
"""
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo
)
from app.core.config import settings


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура внизу"""
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статус"), KeyboardButton(text="📈 Сделки")],
            [KeyboardButton(text="📰 Новости"), KeyboardButton(text="📋 История")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def get_start_button() -> InlineKeyboardMarkup:
    """Кнопка запуска (открывает WebApp)"""
    
    webapp_url = settings.webapp_url
    
    if webapp_url:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚀 Запустить бота",
                web_app=WebAppInfo(url=webapp_url)
            )]
        ])
    else:
        # Если WebApp не настроен — обычная кнопка
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚀 Запустить бота",
                callback_data="start_bot"
            )]
        ])


def get_stop_button() -> InlineKeyboardMarkup:
    """Кнопка остановки"""
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🛑 Остановить бота",
            callback_data="stop_bot"
        )]
    ])


def get_confirm_stop() -> InlineKeyboardMarkup:
    """Подтверждение остановки"""
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="confirm_stop"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel_stop")
        ]
    ])
