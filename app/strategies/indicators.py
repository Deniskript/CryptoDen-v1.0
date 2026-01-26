"""
Technical Indicators — Расчёт индикаторов
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple


class TechnicalIndicators:
    """Библиотека технических индикаторов"""
    
    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> float:
        """RSI"""
        if len(series) < period + 1:
            return 50.0
        
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))
        
        value = rsi.iloc[-1]
        return round(float(value), 2) if not pd.isna(value) else 50.0
    
    @staticmethod
    def ema(series: pd.Series, period: int) -> float:
        """EMA"""
        if len(series) < period:
            return float(series.iloc[-1])
        
        ema = series.ewm(span=period, adjust=False).mean()
        return round(float(ema.iloc[-1]), 6)
    
    @staticmethod
    def sma(series: pd.Series, period: int) -> float:
        """SMA"""
        if len(series) < period:
            return float(series.iloc[-1])
        
        return round(float(series.rolling(period).mean().iloc[-1]), 6)
    
    @staticmethod
    def stochastic_k(df: pd.DataFrame, period: int = 14) -> float:
        """Stochastic K"""
        if len(df) < period:
            return 50.0
        
        low_min = df['low'].rolling(window=period).min()
        high_max = df['high'].rolling(window=period).max()
        
        denom = high_max - low_min
        k = 100 * (df['close'] - low_min) / denom.replace(0, 0.0001)
        
        value = k.iloc[-1]
        return round(float(value), 2) if not pd.isna(value) else 50.0
    
    @staticmethod
    def stochastic_d(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> float:
        """Stochastic D"""
        if len(df) < k_period + d_period:
            return 50.0
        
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        
        denom = high_max - low_min
        k = 100 * (df['close'] - low_min) / denom.replace(0, 0.0001)
        d = k.rolling(d_period).mean()
        
        value = d.iloc[-1]
        return round(float(value), 2) if not pd.isna(value) else 50.0
    
    @staticmethod
    def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """MACD - returns (macd_line, signal_line, histogram)"""
        if len(series) < slow + signal:
            return 0.0, 0.0, 0.0
        
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return (
            round(float(macd_line.iloc[-1]), 6),
            round(float(signal_line.iloc[-1]), 6),
            round(float(histogram.iloc[-1]), 6)
        )
    
    @staticmethod
    def macd_cross_direction(series: pd.Series) -> Optional[str]:
        """Направление MACD кросса"""
        if len(series) < 35:
            return None
        
        ema12 = series.ewm(span=12, adjust=False).mean()
        ema26 = series.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        
        hist = macd - signal
        
        if len(hist) >= 2:
            prev = hist.iloc[-2]
            curr = hist.iloc[-1]
            
            if not pd.isna(prev) and not pd.isna(curr):
                if prev < 0 and curr > 0:
                    return "up"
                elif prev > 0 and curr < 0:
                    return "down"
        
        return None
    
    @staticmethod
    def bollinger_bands(series: pd.Series, period: int = 20, std: float = 2.0) -> Tuple[float, float, float]:
        """Bollinger Bands - returns (upper, middle, lower)"""
        if len(series) < period:
            price = float(series.iloc[-1])
            return price, price, price
        
        sma = series.rolling(period).mean()
        std_dev = series.rolling(period).std()
        
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        
        return (
            round(float(upper.iloc[-1]), 6),
            round(float(sma.iloc[-1]), 6),
            round(float(lower.iloc[-1]), 6)
        )
    
    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> float:
        """Average True Range"""
        if len(df) < period + 1:
            return 0.0
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        value = atr.iloc[-1]
        return round(float(value), 6) if not pd.isna(value) else 0.0
    
    @staticmethod
    def volume_sma(df: pd.DataFrame, period: int = 20) -> float:
        """Volume SMA"""
        if len(df) < period:
            return float(df['volume'].iloc[-1])
        
        return float(df['volume'].rolling(period).mean().iloc[-1])
    
    @staticmethod
    def is_volume_spike(df: pd.DataFrame, multiplier: float = 1.5, period: int = 20) -> bool:
        """Check if current volume is a spike"""
        if len(df) < period + 1:
            return False
        
        avg_volume = df['volume'].rolling(period).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        
        return current_volume > avg_volume * multiplier


# Глобальный экземпляр
indicators = TechnicalIndicators()
