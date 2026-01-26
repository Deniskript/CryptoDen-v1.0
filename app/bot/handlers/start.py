"""
Start Handler - /start, /help
=============================
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command

from app.bot.keyboards import get_main_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start"""
    user = message.from_user
    
    text = f"""
🚀 <b>Добро пожаловать в CryptoDen!</b>

Привет, {user.first_name}! 👋

Я — AI торговый бот для криптовалют.

<b>Что я умею:</b>
• 📊 140+ торговых стратегий
• 📰 Анализ новостей
• 🤖 AI принятие решений
• 📈 Автоматическая торговля

<b>Используй меню ниже для навигации!</b>
"""
    
    await message.answer(
        text,
        reply_markup=get_main_keyboard()
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help"""
    text = """
📚 <b>ПОМОЩЬ</b>

<b>Команды:</b>
/start — Начать
/status — Статус системы
/signals — Текущие сигналы
/trades — Активные сделки
/news — Новости рынка
/settings — Настройки

<b>Кнопки меню:</b>
📊 Статус — состояние системы
📈 Сигналы — текущие сигналы
📰 Новости — новости рынка
💼 Сделки — активные позиции
⚙️ Настройки — параметры бота

<b>Поддержка:</b> @cryptoden_support
"""
    
    await message.answer(text)


@router.message(lambda m: m.text == "❓ Помощь")
async def btn_help(message: Message):
    """Кнопка Помощь"""
    await cmd_help(message)
