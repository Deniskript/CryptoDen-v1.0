"""
Constants - Константы приложения
================================

Все константы в одном месте для удобства.
"""

from typing import List, Dict

# === Монеты для торговли ===
# Выбраны по результатам бэктестинга (WR 64%+)
COINS: List[str] = [
    "BTC",   # Bitcoin
    "ETH",   # Ethereum
    "BNB",   # Binance Coin
    "SOL",   # Solana
    "XRP",   # Ripple
    "ADA",   # Cardano
    "DOGE",  # Dogecoin
    "MATIC", # Polygon
    "LINK",  # Chainlink
    "AVAX",  # Avalanche
]

# === Таймфреймы ===
TIMEFRAMES: List[str] = ["1", "5", "15", "60", "240", "D"]

# === Стратегии по умолчанию ===
# Формат: {coin: {strategy_name, direction, params}}
DEFAULT_STRATEGIES: Dict[str, Dict] = {
    "BTC": {"strategy": "RSI_OVERBOUGHT", "direction": "SHORT", "rsi_period": 21, "rsi_level": 80},
    "ETH": {"strategy": "STOCH_MACD", "direction": "LONG", "stoch_period": 14, "stoch_level": 25},
    "BNB": {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "SOL": {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "XRP": {"strategy": "RSI_STOCH_EMA", "direction": "LONG", "rsi_level": 40, "stoch_level": 30},
    "ADA": {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "DOGE": {"strategy": "STOCH_MACD", "direction": "LONG", "stoch_period": 14, "stoch_level": 30},
    "MATIC": {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "LINK": {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "AVAX": {"strategy": "DOUBLE_BOTTOM", "direction": "LONG"},
}

# === Risk Management ===
DEFAULT_TP_PERCENT = 0.3   # Take Profit 0.3%
DEFAULT_SL_PERCENT = 0.5   # Stop Loss 0.5%
DEFAULT_RR_RATIO = 0.6     # Risk/Reward

MAX_OPEN_POSITIONS = 5
MAX_POSITION_SIZE_PERCENT = 20  # Max 20% баланса на одну позицию

# === Timing ===
SIGNAL_CHECK_INTERVAL = 60  # Проверка сигналов каждые 60 сек
NEWS_CHECK_INTERVAL = 300   # Проверка новостей каждые 5 мин
POSITION_UPDATE_INTERVAL = 30  # Обновление позиций каждые 30 сек

# === News Sources (для парсинга) ===
NEWS_SOURCES = [
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]

# === Critical Events (остановка торговли) ===
CRITICAL_EVENTS = [
    "FOMC",
    "CPI",
    "NFP",
    "FED",
    "SEC",
    "hack",
    "exploit",
    "bankruptcy",
]
