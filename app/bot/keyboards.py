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
    Главная клавиатура v3.0 — 6 кнопок
    """
    
    webapp_url = settings.webapp_url or "https://app.cryptoden.ru"
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🦊 CryptoDen",
                    web_app=WebAppInfo(url=webapp_url)
                ),
                KeyboardButton(
                    text="📊 Статистика",
                    web_app=WebAppInfo(url=f"{webapp_url}/stats")
                )
            ],
            [
                KeyboardButton(
                    text="🐋 Рынок",
                    web_app=WebAppInfo(url=f"{webapp_url}/market")
                ),
                KeyboardButton(
                    text="📰 Новости",
                    web_app=WebAppInfo(url=f"{webapp_url}/news")
                )
            ],
            [
                KeyboardButton(
                    text="🔍 Анализ",
                    web_app=WebAppInfo(url=f"{webapp_url}/analyze")
                ),
                KeyboardButton(text="❓ Помощь")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    
    return keyboard
