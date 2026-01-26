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
    logger.info("💡 Available commands:")
    logger.info("   /run    — 🚀 Start trading bot")
    logger.info("   /stop   — 🛑 Stop trading bot")
    logger.info("   /pause  — ⏸️ Toggle AI on/off")
    logger.info("   /status — 📊 Bot status")
    logger.info("   /live   — 💰 Switch Paper/Live mode")
    logger.info("")
    logger.info("💰 Tokens are saved: AI works only when bot is running!")
    logger.info("=" * 60)
    
    # Уведомляем о готовности
    await telegram_bot.notify_startup()
    
    # Только слушаем Telegram команды
    # Бот НЕ торгует пока не получит /run
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
