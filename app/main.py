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


async def start_smart_notifications():
    """Запуск умных уведомлений с реальными данными рынка"""
    try:
        from app.core.smart_notifications import smart_notifications
        from app.core.market_data_provider import market_data
        
        # Устанавливаем callback для отправки
        smart_notifications.set_send_callback(telegram_bot.send_message)
        
        # Запускаем
        await smart_notifications.start()
        
        # Получаем реальные данные рынка
        snapshot = await market_data.get_snapshot(force_refresh=True)
        logger.info(f"📊 Market: BTC=${snapshot.btc_price:,.0f}, RSI={snapshot.btc_rsi:.0f}, F&G={snapshot.fear_greed}")
        
        # Данные для startup sequence (с реальными значениями)
        startup_data = {
            "btc_price": snapshot.btc_price,
            "btc_rsi": snapshot.btc_rsi,
            "fear_greed": snapshot.fear_greed,
            "coins_count": 7,
            "minutes_to_funding": 120,
        }
        
        # Запускаем последовательность приветствия
        asyncio.create_task(smart_notifications.send_startup_sequence(startup_data))
        
        logger.info("✅ Smart Notifications started with real market data")
    except Exception as e:
        logger.error(f"❌ Smart Notifications error: {e}")
        import traceback
        traceback.print_exc()


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
    
    # Запускаем умные уведомления
    asyncio.create_task(start_smart_notifications())
    
    # Слушаем Telegram команды
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
