"""
🤖 CryptoDen Trading Modules
"""
from app.modules.base_module import BaseModule, ModuleSignal
from app.modules.grid_bot import grid_bot, GridBot
from app.modules.funding_scalper import funding_scalper, FundingScalper
from app.modules.arbitrage import arbitrage_scanner, ArbitrageScanner
from app.modules.listing_hunter import listing_hunter, ListingHunter

__all__ = [
    "BaseModule",
    "ModuleSignal", 
    "grid_bot",
    "GridBot",
    "funding_scalper",
    "FundingScalper",
    "arbitrage_scanner",
    "ArbitrageScanner",
    "listing_hunter",
    "ListingHunter",
]
