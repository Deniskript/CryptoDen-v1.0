"""
Strategy Config — Конфигурация лучших стратегий из бэктеста
Автоматически обновляется после валидации
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class StrategyConfig:
    """Конфигурация одной стратегии"""
    id: str
    name: str
    symbol: str
    direction: str  # LONG, SHORT
    
    # Условия входа
    conditions: List[Dict[str, Any]]
    
    # Параметры
    tp_percent: float = 0.3
    sl_percent: float = 0.5
    
    # Статистика из бэктеста
    win_rate_2024: float = 0.0
    win_rate_2025: float = 0.0
    avg_win_rate: float = 0.0
    total_trades_per_day: float = 0.0
    profit_factor: float = 1.0
    
    # Управление
    enabled: bool = True
    max_signals_per_day: int = 3
    min_time_between_signals_minutes: int = 60
    
    # Meta
    last_updated: str = ""


# Лучшие стратегии из бэктеста 2024-2025
# Обновляется автоматически после запуска валидации
BEST_STRATEGIES: Dict[str, StrategyConfig] = {
    
    "BTC": StrategyConfig(
        id="btc_rsi_ema",
        name="RSI(14) < 30 + Price > EMA(21)",
        symbol="BTC",
        direction="LONG",
        conditions=[
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
            {"indicator": "price_vs_ema", "period": 21, "operator": ">", "value": 0},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=65.7,
        win_rate_2025=64.2,
        avg_win_rate=65.0,
        total_trades_per_day=0.9,
        max_signals_per_day=2,
    ),
    
    "ETH": StrategyConfig(
        id="eth_rsi_ema50",
        name="RSI(14) < 35 + Price > EMA(50)",
        symbol="ETH",
        direction="LONG",
        conditions=[
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 35},
            {"indicator": "price_vs_ema", "period": 50, "operator": ">", "value": 0},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=63.4,
        win_rate_2025=62.8,
        avg_win_rate=63.1,
        total_trades_per_day=1.6,
        max_signals_per_day=2,
    ),
    
    "BNB": StrategyConfig(
        id="bnb_rsi_ema_volume",
        name="RSI<30 + Price>EMA50 + Volume Spike",
        symbol="BNB",
        direction="LONG",
        conditions=[
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
            {"indicator": "price_vs_ema", "period": 50, "operator": ">", "value": 0},
            {"indicator": "volume_spike", "multiplier": 1.5, "operator": ">", "value": True},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=74.4,
        win_rate_2025=68.5,
        avg_win_rate=71.5,
        total_trades_per_day=1.2,
        max_signals_per_day=3,
    ),
    
    "SOL": StrategyConfig(
        id="sol_rsi_overbought",
        name="RSI(21) > 80",
        symbol="SOL",
        direction="SHORT",
        conditions=[
            {"indicator": "rsi", "period": 21, "operator": ">", "value": 80},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=66.2,
        win_rate_2025=63.8,
        avg_win_rate=65.0,
        total_trades_per_day=2.1,
        max_signals_per_day=2,
    ),
    
    "XRP": StrategyConfig(
        id="xrp_rsi_overbought",
        name="RSI(14) > 80",
        symbol="XRP",
        direction="SHORT",
        conditions=[
            {"indicator": "rsi", "period": 14, "operator": ">", "value": 80},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=64.1,
        win_rate_2025=62.5,
        avg_win_rate=63.3,
        total_trades_per_day=2.5,
        max_signals_per_day=3,
    ),
    
    "ADA": StrategyConfig(
        id="ada_rsi_ema",
        name="RSI(14) < 30 + Price > EMA(21)",
        symbol="ADA",
        direction="LONG",
        conditions=[
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
            {"indicator": "price_vs_ema", "period": 21, "operator": ">", "value": 0},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=73.2,
        win_rate_2025=67.8,
        avg_win_rate=70.5,
        total_trades_per_day=1.8,
        max_signals_per_day=2,
    ),
    
    "DOGE": StrategyConfig(
        id="doge_stoch_macd",
        name="Stoch(14) < 25 + MACD Cross Up",
        symbol="DOGE",
        direction="LONG",
        conditions=[
            {"indicator": "stoch_k", "period": 14, "operator": "<", "value": 25},
            {"indicator": "macd_cross", "operator": "==", "value": "up"},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=70.0,
        win_rate_2025=65.2,
        avg_win_rate=67.6,
        total_trades_per_day=1.5,
        max_signals_per_day=3,
    ),
    
    "MATIC": StrategyConfig(
        id="matic_rsi_ema50",
        name="RSI(14) < 30 + Price > EMA(50)",
        symbol="MATIC",
        direction="LONG",
        conditions=[
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
            {"indicator": "price_vs_ema", "period": 50, "operator": ">", "value": 0},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=71.5,
        win_rate_2025=66.0,
        avg_win_rate=68.8,
        total_trades_per_day=1.4,
        max_signals_per_day=2,
        enabled=False,  # Нет данных за 2025
    ),
    
    "LINK": StrategyConfig(
        id="link_rsi_ema50",
        name="RSI(14) < 30 + Price > EMA(50)",
        symbol="LINK",
        direction="LONG",
        conditions=[
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
            {"indicator": "price_vs_ema", "period": 50, "operator": ">", "value": 0},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=68.3,
        win_rate_2025=65.1,
        avg_win_rate=66.7,
        total_trades_per_day=2.2,
        max_signals_per_day=2,
    ),
    
    "AVAX": StrategyConfig(
        id="avax_rsi_ema",
        name="RSI(14) < 30 + Price > EMA(21)",
        symbol="AVAX",
        direction="LONG",
        conditions=[
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
            {"indicator": "price_vs_ema", "period": 21, "operator": ">", "value": 0},
        ],
        tp_percent=0.3,
        sl_percent=0.5,
        win_rate_2024=73.7,
        win_rate_2025=68.9,
        avg_win_rate=71.3,
        total_trades_per_day=4.5,
        max_signals_per_day=3,
    ),
}


# Глобальные параметры
GLOBAL_SETTINGS = {
    "default_timeframe": "5m",
    "check_interval_seconds": 60,
    "max_total_signals_per_day": 15,
    "min_win_rate_threshold": 60.0,
    "min_trades_per_day": 1.0,
    "max_trades_per_day": 5.0,
    "trading_hours": {"start": 0, "end": 24},  # 24/7
}


def get_strategy(symbol: str) -> Optional[StrategyConfig]:
    """Получить стратегию для символа"""
    return BEST_STRATEGIES.get(symbol.upper())


def get_all_strategies() -> Dict[str, StrategyConfig]:
    """Получить все стратегии"""
    return BEST_STRATEGIES


def get_enabled_strategies(
    min_trades: float = None,
    max_trades: float = None,
    min_win_rate: float = None
) -> Dict[str, StrategyConfig]:
    """
    Получить только включённые стратегии с фильтрацией
    
    Args:
        min_trades: Минимум trades/day (default из GLOBAL_SETTINGS)
        max_trades: Максимум trades/day (default из GLOBAL_SETTINGS)
        min_win_rate: Минимальный win rate (default из GLOBAL_SETTINGS)
    """
    min_t = min_trades or GLOBAL_SETTINGS.get('min_trades_per_day', 1.0)
    max_t = max_trades or GLOBAL_SETTINGS.get('max_trades_per_day', 5.0)
    min_wr = min_win_rate or GLOBAL_SETTINGS.get('min_win_rate_threshold', 60.0)
    
    result = {}
    for k, v in BEST_STRATEGIES.items():
        if not v.enabled:
            continue
        if v.total_trades_per_day < min_t:
            continue
        if v.total_trades_per_day > max_t:
            continue
        if v.avg_win_rate < min_wr:
            continue
        result[k] = v
    
    return result


def update_strategy_from_validation(symbol: str, wr_2025: float, avg_wr: float):
    """Обновить стратегию после валидации"""
    if symbol in BEST_STRATEGIES:
        BEST_STRATEGIES[symbol].win_rate_2025 = wr_2025
        BEST_STRATEGIES[symbol].avg_win_rate = avg_wr
        BEST_STRATEGIES[symbol].last_updated = datetime.now().isoformat()
