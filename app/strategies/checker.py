"""
Strategy Checker — Проверка условий стратегий в реальном времени
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

import pandas as pd
import numpy as np

from app.strategies.config import (
    StrategyConfig, 
    get_strategy,
    get_short_strategy,
    get_enabled_strategies,
    get_strategies_summary,
    GLOBAL_SETTINGS
)
from app.strategies.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Торговый сигнал"""
    symbol: str
    direction: str  # LONG, SHORT
    strategy_id: str
    strategy_name: str
    
    # Цены
    entry_price: float
    stop_loss: float
    take_profit: float
    
    # Индикаторы на момент сигнала
    indicators: Dict[str, float]
    conditions_met: List[str]
    
    # Статистика
    win_rate: float
    confidence: float  # 0-1
    
    # Время
    timestamp: datetime
    expires_at: datetime  # Сигнал истекает через N минут
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'strategy': self.strategy_name,
            'entry': self.entry_price,
            'sl': self.stop_loss,
            'tp': self.take_profit,
            'win_rate': self.win_rate,
            'confidence': self.confidence,
            'conditions': self.conditions_met,
            'timestamp': self.timestamp.isoformat(),
        }


class StrategyChecker:
    """
    Проверка стратегий в реальном времени
    
    Функции:
    - Проверка условий для каждой монеты
    - Генерация сигналов
    - Контроль частоты сигналов
    """
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
        self.last_signals: Dict[str, datetime] = {}  # symbol -> last signal time
        self.signals_today: Dict[str, int] = {}  # symbol -> count today
        self.last_reset_date: datetime = datetime.utcnow().date()
        
        logger.info("StrategyChecker initialized")
    
    def _reset_daily_counters(self):
        """Сброс дневных счётчиков"""
        today = datetime.utcnow().date()
        if today > self.last_reset_date:
            self.signals_today = {}
            self.last_reset_date = today
            logger.info("Daily counters reset")
    
    def _can_generate_signal(self, symbol: str, strategy: StrategyConfig) -> tuple:
        """Проверить можно ли генерировать сигнал"""
        
        self._reset_daily_counters()
        
        # Проверка дневного лимита для символа
        today_count = self.signals_today.get(symbol, 0)
        if today_count >= strategy.max_signals_per_day:
            return False, f"Daily limit reached ({strategy.max_signals_per_day})"
        
        # Проверка общего лимита
        total_today = sum(self.signals_today.values())
        max_total = GLOBAL_SETTINGS.get('max_total_signals_per_day', 15)
        if total_today >= max_total:
            return False, f"Total daily limit reached ({max_total})"
        
        # Проверка минимального интервала
        if symbol in self.last_signals:
            last_time = self.last_signals[symbol]
            min_interval = timedelta(minutes=strategy.min_time_between_signals_minutes)
            if datetime.utcnow() - last_time < min_interval:
                remaining = min_interval - (datetime.utcnow() - last_time)
                return False, f"Cooldown: {remaining.seconds // 60}m remaining"
        
        return True, "OK"
    
    def _check_condition(
        self, 
        condition: Dict[str, Any], 
        df: pd.DataFrame,
        current_price: float
    ) -> tuple:
        """Проверить одно условие"""
        
        indicator = condition.get('indicator')
        operator = condition.get('operator')
        value = condition.get('value')
        
        actual_value = None
        description = ""
        
        try:
            # RSI
            if indicator == 'rsi':
                period = condition.get('period', 14)
                actual_value = self.indicators.rsi(df['close'], period)
                description = f"RSI({period})={actual_value:.1f}"
            
            # Stochastic K
            elif indicator == 'stoch_k':
                period = condition.get('period', 14)
                actual_value = self.indicators.stochastic_k(df, period)
                description = f"Stoch({period})={actual_value:.1f}"
            
            # Price vs EMA
            elif indicator == 'price_vs_ema':
                period = condition.get('period', 50)
                ema = self.indicators.ema(df['close'], period)
                actual_value = current_price - ema
                description = f"Price vs EMA({period})={actual_value:+.2f}"
            
            # MACD Cross
            elif indicator == 'macd_cross':
                actual_value = self.indicators.macd_cross_direction(df['close'])
                description = f"MACD Cross={actual_value}"
            
            # Volume Spike
            elif indicator == 'volume_spike':
                multiplier = condition.get('multiplier', 1.5)
                actual_value = self.indicators.is_volume_spike(df, multiplier)
                description = f"Volume Spike={actual_value}"
            
            # === SHORT INDICATORS ===
            
            # Stochastic Overbought (> 80)
            elif indicator == 'stoch_overbought':
                actual_value = self.indicators.stochastic_k(df, 14)
                description = f"Stoch K={actual_value:.1f}"
                # Для этого индикатора проверяем > 80
                return actual_value > 80, description
            
            # Stochastic Falling (текущий < предыдущий)
            elif indicator == 'stoch_falling':
                stoch_k = self.indicators.stochastic_k(df, 14)
                # Берём предыдущее значение
                if len(df) > 15:
                    df_prev = df.iloc[:-1]
                    stoch_k_prev = self.indicators.stochastic_k(df_prev, 14)
                    actual_value = stoch_k < stoch_k_prev
                    description = f"Stoch Falling={actual_value} ({stoch_k:.1f} < {stoch_k_prev:.1f})"
                    return actual_value, description
                return False, "Insufficient data"
            
            # MACD Bearish (MACD < Signal)
            elif indicator == 'macd_bearish':
                macd_line, signal_line, _ = self.indicators.macd(df['close'])
                actual_value = macd_line < signal_line
                description = f"MACD Bearish={actual_value} ({macd_line:.4f} < {signal_line:.4f})"
                return actual_value, description
            
            else:
                logger.warning(f"Unknown indicator: {indicator}")
                return False, f"Unknown: {indicator}"
            
            # Проверка условия
            met = False
            if operator == '>' and actual_value is not None:
                met = actual_value > value
            elif operator == '<' and actual_value is not None:
                met = actual_value < value
            elif operator == '==' and actual_value is not None:
                met = actual_value == value
            elif operator == '>=' and actual_value is not None:
                met = actual_value >= value
            elif operator == '<=' and actual_value is not None:
                met = actual_value <= value
            
            return met, description
            
        except Exception as e:
            logger.error(f"Error checking condition {indicator}: {e}")
            return False, f"Error: {e}"
    
    async def check_symbol(
        self,
        symbol: str,
        df: pd.DataFrame,
        current_price: float
    ) -> Optional[Signal]:
        """Проверить ВСЕ стратегии для символа (LONG + SHORT)"""
        
        # Сначала проверяем LONG
        signal = await self._check_single_strategy(symbol, df, current_price, get_strategy(symbol))
        if signal:
            return signal
        
        # Затем проверяем SHORT
        signal = await self._check_single_strategy(symbol, df, current_price, get_short_strategy(symbol))
        if signal:
            return signal
        
        return None
    
    async def _check_single_strategy(
        self,
        symbol: str,
        df: pd.DataFrame,
        current_price: float,
        strategy: Optional[StrategyConfig]
    ) -> Optional[Signal]:
        """Проверить одну стратегию"""
        
        if not strategy or not strategy.enabled:
            return None
        
        # Уникальный ключ для лимитов (включает направление)
        signal_key = f"{symbol}_{strategy.direction}"
        
        # Проверка лимитов
        can_signal, reason = self._can_generate_signal(signal_key, strategy)
        if not can_signal:
            logger.debug(f"{symbol} {strategy.direction}: {reason}")
            return None
        
        # Проверка всех условий
        conditions_met = []
        all_met = True
        
        for condition in strategy.conditions:
            met, description = self._check_condition(condition, df, current_price)
            
            if met:
                conditions_met.append(f"✅ {description}")
            else:
                conditions_met.append(f"❌ {description}")
                all_met = False
        
        if not all_met:
            return None
        
        # ВСЕ УСЛОВИЯ ВЫПОЛНЕНЫ — генерируем сигнал!
        emoji = "📈" if strategy.direction == "LONG" else "📉"
        logger.info(f"{emoji} {symbol}: {strategy.direction} Signal generated!")
        
        # Расчёт SL/TP
        if strategy.direction == "LONG":
            stop_loss = current_price * (1 - strategy.sl_percent / 100)
            take_profit = current_price * (1 + strategy.tp_percent / 100)
        else:
            stop_loss = current_price * (1 + strategy.sl_percent / 100)
            take_profit = current_price * (1 - strategy.tp_percent / 100)
        
        # Собираем индикаторы
        indicators_data = {
            'rsi_14': self.indicators.rsi(df['close'], 14),
            'ema_21': self.indicators.ema(df['close'], 21),
            'ema_50': self.indicators.ema(df['close'], 50),
            'stoch_k': self.indicators.stochastic_k(df, 14),
        }
        
        # Обновляем счётчики
        self.last_signals[signal_key] = datetime.utcnow()
        self.signals_today[signal_key] = self.signals_today.get(signal_key, 0) + 1
        
        # Создаём сигнал
        signal = Signal(
            symbol=symbol,
            direction=strategy.direction,
            strategy_id=strategy.id,
            strategy_name=strategy.name,
            entry_price=current_price,
            stop_loss=round(stop_loss, 6),
            take_profit=round(take_profit, 6),
            indicators=indicators_data,
            conditions_met=[c for c in conditions_met if c.startswith("✅")],
            win_rate=strategy.avg_win_rate,
            confidence=strategy.avg_win_rate / 100,
            timestamp=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=30),
        )
        
        return signal
    
    async def check_all_symbols(
        self,
        market_data: Dict[str, Dict]
    ) -> List[Signal]:
        """Проверить все символы"""
        
        signals = []
        
        for symbol, strategy in get_enabled_strategies().items():
            if symbol not in market_data:
                continue
            
            data = market_data[symbol]
            df = data.get('ohlcv')
            price = data.get('price')
            
            if df is None or price is None:
                continue
            
            signal = await self.check_symbol(symbol, df, price)
            
            if signal:
                signals.append(signal)
                logger.info(f"✅ Signal: {symbol} {signal.direction} @ ${price}")
        
        return signals
    
    def get_status(self) -> dict:
        """Статус чекера"""
        self._reset_daily_counters()
        
        summary = get_strategies_summary()
        
        return {
            'signals_today': dict(self.signals_today),
            'total_today': sum(self.signals_today.values()),
            'last_signals': {
                k: v.isoformat() 
                for k, v in self.last_signals.items()
            },
            'enabled_strategies': summary['total'],
            'long_strategies': summary['long'],
            'short_strategies': summary['short'],
        }


# Глобальный экземпляр
strategy_checker = StrategyChecker()
