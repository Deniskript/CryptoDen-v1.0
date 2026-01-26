"""
Telegram Keyboards — Только навигация
Управление ботом через WebApp!
"""
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo
)
from app.core.config import settings


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Главная клавиатура — только навигация
    БЕЗ кнопок Запустить/Остановить (они в WebApp)
    """
    
    webapp_url = settings.webapp_url or "https://app.cryptoden.ru"
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            # Панель управления — WebApp
            [KeyboardButton(
                text="🎛 Панель управления",
                web_app=WebAppInfo(url=webapp_url)
            )],
            # Навигация
            [
                KeyboardButton(text="📊 Статус"),
                KeyboardButton(text="📈 Сделки")
            ],
            [
                KeyboardButton(text="📰 Новости"),
                KeyboardButton(text="📋 История")
            ],
            # Помощь
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    return keyboard
