"""
CryptoDen — Главная точка входа
"""
import asyncio
import signal
import sys

from app.core.config import settings
from app.core.logger import logger
from app.core.monitor import market_monitor


async def main():
    """Главная функция"""
    
    logger.info("=" * 50)
    logger.info("🚀 CRYPTODEN TRADING BOT")
    logger.info("=" * 50)
    
    # Обработка Ctrl+C
    loop = asyncio.get_event_loop()
    
    def shutdown():
        logger.info("Shutting down...")
        asyncio.create_task(market_monitor.stop())
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)
    
    # Запуск мониторинга
    await market_monitor.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
