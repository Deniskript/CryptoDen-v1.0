"""
📊 ПОЛНЫЙ БЭКТЕСТ 132 СТРАТЕГИЙ
Период: Январь 2025
Цель: Найти лучшие стратегии для каждого типа рынка
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import sys

# Добавляем путь к проекту
sys.path.insert(0, '/root/crypto-bot')

from app.core.logger import logger


class MarketRegime(Enum):
    """5 типов рынка"""
    SIDEWAYS = "sideways"           # Боковик
    UPTREND = "uptrend"             # Тренд вверх
    DOWNTREND = "downtrend"         # Тренд вниз
    OVERSOLD = "oversold"           # Перепроданность
    OVERBOUGHT = "overbought"       # Перекупленность


@dataclass
class TradeResult:
    """Результат одной сделки"""
    symbol: str
    strategy_id: str
    strategy_name: str
    direction: str
    market_regime: MarketRegime
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    pnl_percent: float
    pnl_usd: float
    won: bool
    hold_hours: float
    exit_reason: str


@dataclass
class StrategyStats:
    """Статистика стратегии"""
    strategy_id: str
    strategy_name: str
    category: str
    
    # Общая статистика
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # PnL
    total_pnl_percent: float = 0.0
    monthly_pnl: float = 0.0
    projected_yearly_pnl: float = 0.0
    
    # Риск
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    # Сигналы
    signals_per_month: float = 0.0
    avg_hold_hours: float = 0.0
    
    # По монетам
    profitable_coins: int = 0
    best_coin: str = ""
    worst_coin: str = ""
    
    # По режимам рынка
    best_regime: str = ""
    regime_stats: Dict = field(default_factory=dict)
    
    # Качество
    max_consecutive_losses: int = 0
    
    @property
    def score(self) -> float:
        """Общий скор стратегии для ранжирования"""
        if self.total_trades < 5:
            return 0
        
        score = 0
        
        # Win Rate (макс 30 баллов)
        if self.win_rate >= 70:
            score += 30
        elif self.win_rate >= 65:
            score += 25
        elif self.win_rate >= 60:
            score += 20
        elif self.win_rate >= 55:
            score += 10
        
        # PnL (макс 30 баллов)
        if self.monthly_pnl >= 10:
            score += 30
        elif self.monthly_pnl >= 7:
            score += 25
        elif self.monthly_pnl >= 5:
            score += 20
        elif self.monthly_pnl >= 3:
            score += 10
        
        # Profit Factor (макс 20 баллов)
        if self.profit_factor >= 2.5:
            score += 20
        elif self.profit_factor >= 2.0:
            score += 15
        elif self.profit_factor >= 1.5:
            score += 10
        
        # Drawdown штраф (макс -20 баллов)
        if self.max_drawdown > 15:
            score -= 20
        elif self.max_drawdown > 10:
            score -= 10
        elif self.max_drawdown > 7:
            score -= 5
        
        # Бонус за количество монет
        score += min(self.profitable_coins * 2, 10)
        
        return score


class MarketClassifier:
    """
    🔍 Классификатор типа рынка
    Работает ЛОКАЛЬНО без AI токенов!
    """
    
    @staticmethod
    def classify(df: pd.DataFrame, idx: int, lookback: int = 24) -> MarketRegime:
        """
        Определить тип рынка на момент idx
        lookback = 24 часа назад
        """
        if idx < lookback + 50:
            return MarketRegime.SIDEWAYS
        
        # Текущие значения
        current = df.iloc[idx]
        
        # RSI
        rsi = current.get('rsi', 50)
        
        # Тренд по EMA
        ema_9 = current.get('ema_9', current['close'])
        ema_21 = current.get('ema_21', current['close'])
        ema_50 = current.get('ema_50', current['close'])
        
        # Изменение цены за период
        window = df.iloc[idx-lookback:idx+1]
        price_change = (current['close'] - window['close'].iloc[0]) / window['close'].iloc[0] * 100
        
        # === КЛАССИФИКАЦИЯ ===
        
        # 1. Экстремумы (приоритет!)
        if rsi < 30:
            return MarketRegime.OVERSOLD
        
        if rsi > 70:
            return MarketRegime.OVERBOUGHT
        
        # 2. Тренды
        if ema_9 > ema_21 > ema_50 and price_change > 2:
            return MarketRegime.UPTREND
        
        if ema_9 < ema_21 < ema_50 and price_change < -2:
            return MarketRegime.DOWNTREND
        
        # 3. Боковик (по умолчанию)
        return MarketRegime.SIDEWAYS
    
    @staticmethod
    def get_regime_for_period(df: pd.DataFrame, start_idx: int, end_idx: int) -> Dict[MarketRegime, float]:
        """Получить распределение режимов за период"""
        regimes = {}
        
        for regime in MarketRegime:
            regimes[regime] = 0
        
        count = 0
        for idx in range(start_idx, min(end_idx, len(df)), 4):  # Каждые 4 часа
            regime = MarketClassifier.classify(df, idx)
            regimes[regime] += 1
            count += 1
        
        # Конвертируем в проценты
        if count > 0:
            for regime in regimes:
                regimes[regime] = regimes[regime] / count * 100
        
        return regimes


class FullStrategyBacktester:
    """
    📊 Полный бэктестер всех 132 стратегий
    """
    
    def __init__(self):
        self.commission = 0.001  # 0.1% Bybit Spot
        self.initial_balance = 1000
        self.position_size_pct = 0.15
        
        # SL/TP параметры
        self.default_sl = 0.015  # 1.5%
        self.default_tp = 0.025  # 2.5%
        self.max_hold_hours = 48
        
        # Результаты
        self.all_trades: List[TradeResult] = []
        self.strategy_stats: Dict[str, StrategyStats] = {}
        
        # Загружаем стратегии
        self.strategies = self._load_strategies()
        
        print(f"📊 Загружено стратегий: {len(self.strategies)}")
    
    def _load_strategies(self) -> Dict:
        """Загрузить все стратегии из библиотеки + встроенные"""
        
        strategies = {}
        
        try:
            from app.backtesting.strategies import StrategyLibrary
            
            library = StrategyLibrary()
            lib_strategies = library.get_all_strategies()
            
            # Конвертируем стратегии из библиотеки в нужный формат
            for strategy in lib_strategies:
                strategy_id = strategy.id
                strategies[strategy_id] = {
                    'name': strategy.name,
                    'category': strategy.category,
                    'direction': strategy.direction,
                    'conditions': strategy.condition,
                    'regime': list(MarketRegime),  # Все режимы по умолчанию
                }
            
            print(f"   ✅ Загружено из библиотеки: {len(strategies)}")
            
        except Exception as e:
            print(f"   ⚠️ Ошибка импорта библиотеки: {e}")
        
        # Добавляем встроенные стратегии
        builtin = self._get_builtin_strategies()
        
        for sid, s in builtin.items():
            if sid not in strategies:
                strategies[sid] = s
        
        print(f"   ✅ + встроенных: {len(builtin)}")
        
        return strategies
    
    def _get_builtin_strategies(self) -> Dict:
        """Встроенные стратегии - гарантированно работают"""
        
        return {
            # === RSI СТРАТЕГИИ (15) ===
            "RSI_25_LONG": {
                "name": "RSI < 25 Extreme",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 25,
                "regime": [MarketRegime.OVERSOLD],
            },
            "RSI_30_LONG": {
                "name": "RSI < 30",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 30,
                "regime": [MarketRegime.OVERSOLD, MarketRegime.SIDEWAYS],
            },
            "RSI_35_LONG": {
                "name": "RSI < 35",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 35,
                "regime": [MarketRegime.OVERSOLD, MarketRegime.SIDEWAYS],
            },
            "RSI_40_LONG": {
                "name": "RSI < 40 Moderate",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 40 and df.iloc[i]['rsi'] > df.iloc[i-1]['rsi'],
                "regime": [MarketRegime.SIDEWAYS],
            },
            "RSI_70_SHORT": {
                "name": "RSI > 70",
                "category": "RSI",
                "direction": "SHORT",
                "conditions": lambda df, i: df.iloc[i]['rsi'] > 70,
                "regime": [MarketRegime.OVERBOUGHT],
            },
            "RSI_75_SHORT": {
                "name": "RSI > 75 Extreme",
                "category": "RSI",
                "direction": "SHORT",
                "conditions": lambda df, i: df.iloc[i]['rsi'] > 75,
                "regime": [MarketRegime.OVERBOUGHT],
            },
            "RSI_REVERSAL_LONG": {
                "name": "RSI Reversal from 30",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i-1]['rsi'] < 30 and df.iloc[i]['rsi'] > 30,
                "regime": [MarketRegime.OVERSOLD],
            },
            "RSI_REVERSAL_SHORT": {
                "name": "RSI Reversal from 70",
                "category": "RSI",
                "direction": "SHORT",
                "conditions": lambda df, i: df.iloc[i-1]['rsi'] > 70 and df.iloc[i]['rsi'] < 70,
                "regime": [MarketRegime.OVERBOUGHT],
            },
            "RSI_EMA_LONG": {
                "name": "RSI < 40 + Price > EMA21",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 40 and df.iloc[i]['close'] > df.iloc[i]['ema_21'],
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERSOLD],
            },
            "RSI_EMA50_LONG": {
                "name": "RSI < 35 + Price > EMA50",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 35 and df.iloc[i]['close'] > df.iloc[i]['ema_50'],
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERSOLD],
            },
            "RSI_MOMENTUM_LONG": {
                "name": "RSI Rising from Low",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['rsi'] < 45 and 
                    df.iloc[i]['rsi'] > df.iloc[i-1]['rsi'] > df.iloc[i-2]['rsi']
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "RSI_DOUBLE_BOTTOM": {
                "name": "RSI Double Bottom",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-10:i]['rsi'].min() < 30 and
                    df.iloc[i]['rsi'] < 35 and
                    df.iloc[i]['rsi'] > df.iloc[i-1]['rsi']
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "RSI_MACD_LONG": {
                "name": "RSI < 40 + MACD Positive",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 40 and df.iloc[i]['macd_hist'] > 0,
                "regime": [MarketRegime.SIDEWAYS],
            },
            "RSI_VOLUME_LONG": {
                "name": "RSI < 35 + Volume Spike",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 35 and df.iloc[i]['volume_ratio'] > 1.5,
                "regime": [MarketRegime.OVERSOLD],
            },
            "RSI_BB_LONG": {
                "name": "RSI < 35 + Price at BB Lower",
                "category": "RSI",
                "direction": "LONG",
                "conditions": lambda df, i: df.iloc[i]['rsi'] < 35 and df.iloc[i]['close'] <= df.iloc[i]['bb_lower'] * 1.01,
                "regime": [MarketRegime.OVERSOLD],
            },
            
            # === EMA СТРАТЕГИИ (12) ===
            "EMA_CROSS_9_21_LONG": {
                "name": "EMA 9/21 Golden Cross",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['ema_9'] <= df.iloc[i-1]['ema_21'] and 
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21']
                ),
                "regime": [MarketRegime.UPTREND, MarketRegime.SIDEWAYS],
            },
            "EMA_CROSS_21_50_LONG": {
                "name": "EMA 21/50 Cross",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['ema_21'] <= df.iloc[i-1]['ema_50'] and 
                    df.iloc[i]['ema_21'] > df.iloc[i]['ema_50']
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "EMA_CROSS_9_21_SHORT": {
                "name": "EMA 9/21 Death Cross",
                "category": "EMA",
                "direction": "SHORT",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['ema_9'] >= df.iloc[i-1]['ema_21'] and 
                    df.iloc[i]['ema_9'] < df.iloc[i]['ema_21']
                ),
                "regime": [MarketRegime.DOWNTREND, MarketRegime.SIDEWAYS],
            },
            "EMA_TRIPLE_LONG": {
                "name": "EMA Triple Align (9>21>50)",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] > df.iloc[i]['ema_50'] and
                    df.iloc[i-1]['ema_9'] <= df.iloc[i-1]['ema_21']
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "EMA_PULLBACK_LONG": {
                "name": "EMA21 Pullback Buy",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_50'] and
                    df.iloc[i-1]['close'] < df.iloc[i-1]['ema_21'] and
                    df.iloc[i]['close'] > df.iloc[i]['ema_21']
                ),
                "regime": [MarketRegime.UPTREND, MarketRegime.SIDEWAYS],
            },
            "EMA_BOUNCE_50_LONG": {
                "name": "EMA50 Bounce",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['low'] <= df.iloc[i]['ema_50'] * 1.005 and
                    df.iloc[i]['close'] > df.iloc[i]['ema_50'] and
                    df.iloc[i]['ema_21'] > df.iloc[i]['ema_50']
                ),
                "regime": [MarketRegime.UPTREND, MarketRegime.SIDEWAYS],
            },
            "EMA_RIBBON_LONG": {
                "name": "EMA Ribbon Expansion",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] > df.iloc[i]['ema_50'] and
                    (df.iloc[i]['ema_9'] - df.iloc[i]['ema_21']) > (df.iloc[i-1]['ema_9'] - df.iloc[i-1]['ema_21'])
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "EMA_SUPPORT_LONG": {
                "name": "Price Reclaim EMA21",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-2]['close'] > df.iloc[i-2]['ema_21'] and
                    df.iloc[i-1]['close'] < df.iloc[i-1]['ema_21'] and
                    df.iloc[i]['close'] > df.iloc[i]['ema_21']
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "EMA_SQUEEZE_LONG": {
                "name": "EMA Squeeze Breakout",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    abs(df.iloc[i-1]['ema_9'] - df.iloc[i-1]['ema_21']) / df.iloc[i-1]['close'] < 0.002 and
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] and
                    df.iloc[i]['close'] > df.iloc[i]['ema_9']
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "EMA_MOMENTUM_LONG": {
                "name": "EMA9 Momentum",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] > df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] and
                    df.iloc[i]['close'] > df.iloc[i]['open'] and
                    df.iloc[i-1]['close'] > df.iloc[i-1]['open']
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "EMA_TREND_CONTINUATION": {
                "name": "EMA Trend Continuation",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] > df.iloc[i]['ema_50'] and
                    df.iloc[i]['close'] > df.iloc[i]['ema_9'] and
                    df.iloc[i]['rsi'] > 50 and df.iloc[i]['rsi'] < 65
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "EMA_PRICE_ACTION": {
                "name": "Price Above All EMAs",
                "category": "EMA",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] > df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] > df.iloc[i]['ema_50'] and
                    df.iloc[i-1]['close'] < df.iloc[i-1]['ema_9'] and
                    df.iloc[i]['close'] > df.iloc[i-1]['high']
                ),
                "regime": [MarketRegime.UPTREND, MarketRegime.SIDEWAYS],
            },
            
            # === BOLLINGER СТРАТЕГИИ (10) ===
            "BB_BOUNCE_LOWER_LONG": {
                "name": "BB Lower Bounce",
                "category": "BOLLINGER",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['close'] <= df.iloc[i-1]['bb_lower'] and 
                    df.iloc[i]['close'] > df.iloc[i]['bb_lower']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERSOLD],
            },
            "BB_BOUNCE_UPPER_SHORT": {
                "name": "BB Upper Bounce",
                "category": "BOLLINGER",
                "direction": "SHORT",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['close'] >= df.iloc[i-1]['bb_upper'] and 
                    df.iloc[i]['close'] < df.iloc[i]['bb_upper']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERBOUGHT],
            },
            "BB_SQUEEZE_LONG": {
                "name": "BB Squeeze Breakout Up",
                "category": "BOLLINGER",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['bb_std'] < df.iloc[i-5:-1]['bb_std'].mean() * 0.8 and
                    df.iloc[i]['close'] > df.iloc[i]['bb_upper']
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "BB_MIDDLE_CROSS_LONG": {
                "name": "BB Middle Cross Up",
                "category": "BOLLINGER",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['close'] < df.iloc[i-1]['bb_mid'] and
                    df.iloc[i]['close'] > df.iloc[i]['bb_mid'] and
                    df.iloc[i]['rsi'] > 45
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "BB_WALK_BAND_LONG": {
                "name": "BB Walk Upper Band",
                "category": "BOLLINGER",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] > df.iloc[i]['bb_upper'] * 0.99 and
                    df.iloc[i-1]['close'] > df.iloc[i-1]['bb_upper'] * 0.99 and
                    df.iloc[i]['rsi'] < 75
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "BB_RSI_COMBO_LONG": {
                "name": "BB Lower + RSI < 35",
                "category": "BOLLINGER",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] <= df.iloc[i]['bb_lower'] * 1.005 and
                    df.iloc[i]['rsi'] < 35
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "BB_EXPANSION_LONG": {
                "name": "BB Expansion Breakout",
                "category": "BOLLINGER",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['bb_std'] > df.iloc[i-1]['bb_std'] * 1.2 and
                    df.iloc[i]['close'] > df.iloc[i]['bb_mid'] and
                    df.iloc[i]['close'] > df.iloc[i-1]['high']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.UPTREND],
            },
            "BB_PERCENT_LOW_LONG": {
                "name": "BB %B < 0.1",
                "category": "BOLLINGER",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    (df.iloc[i]['close'] - df.iloc[i]['bb_lower']) / (df.iloc[i]['bb_upper'] - df.iloc[i]['bb_lower'] + 1e-10) < 0.1
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "BB_MEAN_REVERSION_LONG": {
                "name": "BB Mean Reversion Long",
                "category": "BOLLINGER",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['close'] < df.iloc[i-1]['bb_lower'] and
                    df.iloc[i]['close'] > df.iloc[i]['bb_lower'] and
                    df.iloc[i]['close'] < df.iloc[i]['bb_mid']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERSOLD],
            },
            "BB_MEAN_REVERSION_SHORT": {
                "name": "BB Mean Reversion Short",
                "category": "BOLLINGER",
                "direction": "SHORT",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['close'] > df.iloc[i-1]['bb_upper'] and
                    df.iloc[i]['close'] < df.iloc[i]['bb_upper'] and
                    df.iloc[i]['close'] > df.iloc[i]['bb_mid']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERBOUGHT],
            },
            
            # === MACD СТРАТЕГИИ (10) ===
            "MACD_CROSS_UP_LONG": {
                "name": "MACD Golden Cross",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['macd'] <= df.iloc[i-1]['macd_signal'] and 
                    df.iloc[i]['macd'] > df.iloc[i]['macd_signal']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.UPTREND],
            },
            "MACD_CROSS_DOWN_SHORT": {
                "name": "MACD Death Cross",
                "category": "MACD",
                "direction": "SHORT",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['macd'] >= df.iloc[i-1]['macd_signal'] and 
                    df.iloc[i]['macd'] < df.iloc[i]['macd_signal']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.DOWNTREND],
            },
            "MACD_ZERO_CROSS_LONG": {
                "name": "MACD Cross Zero Up",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['macd'] <= 0 and 
                    df.iloc[i]['macd'] > 0
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.UPTREND],
            },
            "MACD_HISTOGRAM_REVERSAL_LONG": {
                "name": "MACD Histogram Reversal Up",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-2]['macd_hist'] < df.iloc[i-1]['macd_hist'] < 0 and
                    df.iloc[i]['macd_hist'] > df.iloc[i-1]['macd_hist']
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "MACD_DIVERGENCE_LONG": {
                "name": "MACD Bullish Divergence",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] < df.iloc[i-10:i]['close'].min() * 1.01 and
                    df.iloc[i]['macd'] > df.iloc[i-10:i]['macd'].min() and
                    df.iloc[i]['rsi'] < 40
                ),
                "regime": [MarketRegime.OVERSOLD, MarketRegime.SIDEWAYS],
            },
            "MACD_MOMENTUM_LONG": {
                "name": "MACD Momentum Increasing",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['macd_hist'] > 0 and
                    df.iloc[i]['macd_hist'] > df.iloc[i-1]['macd_hist'] > df.iloc[i-2]['macd_hist']
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "MACD_BELOW_ZERO_CROSS_LONG": {
                "name": "MACD Cross Below Zero",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['macd'] <= df.iloc[i-1]['macd_signal'] and 
                    df.iloc[i]['macd'] > df.iloc[i]['macd_signal'] and
                    df.iloc[i]['macd'] < 0
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERSOLD],
            },
            "MACD_RSI_COMBO_LONG": {
                "name": "MACD Cross + RSI < 45",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['macd'] <= df.iloc[i-1]['macd_signal'] and 
                    df.iloc[i]['macd'] > df.iloc[i]['macd_signal'] and
                    df.iloc[i]['rsi'] < 45
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "MACD_EMA_COMBO_LONG": {
                "name": "MACD Cross + Price > EMA21",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['macd'] <= df.iloc[i-1]['macd_signal'] and 
                    df.iloc[i]['macd'] > df.iloc[i]['macd_signal'] and
                    df.iloc[i]['close'] > df.iloc[i]['ema_21']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.UPTREND],
            },
            "MACD_STRONG_MOMENTUM_LONG": {
                "name": "MACD Strong Momentum",
                "category": "MACD",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['macd'] > 0 and
                    df.iloc[i]['macd_signal'] > 0 and
                    df.iloc[i]['macd_hist'] > df.iloc[i-1]['macd_hist'] * 1.5
                ),
                "regime": [MarketRegime.UPTREND],
            },
            
            # === STOCHASTIC СТРАТЕГИИ (10) ===
            "STOCH_OVERSOLD_LONG": {
                "name": "Stoch Oversold Cross",
                "category": "STOCHASTIC",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['stoch_k'] < 25 and 
                    df.iloc[i]['stoch_k'] > df.iloc[i]['stoch_d'] and
                    df.iloc[i-1]['stoch_k'] <= df.iloc[i-1]['stoch_d']
                ),
                "regime": [MarketRegime.OVERSOLD, MarketRegime.SIDEWAYS],
            },
            "STOCH_OVERBOUGHT_SHORT": {
                "name": "Stoch Overbought Cross",
                "category": "STOCHASTIC",
                "direction": "SHORT",
                "conditions": lambda df, i: (
                    df.iloc[i]['stoch_k'] > 75 and 
                    df.iloc[i]['stoch_k'] < df.iloc[i]['stoch_d'] and
                    df.iloc[i-1]['stoch_k'] >= df.iloc[i-1]['stoch_d']
                ),
                "regime": [MarketRegime.OVERBOUGHT, MarketRegime.SIDEWAYS],
            },
            "STOCH_20_LONG": {
                "name": "Stoch < 20 Extreme",
                "category": "STOCHASTIC",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['stoch_k'] < 20 and
                    df.iloc[i]['stoch_k'] > df.iloc[i-1]['stoch_k']
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "STOCH_80_SHORT": {
                "name": "Stoch > 80 Extreme",
                "category": "STOCHASTIC",
                "direction": "SHORT",
                "conditions": lambda df, i: (
                    df.iloc[i]['stoch_k'] > 80 and
                    df.iloc[i]['stoch_k'] < df.iloc[i-1]['stoch_k']
                ),
                "regime": [MarketRegime.OVERBOUGHT],
            },
            "STOCH_REVERSAL_LONG": {
                "name": "Stoch Reversal from 20",
                "category": "STOCHASTIC",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['stoch_k'] < 20 and
                    df.iloc[i]['stoch_k'] > 20
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "STOCH_RSI_COMBO_LONG": {
                "name": "Stoch < 30 + RSI < 40",
                "category": "STOCHASTIC",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['stoch_k'] < 30 and
                    df.iloc[i]['rsi'] < 40
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "STOCH_EMA_COMBO_LONG": {
                "name": "Stoch Cross + Price > EMA21",
                "category": "STOCHASTIC",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['stoch_k'] < 30 and
                    df.iloc[i]['stoch_k'] > df.iloc[i]['stoch_d'] and
                    df.iloc[i]['close'] > df.iloc[i]['ema_21']
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "STOCH_MOMENTUM_LONG": {
                "name": "Stoch Rising Momentum",
                "category": "STOCHASTIC",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['stoch_k'] > df.iloc[i-1]['stoch_k'] > df.iloc[i-2]['stoch_k'] and
                    df.iloc[i]['stoch_k'] < 50 and
                    df.iloc[i]['stoch_k'] > df.iloc[i]['stoch_d']
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "STOCH_DOUBLE_BOTTOM_LONG": {
                "name": "Stoch Double Bottom",
                "category": "STOCHASTIC",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-10:i]['stoch_k'].min() < 20 and
                    df.iloc[i]['stoch_k'] < 30 and
                    df.iloc[i]['stoch_k'] > df.iloc[i-1]['stoch_k']
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "STOCH_MACD_COMBO_LONG": {
                "name": "Stoch + MACD Combo",
                "category": "STOCHASTIC",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['stoch_k'] < 35 and
                    df.iloc[i]['stoch_k'] > df.iloc[i]['stoch_d'] and
                    df.iloc[i]['macd_hist'] > df.iloc[i-1]['macd_hist']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERSOLD],
            },
            
            # === КОМБИНИРОВАННЫЕ СТРАТЕГИИ (15) ===
            "TRIPLE_CONFIRM_LONG": {
                "name": "Triple Confirmation",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    35 < df.iloc[i]['rsi'] < 55 and
                    df.iloc[i]['macd_hist'] > 0 and
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] and
                    df.iloc[i]['close'] > df.iloc[i]['ema_50']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.UPTREND],
            },
            "PULLBACK_BUY_LONG": {
                "name": "Pullback in Uptrend",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] > df.iloc[i]['ema_50'] and
                    df.iloc[i]['rsi'] < 45 and df.iloc[i]['rsi'] > 30 and
                    df.iloc[i]['close'] > df.iloc[i]['ema_21'] and
                    df.iloc[i]['close'] < df.iloc[i]['ema_9']
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "BREAKOUT_VOLUME_LONG": {
                "name": "Breakout with Volume",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] > df.iloc[i]['bb_upper'] and
                    df.iloc[i]['volume_ratio'] > 1.5 and
                    df.iloc[i]['rsi'] < 75
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "OVERSOLD_BOUNCE_LONG": {
                "name": "Oversold Bounce Combo",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['rsi'] < 35 and
                    df.iloc[i]['stoch_k'] < 25 and
                    df.iloc[i]['close'] <= df.iloc[i]['bb_lower'] * 1.01
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "TREND_STRENGTH_LONG": {
                "name": "Strong Trend Confirmation",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] > df.iloc[i]['ema_50'] and
                    df.iloc[i]['macd'] > 0 and
                    df.iloc[i]['rsi'] > 50 and df.iloc[i]['rsi'] < 70 and
                    df.iloc[i]['close'] > df.iloc[i]['ema_9']
                ),
                "regime": [MarketRegime.UPTREND],
            },
            "REVERSAL_COMBO_LONG": {
                "name": "Reversal Multi-Indicator",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['rsi'] < 35 and
                    df.iloc[i-1]['macd'] < df.iloc[i-1]['macd_signal'] and
                    df.iloc[i]['macd'] > df.iloc[i]['macd_signal'] and
                    df.iloc[i]['close'] > df.iloc[i]['bb_lower']
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "MOMENTUM_BREAKOUT_LONG": {
                "name": "Momentum Breakout",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] > df.iloc[i-1]['high'] and
                    df.iloc[i]['rsi'] > 55 and df.iloc[i]['rsi'] < 70 and
                    df.iloc[i]['macd_hist'] > 0 and
                    df.iloc[i]['volume_ratio'] > 1.3
                ),
                "regime": [MarketRegime.UPTREND, MarketRegime.SIDEWAYS],
            },
            "SUPPORT_BOUNCE_LONG": {
                "name": "Support Bounce",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] > df.iloc[i]['ema_50'] and
                    df.iloc[i-1]['low'] < df.iloc[i-1]['ema_50'] and
                    df.iloc[i]['rsi'] > df.iloc[i-1]['rsi'] and
                    df.iloc[i]['rsi'] < 50
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "DIVERGENCE_ENTRY_LONG": {
                "name": "RSI Divergence Entry",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] < df.iloc[i-5:i]['close'].min() * 1.005 and
                    df.iloc[i]['rsi'] > df.iloc[i-5:i]['rsi'].min() + 5 and
                    df.iloc[i]['rsi'] < 40
                ),
                "regime": [MarketRegime.OVERSOLD, MarketRegime.SIDEWAYS],
            },
            "SQUEEZE_MOMENTUM_LONG": {
                "name": "Squeeze Momentum",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['bb_std'] < df.iloc[i-10:i]['bb_std'].mean() * 0.8 and
                    df.iloc[i]['macd_hist'] > df.iloc[i-1]['macd_hist'] > 0 and
                    df.iloc[i]['close'] > df.iloc[i]['ema_21']
                ),
                "regime": [MarketRegime.SIDEWAYS],
            },
            "SWING_LOW_LONG": {
                "name": "Swing Low Entry",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['low'] == df.iloc[i-5:i+1]['low'].min() and
                    df.iloc[i]['close'] > df.iloc[i-1]['high'] and
                    df.iloc[i]['rsi'] < 45
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERSOLD],
            },
            "CANDLE_PATTERN_LONG": {
                "name": "Bullish Engulfing + RSI",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['close'] < df.iloc[i-1]['open'] and
                    df.iloc[i]['close'] > df.iloc[i]['open'] and
                    df.iloc[i]['close'] > df.iloc[i-1]['open'] and
                    df.iloc[i]['open'] < df.iloc[i-1]['close'] and
                    df.iloc[i]['rsi'] < 50
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.OVERSOLD],
            },
            "VOLUME_CLIMAX_LONG": {
                "name": "Volume Climax Reversal",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i-1]['volume_ratio'] > 2.0 and
                    df.iloc[i-1]['close'] < df.iloc[i-1]['open'] and
                    df.iloc[i]['close'] > df.iloc[i]['open'] and
                    df.iloc[i]['rsi'] < 40
                ),
                "regime": [MarketRegime.OVERSOLD],
            },
            "MULTI_TIMEFRAME_LONG": {
                "name": "Multi-TF Alignment",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['close'] > df.iloc[i]['ema_50'] and
                    df.iloc[i]['close'] > df.iloc[i]['ema_100'] and
                    df.iloc[i]['rsi'] > 45 and df.iloc[i]['rsi'] < 65 and
                    df.iloc[i]['macd'] > df.iloc[i]['macd_signal']
                ),
                "regime": [MarketRegime.UPTREND, MarketRegime.SIDEWAYS],
            },
            "CONSERVATIVE_ENTRY_LONG": {
                "name": "Conservative Multi-Filter",
                "category": "COMBINED",
                "direction": "LONG",
                "conditions": lambda df, i: (
                    df.iloc[i]['rsi'] > 40 and df.iloc[i]['rsi'] < 60 and
                    df.iloc[i]['macd'] > df.iloc[i]['macd_signal'] and
                    df.iloc[i]['ema_9'] > df.iloc[i]['ema_21'] and
                    df.iloc[i]['close'] > df.iloc[i]['bb_mid'] and
                    df.iloc[i]['stoch_k'] > df.iloc[i]['stoch_d']
                ),
                "regime": [MarketRegime.SIDEWAYS, MarketRegime.UPTREND],
            },
        }
    
    async def load_data(self, symbol: str) -> pd.DataFrame:
        """Загрузить данные за январь 2025"""
        
        try:
            from app.trading.bybit.client import bybit_client
            
            print(f"   📥 Загружаю {symbol}...")
            
            all_klines = []
            start_date = datetime(2025, 1, 1)
            end_date = datetime.now()
            
            current_end = int(end_date.timestamp() * 1000)
            start_ts = int(start_date.timestamp() * 1000)
            
            while current_end > start_ts:
                try:
                    # Используем публичный метод для получения свечей
                    url = "https://api.bybit.com/v5/market/kline"
                    params = {
                        "category": "spot",
                        "symbol": f"{symbol}USDT",
                        "interval": "60",
                        "limit": 1000,
                        "end": current_end
                    }
                    
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, params=params) as resp:
                            data = await resp.json()
                            
                            if data.get('retCode') != 0:
                                break
                            
                            klines = data.get('result', {}).get('list', [])
                            
                            if not klines:
                                break
                            
                            all_klines = klines + all_klines
                            current_end = int(klines[-1][0]) - 1
                            
                except Exception as e:
                    print(f"      ⚠️ Ошибка загрузки: {e}")
                    break
                
                await asyncio.sleep(0.05)
            
            if not all_klines:
                return pd.DataFrame()
            
            df = pd.DataFrame(all_klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
            df = df.sort_values('timestamp').reset_index(drop=True)
            df = df[df['timestamp'] >= start_date]
            df = df.dropna()
            
            print(f"   ✅ {symbol}: {len(df)} свечей")
            return df
            
        except Exception as e:
            print(f"   ❌ {symbol}: {e}")
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Рассчитать все индикаторы"""
        
        df = df.copy()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Stochastic
        low_14 = df['low'].rolling(14).min()
        high_14 = df['high'].rolling(14).max()
        df['stoch_k'] = ((df['close'] - low_14) / (high_14 - low_14 + 1e-10)) * 100
        df['stoch_d'] = df['stoch_k'].rolling(3).mean()
        
        # EMA
        for period in [9, 21, 50, 100, 200]:
            df[f'ema_{period}'] = df['close'].ewm(span=period).mean()
        
        # MACD
        ema_12 = df['close'].ewm(span=12).mean()
        ema_26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # Bollinger
        df['bb_mid'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        
        # Volume
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / (df['volume_sma'] + 1e-10)
        
        return df
    
    def check_strategy_signal(self, df: pd.DataFrame, idx: int, strategy: Dict) -> Optional[str]:
        """Проверить сигнал стратегии"""
        
        try:
            conditions_func = strategy.get('conditions')
            if conditions_func and conditions_func(df, idx):
                return strategy.get('direction', 'LONG')
        except Exception:
            pass
        
        return None
    
    def simulate_trade(
        self, 
        df: pd.DataFrame, 
        entry_idx: int, 
        direction: str,
        strategy_id: str,
        strategy_name: str,
        regime: MarketRegime,
        symbol: str
    ) -> Optional[TradeResult]:
        """Симуляция сделки"""
        
        entry_row = df.iloc[entry_idx]
        entry_price = entry_row['close']
        entry_time = entry_row['timestamp']
        
        # Динамические SL/TP на основе ATR
        atr_pct = entry_row.get('atr_pct', 2.0) / 100
        
        if direction == "LONG":
            sl_pct = max(self.default_sl, atr_pct * 0.8)
            tp_pct = max(self.default_tp, atr_pct * 1.5)
            stop_loss = entry_price * (1 - sl_pct)
            take_profit = entry_price * (1 + tp_pct)
        else:
            sl_pct = max(self.default_sl, atr_pct * 0.8)
            tp_pct = max(self.default_tp, atr_pct * 1.5)
            stop_loss = entry_price * (1 + sl_pct)
            take_profit = entry_price * (1 - tp_pct)
        
        # Проходим по свечам
        for i in range(entry_idx + 1, min(entry_idx + self.max_hold_hours, len(df))):
            row = df.iloc[i]
            high = row['high']
            low = row['low']
            
            exit_price = None
            exit_reason = ""
            
            if direction == "LONG":
                if low <= stop_loss:
                    exit_price = stop_loss
                    exit_reason = "SL"
                elif high >= take_profit:
                    exit_price = take_profit
                    exit_reason = "TP"
            else:
                if high >= stop_loss:
                    exit_price = stop_loss
                    exit_reason = "SL"
                elif low <= take_profit:
                    exit_price = take_profit
                    exit_reason = "TP"
            
            if exit_price:
                if direction == "LONG":
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100
                
                pnl_pct -= self.commission * 100 * 2
                hold_hours = (row['timestamp'] - entry_time).total_seconds() / 3600
                
                return TradeResult(
                    symbol=symbol,
                    strategy_id=strategy_id,
                    strategy_name=strategy_name,
                    direction=direction,
                    market_regime=regime,
                    entry_time=entry_time,
                    entry_price=entry_price,
                    exit_time=row['timestamp'],
                    exit_price=exit_price,
                    pnl_percent=pnl_pct,
                    pnl_usd=self.initial_balance * self.position_size_pct * (pnl_pct / 100),
                    won=pnl_pct > 0,
                    hold_hours=hold_hours,
                    exit_reason=exit_reason
                )
        
        # Выход по времени
        if entry_idx + self.max_hold_hours < len(df):
            exit_row = df.iloc[entry_idx + self.max_hold_hours]
            exit_price = exit_row['close']
            
            if direction == "LONG":
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - exit_price) / entry_price) * 100
            
            pnl_pct -= self.commission * 100 * 2
            
            return TradeResult(
                symbol=symbol,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                direction=direction,
                market_regime=regime,
                entry_time=entry_time,
                entry_price=entry_price,
                exit_time=exit_row['timestamp'],
                exit_price=exit_price,
                pnl_percent=pnl_pct,
                pnl_usd=self.initial_balance * self.position_size_pct * (pnl_pct / 100),
                won=pnl_pct > 0,
                hold_hours=self.max_hold_hours,
                exit_reason="TIME"
            )
        
        return None
    
    async def backtest_strategy_on_symbol(
        self, 
        df: pd.DataFrame, 
        strategy_id: str, 
        strategy: Dict,
        symbol: str
    ) -> List[TradeResult]:
        """Бэктест одной стратегии на одной монете"""
        
        trades = []
        last_trade_idx = 0
        min_bars_between = 6  # Минимум 6 часов между сделками
        
        for i in range(50, len(df)):
            if i - last_trade_idx < min_bars_between:
                continue
            
            # Определяем режим рынка
            regime = MarketClassifier.classify(df, i)
            
            # Проверяем подходит ли стратегия для этого режима
            allowed_regimes = strategy.get('regime', list(MarketRegime))
            if regime not in allowed_regimes:
                continue
            
            # Проверяем сигнал
            signal = self.check_strategy_signal(df, i, strategy)
            
            if signal:
                trade = self.simulate_trade(
                    df, i, signal, 
                    strategy_id, 
                    strategy.get('name', strategy_id),
                    regime,
                    symbol
                )
                if trade:
                    trades.append(trade)
                    last_trade_idx = i
        
        return trades
    
    def calculate_strategy_stats(self, strategy_id: str, strategy: Dict, all_trades: List[TradeResult]) -> StrategyStats:
        """Рассчитать статистику стратегии"""
        
        stats = StrategyStats(
            strategy_id=strategy_id,
            strategy_name=strategy.get('name', strategy_id),
            category=strategy.get('category', 'UNKNOWN')
        )
        
        if not all_trades:
            return stats
        
        stats.total_trades = len(all_trades)
        stats.winning_trades = sum(1 for t in all_trades if t.won)
        stats.losing_trades = stats.total_trades - stats.winning_trades
        stats.win_rate = stats.winning_trades / stats.total_trades * 100
        
        # PnL
        stats.total_pnl_percent = sum(t.pnl_percent for t in all_trades)
        
        # Месячный и годовой PnL
        if len(all_trades) >= 2:
            days = (all_trades[-1].exit_time - all_trades[0].entry_time).days
            if days > 0:
                stats.monthly_pnl = stats.total_pnl_percent / days * 30
                stats.projected_yearly_pnl = stats.total_pnl_percent / days * 365
            else:
                stats.monthly_pnl = stats.total_pnl_percent
                stats.projected_yearly_pnl = stats.total_pnl_percent * 12
        else:
            stats.monthly_pnl = stats.total_pnl_percent
            stats.projected_yearly_pnl = stats.total_pnl_percent * 12
        
        stats.signals_per_month = stats.total_trades
        
        # Avg win/loss
        winning = [t.pnl_percent for t in all_trades if t.won]
        losing = [abs(t.pnl_percent) for t in all_trades if not t.won]
        
        stats.avg_win = np.mean(winning) if winning else 0
        stats.avg_loss = np.mean(losing) if losing else 0
        
        # Profit Factor
        gross_profit = sum(winning) if winning else 0
        gross_loss = sum(losing) if losing else 1
        stats.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Max Drawdown
        cumulative = 0
        peak = 0
        max_dd = 0
        for t in all_trades:
            cumulative += t.pnl_percent
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        stats.max_drawdown = max_dd
        
        # Avg hold time
        stats.avg_hold_hours = np.mean([t.hold_hours for t in all_trades])
        
        # По монетам
        coins = {}
        for t in all_trades:
            if t.symbol not in coins:
                coins[t.symbol] = 0
            coins[t.symbol] += t.pnl_percent
        
        stats.profitable_coins = sum(1 for pnl in coins.values() if pnl > 0)
        if coins:
            stats.best_coin = max(coins.items(), key=lambda x: x[1])[0]
            stats.worst_coin = min(coins.items(), key=lambda x: x[1])[0]
        
        # По режимам
        regimes = {}
        for t in all_trades:
            regime = t.market_regime.value
            if regime not in regimes:
                regimes[regime] = {'trades': 0, 'pnl': 0, 'wins': 0}
            regimes[regime]['trades'] += 1
            regimes[regime]['pnl'] += t.pnl_percent
            if t.won:
                regimes[regime]['wins'] += 1
        
        stats.regime_stats = regimes
        if regimes:
            stats.best_regime = max(regimes.items(), key=lambda x: x[1]['pnl'])[0]
        
        # Max consecutive losses
        consecutive = 0
        max_consecutive = 0
        for t in all_trades:
            if not t.won:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0
        stats.max_consecutive_losses = max_consecutive
        
        return stats
    
    async def run_full_backtest(self, symbols: List[str] = None):
        """Запустить полный бэктест"""
        
        if symbols is None:
            symbols = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "BNB"]
        
        print("=" * 80)
        print("📊 ПОЛНЫЙ БЭКТЕСТ СТРАТЕГИЙ")
        print("=" * 80)
        print(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 Период: Январь 2025")
        print(f"💰 Депозит: ${self.initial_balance}")
        print(f"🪙 Монеты: {', '.join(symbols)}")
        print(f"📈 Стратегий: {len(self.strategies)}")
        print("=" * 80)
        
        # Загружаем данные
        print("\n📥 Загрузка данных...")
        data = {}
        for symbol in symbols:
            df = await self.load_data(symbol)
            if not df.empty:
                data[symbol] = self.calculate_indicators(df)
        
        print(f"\n✅ Загружено данных: {len(data)} монет")
        
        # Тестируем каждую стратегию
        print("\n📊 Тестирование стратегий...")
        all_strategy_results = {}
        
        total = len(self.strategies)
        count = 0
        
        for strategy_id, strategy in self.strategies.items():
            count += 1
            strategy_trades = []
            
            for symbol, df in data.items():
                trades = await self.backtest_strategy_on_symbol(df, strategy_id, strategy, symbol)
                strategy_trades.extend(trades)
            
            if strategy_trades:
                stats = self.calculate_strategy_stats(strategy_id, strategy, strategy_trades)
                all_strategy_results[strategy_id] = stats
                self.all_trades.extend(strategy_trades)
            
            if count % 20 == 0:
                print(f"   ... обработано {count}/{total} стратегий")
        
        print(f"\n✅ Обработано стратегий: {total}")
        
        # Выводим результаты
        self._print_results(all_strategy_results)
        
        # Сохраняем
        self._save_results(all_strategy_results)
        
        return all_strategy_results
    
    def _print_results(self, results: Dict[str, StrategyStats]):
        """Вывод результатов"""
        
        print("\n" + "=" * 80)
        print("📋 РЕЗУЛЬТАТЫ БЭКТЕСТА")
        print("=" * 80)
        
        # Сортируем по скору
        sorted_results = sorted(
            results.values(), 
            key=lambda x: x.score, 
            reverse=True
        )
        
        # Фильтруем по критериям
        excellent = [s for s in sorted_results if s.win_rate >= 60 and s.monthly_pnl >= 5 and s.profit_factor >= 1.5 and s.total_trades >= 5]
        good = [s for s in sorted_results if s.win_rate >= 55 and s.monthly_pnl >= 3 and s.total_trades >= 5 and s not in excellent]
        
        print(f"\n🏆 ОТЛИЧНЫЕ СТРАТЕГИИ ({len(excellent)} шт):")
        print(f"   (WR >= 60%, PnL/мес >= 5%, PF >= 1.5, Trades >= 5)")
        print("-" * 80)
        
        if excellent:
            print(f"{'Стратегия':<35} | {'WR':>5} | {'PnL/мес':>8} | {'PF':>5} | {'DD':>5} | {'Sig':>4} | {'Score':>5}")
            print("-" * 80)
            
            for s in excellent[:15]:
                emoji = "🥇" if s.score >= 70 else "🥈" if s.score >= 60 else "🥉"
                print(f"{emoji} {s.strategy_name[:33]:<33} | "
                      f"{s.win_rate:>4.1f}% | "
                      f"{s.monthly_pnl:>+7.1f}% | "
                      f"{s.profit_factor:>5.2f} | "
                      f"{s.max_drawdown:>4.1f}% | "
                      f"{s.signals_per_month:>4.0f} | "
                      f"{s.score:>5.0f}")
        else:
            print("   Нет стратегий, соответствующих критериям")
        
        print(f"\n👍 ХОРОШИЕ СТРАТЕГИИ ({len(good)} шт):")
        print(f"   (WR >= 55%, PnL/мес >= 3%, Trades >= 5)")
        print("-" * 80)
        
        if good:
            for s in good[:10]:
                print(f"   • {s.strategy_name[:40]:<40} | "
                      f"WR: {s.win_rate:>4.1f}% | "
                      f"PnL: {s.monthly_pnl:>+5.1f}%/мес | "
                      f"Trades: {s.total_trades}")
        
        # Группировка по категориям
        print("\n" + "=" * 80)
        print("📊 ЛУЧШИЕ ПО КАТЕГОРИЯМ:")
        print("=" * 80)
        
        categories = {}
        for s in sorted_results:
            cat = s.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(s)
        
        for cat, strategies in categories.items():
            best = [s for s in strategies if s.win_rate >= 55 and s.monthly_pnl > 0 and s.total_trades >= 3][:3]
            if best:
                print(f"\n📁 {cat}:")
                for s in best:
                    print(f"   ✅ {s.strategy_name[:35]:<35} | WR: {s.win_rate:.1f}% | PnL: {s.monthly_pnl:+.1f}%/мес | Trades: {s.total_trades}")
        
        # Лучшие по режимам рынка
        print("\n" + "=" * 80)
        print("🎯 ЛУЧШИЕ ПО ТИПУ РЫНКА:")
        print("=" * 80)
        
        for regime in MarketRegime:
            regime_strategies = []
            for s in sorted_results:
                if regime.value in s.regime_stats:
                    regime_data = s.regime_stats[regime.value]
                    if regime_data['trades'] >= 3:
                        wr = regime_data['wins'] / regime_data['trades'] * 100
                        if wr >= 55:
                            regime_strategies.append((s, wr, regime_data['pnl'], regime_data['trades']))
            
            regime_strategies.sort(key=lambda x: (x[1], x[2]), reverse=True)
            
            print(f"\n🔹 {regime.value.upper()}:")
            for s, wr, pnl, trades in regime_strategies[:3]:
                print(f"   ✅ {s.strategy_name[:35]:<35} | WR: {wr:.1f}% | PnL: {pnl:+.1f}% | Trades: {trades}")
        
        # Финальные рекомендации
        print("\n" + "=" * 80)
        print("💡 РЕКОМЕНДАЦИИ К ДОБАВЛЕНИЮ:")
        print("=" * 80)
        
        to_add = excellent[:10]
        
        if to_add:
            total_signals = sum(s.signals_per_month for s in to_add)
            avg_pnl = np.mean([s.monthly_pnl for s in to_add])
            
            print(f"\n📈 Добавить {len(to_add)} стратегий:")
            for s in to_add:
                print(f"   ✅ {s.strategy_id}: {s.strategy_name}")
            
            print(f"\n📊 Ожидаемый результат:")
            print(f"   • Сигналов в месяц: ~{total_signals:.0f}")
            print(f"   • Средний PnL: ~{avg_pnl:.1f}%/месяц")
            print(f"   • Годовой PnL: ~{avg_pnl * 12:.0f}%")
        else:
            print("\n⚠️ Нет стратегий, соответствующих критериям.")
            print("   Рекомендуем пересмотреть параметры SL/TP или критерии отбора.")
        
        print("\n" + "=" * 80)
        print(f"⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
    
    def _save_results(self, results: Dict[str, StrategyStats]):
        """Сохранить результаты"""
        
        output = {
            'timestamp': datetime.now().isoformat(),
            'period': 'January 2025',
            'total_strategies_tested': len(self.strategies),
            'strategies_with_trades': len(results),
            'excellent_strategies': [],
            'good_strategies': [],
            'all_strategies': {}
        }
        
        sorted_results = sorted(results.values(), key=lambda x: x.score, reverse=True)
        
        for stats in sorted_results:
            strategy_data = {
                'id': stats.strategy_id,
                'name': stats.strategy_name,
                'category': stats.category,
                'total_trades': stats.total_trades,
                'win_rate': round(stats.win_rate, 2),
                'monthly_pnl': round(stats.monthly_pnl, 2),
                'yearly_pnl': round(stats.projected_yearly_pnl, 2),
                'profit_factor': round(stats.profit_factor, 2),
                'max_drawdown': round(stats.max_drawdown, 2),
                'signals_per_month': round(stats.signals_per_month, 2),
                'score': round(stats.score, 2),
                'profitable_coins': stats.profitable_coins,
                'best_coin': stats.best_coin,
                'best_regime': stats.best_regime,
                'avg_win': round(stats.avg_win, 2),
                'avg_loss': round(stats.avg_loss, 2),
                'max_consecutive_losses': stats.max_consecutive_losses,
            }
            
            output['all_strategies'][stats.strategy_id] = strategy_data
            
            if stats.win_rate >= 60 and stats.monthly_pnl >= 5 and stats.profit_factor >= 1.5 and stats.total_trades >= 5:
                output['excellent_strategies'].append(strategy_data)
            elif stats.win_rate >= 55 and stats.monthly_pnl >= 3 and stats.total_trades >= 5:
                output['good_strategies'].append(strategy_data)
        
        os.makedirs('reports', exist_ok=True)
        filename = f"reports/full_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n💾 Результаты сохранены: {filename}")
        
        return filename


async def main():
    """Запуск бэктеста"""
    backtester = FullStrategyBacktester()
    results = await backtester.run_full_backtest()
    return results


if __name__ == "__main__":
    asyncio.run(main())
