"""
Logger - Настройка логирования
==============================

Использует loguru для красивого логирования.
"""

import sys
from pathlib import Path
from loguru import logger

# Удаляем стандартный handler
logger.remove()

# Формат логов
LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

# Console output
logger.add(
    sys.stdout,
    format=LOG_FORMAT,
    level="INFO",
    colorize=True,
)

# File output
log_path = Path("/root/crypto-bot/logs/bot.log")
if log_path.parent.exists():
    logger.add(
        str(log_path),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
    )

# Экспорт
__all__ = ["logger"]
