"""
🤖 CryptoDen Trading Modules
Модульная система для разных стратегий торговли
"""

from app.modules.base_module import BaseModule, ModuleSignal
from app.modules.grid_bot import grid_bot, GridBot

__all__ = [
    "BaseModule",
    "ModuleSignal",
    "grid_bot",
    "GridBot",
]
