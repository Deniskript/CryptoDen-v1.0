"""
Telegram Keyboards — Кнопки интерфейса
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard(bot_running: bool, ai_enabled: bool) -> InlineKeyboardMarkup:
    """Главная клавиатура"""
    
    # Главная кнопка запуска/остановки
    if bot_running:
        main_button = InlineKeyboardButton(
            text="🛑 ОСТАНОВИТЬ БОТА",
            callback_data="stop_bot"
        )
    else:
        main_button = InlineKeyboardButton(
            text="🚀 ЗАПУСТИТЬ БОТА",
            callback_data="start_bot"
        )
    
    # AI кнопка
    if bot_running:
        ai_text = "⏸️ Пауза AI" if ai_enabled else "▶️ Включить AI"
        ai_button = InlineKeyboardButton(text=ai_text, callback_data="toggle_ai")
    else:
        ai_button = InlineKeyboardButton(text="📊 Стратегии", callback_data="strategies")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [main_button],
        [
            InlineKeyboardButton(text="📊 Статус", callback_data="status"),
            InlineKeyboardButton(text="📈 Сделки", callback_data="trades")
        ],
        [
            InlineKeyboardButton(text="📰 Новости", callback_data="news"),
            ai_button
        ],
        [
            InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
            InlineKeyboardButton(text="📋 История", callback_data="history")
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")
        ]
    ])
    
    return keyboard


def get_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="cancel")
        ]
    ])


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Кнопка назад"""
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])


def get_trades_keyboard(has_trades: bool) -> InlineKeyboardMarkup:
    """Клавиатура сделок"""
    
    buttons = []
    
    if has_trades:
        buttons.append([
            InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_trades")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_coins_keyboard(enabled_coins: dict) -> InlineKeyboardMarkup:
    """Клавиатура включения/выключения монет"""
    
    buttons = []
    row = []
    
    for symbol, enabled in enabled_coins.items():
        emoji = "✅" if enabled else "❌"
        row.append(InlineKeyboardButton(
            text=f"{emoji} {symbol}",
            callback_data=f"toggle_coin_{symbol}"
        ))
        
        if len(row) == 3:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="back")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🪙 Монеты", callback_data="coins"),
            InlineKeyboardButton(text="💰 Live/Paper", callback_data="toggle_mode")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="back")
        ]
    ])
