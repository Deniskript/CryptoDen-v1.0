"""
CryptoDen — Точка входа

Бот НЕ запускается автоматически!
Ожидает команду /run в Telegram для начала торговли.

Экономия токенов: AI работает только когда бот запущен.
"""
import asyncio
import signal as sig

from app.core.logger import logger
from app.notifications import telegram_bot


async def main():
    """Главная функция — только Telegram polling"""
    
    logger.info("=" * 60)
    logger.info("🤖 CRYPTODEN BOT READY")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📱 Waiting for Telegram commands...")
    logger.info("")
    logger.info("💡 Control bot via Telegram WebApp:")
    logger.info("   🎛 Панель управления — Settings & Start/Stop")
    logger.info("   📊 Статус — Current status")
    logger.info("   📈 Сделки — Active trades")
    logger.info("   📰 Новости — Market context")
    logger.info("   📋 История — Trade history")
    logger.info("")
    logger.info("💰 AI works only when bot is running!")
    logger.info("=" * 60)
    
    # Только слушаем Telegram команды
    # Управление через WebApp
    await telegram_bot.start_polling()


async def shutdown():
    """Graceful shutdown"""
    from app.core.monitor import market_monitor
    
    if market_monitor.running:
        await market_monitor.stop()
    
    await telegram_bot.stop()
    logger.info("👋 Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n⏹️ Stopped by user (Ctrl+C)")
        asyncio.run(shutdown())
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
