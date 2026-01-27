"""
🤖 CryptoDen Trading Modules
Модульная система для разных стратегий торговли
"""

from app.modules.base_module import BaseModule, ModuleSignal
from app.modules.grid_bot import grid_bot, GridBot
from app.modules.funding_scalper import funding_scalper, FundingScalper

__all__ = [
    "BaseModule",
    "ModuleSignal",
    "grid_bot",
    "GridBot",
    "funding_scalper",
    "FundingScalper",
]
