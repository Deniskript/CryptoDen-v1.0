"""
News Handler - /news
====================
"""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from app.intelligence.web_parser import web_parser
from app.intelligence.market_state import market_state

router = Router(name="news")


@router.message(Command("news"))
async def cmd_news(message: Message):
    """Команда /news"""
    await send_news(message)


@router.message(lambda m: m.text == "📰 Новости")
async def btn_news(message: Message):
    """Кнопка Новости"""
    await send_news(message)


async def send_news(message: Message):
    """Отправить новости"""
    await message.answer("📰 Загружаю новости...")
    
    # Получаем новости
    try:
        news = await web_parser.fetch_news(10)
    except Exception:
        news = web_parser.get_cached()
    
    # Состояние рынка
    state = market_state.get_state()
    
    text = "📰 <b>НОВОСТИ РЫНКА</b>\n\n"
    
    # Статус рынка
    if state.trading_stopped:
        text += f"⚠️ <b>Торговля остановлена:</b> {state.reason}\n\n"
    elif state.longs_blocked:
        text += f"🔴 <b>LONGs заблокированы:</b> {state.reason}\n\n"
    elif state.shorts_blocked:
        text += f"🔴 <b>SHORTs заблокированы:</b> {state.reason}\n\n"
    elif state.longs_boosted:
        text += f"🚀 <b>LONGs +{state.longs_boost_percent}%</b>\n\n"
    
    # Новости
    if news:
        for item in news[:7]:
            # Сокращаем заголовок
            title = item.title[:60] + "..." if len(item.title) > 60 else item.title
            text += f"• {title}\n"
            text += f"  <i>{item.source} | {item.published.strftime('%H:%M')}</i>\n\n"
    else:
        text += "<i>Новости недоступны</i>"
    
    await message.answer(text, disable_web_page_preview=True)
