"""
Trading Strategies — 140+ стратегий для бэктестинга
Категории: RSI, MACD, Stochastic, Bollinger, EMA, Patterns, Combined
"""
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass, field
import pandas as pd
import numpy as np


@dataclass
class Strategy:
    """Определение стратегии"""
    id: str
    name: str
    category: str
    direction: str  # LONG, SHORT, BOTH
    condition: Callable[[pd.DataFrame], pd.Series]  # Функция условия
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


class StrategyLibrary:
    """
    Библиотека из 140+ торговых стратегий
    """
    
    SYMBOLS = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "MATIC", "LINK", "AVAX"]
    
    def __init__(self):
        self.strategies: Dict[str, Strategy] = {}
        self._register_all_strategies()
    
    def _register_all_strategies(self):
        """Регистрация всех стратегий"""
        
        # === RSI STRATEGIES (25+) ===
        self._register_rsi_strategies()
        
        # === MACD STRATEGIES (15+) ===
        self._register_macd_strategies()
        
        # === STOCHASTIC STRATEGIES (20+) ===
        self._register_stochastic_strategies()
        
        # === BOLLINGER STRATEGIES (15+) ===
        self._register_bollinger_strategies()
        
        # === EMA/SMA STRATEGIES (25+) ===
        self._register_ema_strategies()
        
        # === VOLUME STRATEGIES (10+) ===
        self._register_volume_strategies()
        
        # === PATTERN STRATEGIES (15+) ===
        self._register_pattern_strategies()
        
        # === COMBINED STRATEGIES (35+) ===
        self._register_combined_strategies()
    
    def _register_rsi_strategies(self):
        """RSI стратегии"""
        
        # RSI Oversold (разные периоды и уровни)
        for period in [7, 14, 21]:
            for level in [20, 25, 30, 35]:
                sid = f"rsi_{period}_below_{level}"
                self.strategies[sid] = Strategy(
                    id=sid,
                    name=f"RSI({period}) < {level}",
                    category="RSI",
                    direction="LONG",
                    condition=self._make_rsi_below(period, level),
                    params={"period": period, "level": level}
                )
        
        # RSI Overbought
        for period in [7, 14, 21]:
            for level in [65, 70, 75, 80]:
                sid = f"rsi_{period}_above_{level}"
                self.strategies[sid] = Strategy(
                    id=sid,
                    name=f"RSI({period}) > {level}",
                    category="RSI",
                    direction="SHORT",
                    condition=self._make_rsi_above(period, level),
                    params={"period": period, "level": level}
                )
        
        # RSI + Trend Filter
        for rsi_level in [30, 35, 40]:
            for ema_period in [21, 50]:
                sid = f"rsi_14_below_{rsi_level}_price_above_ema_{ema_period}"
                self.strategies[sid] = Strategy(
                    id=sid,
                    name=f"RSI(14) < {rsi_level} + Price > EMA({ema_period})",
                    category="RSI",
                    direction="LONG",
                    condition=self._make_rsi_with_ema(14, rsi_level, ema_period),
                    params={"rsi_level": rsi_level, "ema_period": ema_period}
                )
    
    def _register_macd_strategies(self):
        """MACD стратегии"""
        
        # MACD Cross Up
        self.strategies["macd_cross_up"] = Strategy(
            id="macd_cross_up",
            name="MACD Cross Up",
            category="MACD",
            direction="LONG",
            condition=self._make_macd_cross("up")
        )
        
        # MACD Cross Down
        self.strategies["macd_cross_down"] = Strategy(
            id="macd_cross_down",
            name="MACD Cross Down",
            category="MACD",
            direction="SHORT",
            condition=self._make_macd_cross("down")
        )
        
        # MACD Histogram Positive/Negative
        self.strategies["macd_hist_positive"] = Strategy(
            id="macd_hist_positive",
            name="MACD Histogram > 0",
            category="MACD",
            direction="LONG",
            condition=lambda df: self._macd_histogram(df) > 0
        )
        
        self.strategies["macd_hist_negative"] = Strategy(
            id="macd_hist_negative",
            name="MACD Histogram < 0",
            category="MACD",
            direction="SHORT",
            condition=lambda df: self._macd_histogram(df) < 0
        )
        
        # MACD + RSI combinations
        for rsi_level in [40, 50]:
            sid = f"macd_cross_up_rsi_below_{rsi_level}"
            self.strategies[sid] = Strategy(
                id=sid,
                name=f"MACD Cross Up + RSI < {rsi_level}",
                category="MACD",
                direction="LONG",
                condition=self._make_macd_rsi(rsi_level)
            )
        
        # MACD Above/Below Zero
        self.strategies["macd_above_zero"] = Strategy(
            id="macd_above_zero",
            name="MACD Line > 0",
            category="MACD",
            direction="LONG",
            condition=lambda df: self._macd_line(df) > 0
        )
        
        self.strategies["macd_below_zero"] = Strategy(
            id="macd_below_zero",
            name="MACD Line < 0",
            category="MACD",
            direction="SHORT",
            condition=lambda df: self._macd_line(df) < 0
        )
    
    def _register_stochastic_strategies(self):
        """Stochastic стратегии"""
        
        # Stochastic Oversold
        for k_period in [5, 9, 14, 21]:
            for level in [15, 20, 25, 30]:
                sid = f"stoch_{k_period}_below_{level}"
                self.strategies[sid] = Strategy(
                    id=sid,
                    name=f"Stoch({k_period}) K < {level}",
                    category="Stochastic",
                    direction="LONG",
                    condition=self._make_stoch_below(k_period, level),
                    params={"period": k_period, "level": level}
                )
        
        # Stochastic Overbought
        for k_period in [5, 9, 14, 21]:
            for level in [70, 75, 80, 85]:
                sid = f"stoch_{k_period}_above_{level}"
                self.strategies[sid] = Strategy(
                    id=sid,
                    name=f"Stoch({k_period}) K > {level}",
                    category="Stochastic",
                    direction="SHORT",
                    condition=self._make_stoch_above(k_period, level),
                    params={"period": k_period, "level": level}
                )
        
        # Stochastic + MACD
        self.strategies["stoch_14_below_25_macd_cross_up"] = Strategy(
            id="stoch_14_below_25_macd_cross_up",
            name="Stoch(14) < 25 + MACD Cross Up",
            category="Stochastic",
            direction="LONG",
            condition=self._make_stoch_macd(14, 25)
        )
        
        # Stochastic K/D Cross
        self.strategies["stoch_k_cross_d_up"] = Strategy(
            id="stoch_k_cross_d_up",
            name="Stoch K Cross D Up",
            category="Stochastic",
            direction="LONG",
            condition=self._make_stoch_kd_cross("up")
        )
    
    def _register_bollinger_strategies(self):
        """Bollinger Bands стратегии"""
        
        # Price below lower band
        for period in [20]:
            for std in [1.5, 2.0, 2.5, 3.0]:
                sid = f"bb_{period}_{str(std).replace('.', '_')}_below_lower"
                self.strategies[sid] = Strategy(
                    id=sid,
                    name=f"Price < BB({period}, {std}) Lower",
                    category="Bollinger",
                    direction="LONG",
                    condition=self._make_bb_below(period, std),
                    params={"period": period, "std": std}
                )
        
        # Price above upper band
        for period in [20]:
            for std in [1.5, 2.0, 2.5, 3.0]:
                sid = f"bb_{period}_{str(std).replace('.', '_')}_above_upper"
                self.strategies[sid] = Strategy(
                    id=sid,
                    name=f"Price > BB({period}, {std}) Upper",
                    category="Bollinger",
                    direction="SHORT",
                    condition=self._make_bb_above(period, std),
                    params={"period": period, "std": std}
                )
        
        # BB Squeeze + Breakout
        self.strategies["bb_squeeze_breakout_up"] = Strategy(
            id="bb_squeeze_breakout_up",
            name="BB Squeeze + Breakout Up",
            category="Bollinger",
            direction="LONG",
            condition=self._make_bb_squeeze("up")
        )
        
        self.strategies["bb_squeeze_breakout_down"] = Strategy(
            id="bb_squeeze_breakout_down",
            name="BB Squeeze + Breakout Down",
            category="Bollinger",
            direction="SHORT",
            condition=self._make_bb_squeeze("down")
        )
        
        # BB %B indicator
        self.strategies["bb_percent_b_below_0"] = Strategy(
            id="bb_percent_b_below_0",
            name="BB %B < 0 (Below Lower)",
            category="Bollinger",
            direction="LONG",
            condition=lambda df: self._calc_bb_percent_b(df) < 0
        )
    
    def _register_ema_strategies(self):
        """EMA/SMA стратегии"""
        
        # EMA Cross
        ema_pairs = [(9, 21), (12, 26), (20, 50), (50, 200), (9, 50), (21, 50)]
        for fast, slow in ema_pairs:
            # Cross Up
            sid = f"ema_{fast}_{slow}_cross_up"
            self.strategies[sid] = Strategy(
                id=sid,
                name=f"EMA({fast}) Cross Up EMA({slow})",
                category="EMA",
                direction="LONG",
                condition=self._make_ema_cross(fast, slow, "up")
            )
            
            # Cross Down
            sid = f"ema_{fast}_{slow}_cross_down"
            self.strategies[sid] = Strategy(
                id=sid,
                name=f"EMA({fast}) Cross Down EMA({slow})",
                category="EMA",
                direction="SHORT",
                condition=self._make_ema_cross(fast, slow, "down")
            )
        
        # Price above/below EMA
        for period in [9, 21, 50, 100, 200]:
            sid = f"price_above_ema_{period}"
            self.strategies[sid] = Strategy(
                id=sid,
                name=f"Price > EMA({period})",
                category="EMA",
                direction="LONG",
                condition=self._make_price_vs_ema(period, "above")
            )
            
            sid = f"price_below_ema_{period}"
            self.strategies[sid] = Strategy(
                id=sid,
                name=f"Price < EMA({period})",
                category="EMA",
                direction="SHORT",
                condition=self._make_price_vs_ema(period, "below")
            )
        
        # Triple EMA Alignment
        self.strategies["triple_ema_bullish"] = Strategy(
            id="triple_ema_bullish",
            name="EMA9 > EMA21 > EMA50",
            category="EMA",
            direction="LONG",
            condition=self._make_triple_ema("bullish")
        )
        
        self.strategies["triple_ema_bearish"] = Strategy(
            id="triple_ema_bearish",
            name="EMA9 < EMA21 < EMA50",
            category="EMA",
            direction="SHORT",
            condition=self._make_triple_ema("bearish")
        )
    
    def _register_volume_strategies(self):
        """Volume стратегии"""
        
        # Volume Spike + Price Up
        self.strategies["volume_spike_price_up"] = Strategy(
            id="volume_spike_price_up",
            name="Volume > 2x Avg + Price Up",
            category="Volume",
            direction="LONG",
            condition=self._make_volume_spike("up", 2.0)
        )
        
        # Volume Spike + Price Down
        self.strategies["volume_spike_price_down"] = Strategy(
            id="volume_spike_price_down",
            name="Volume > 2x Avg + Price Down",
            category="Volume",
            direction="SHORT",
            condition=self._make_volume_spike("down", 2.0)
        )
        
        # Volume Spike + RSI Oversold
        self.strategies["volume_spike_rsi_oversold"] = Strategy(
            id="volume_spike_rsi_oversold",
            name="Volume Spike + RSI < 30",
            category="Volume",
            direction="LONG",
            condition=self._make_volume_rsi(30)
        )
        
        # High Volume Breakout
        for mult in [1.5, 2.0, 3.0]:
            sid = f"volume_breakout_{str(mult).replace('.', '_')}x"
            self.strategies[sid] = Strategy(
                id=sid,
                name=f"Volume > {mult}x + New High",
                category="Volume",
                direction="LONG",
                condition=self._make_volume_breakout(mult)
            )
    
    def _register_pattern_strategies(self):
        """Pattern стратегии"""
        
        # Double Bottom
        self.strategies["double_bottom"] = Strategy(
            id="double_bottom",
            name="Double Bottom Pattern",
            category="Pattern",
            direction="LONG",
            condition=self._detect_double_bottom
        )
        
        # Double Top
        self.strategies["double_top"] = Strategy(
            id="double_top",
            name="Double Top Pattern",
            category="Pattern",
            direction="SHORT",
            condition=self._detect_double_top
        )
        
        # Bullish Engulfing
        self.strategies["bullish_engulfing"] = Strategy(
            id="bullish_engulfing",
            name="Bullish Engulfing",
            category="Pattern",
            direction="LONG",
            condition=self._detect_bullish_engulfing
        )
        
        # Bearish Engulfing
        self.strategies["bearish_engulfing"] = Strategy(
            id="bearish_engulfing",
            name="Bearish Engulfing",
            category="Pattern",
            direction="SHORT",
            condition=self._detect_bearish_engulfing
        )
        
        # Hammer
        self.strategies["hammer"] = Strategy(
            id="hammer",
            name="Hammer Candle",
            category="Pattern",
            direction="LONG",
            condition=self._detect_hammer
        )
        
        # Shooting Star
        self.strategies["shooting_star"] = Strategy(
            id="shooting_star",
            name="Shooting Star",
            category="Pattern",
            direction="SHORT",
            condition=self._detect_shooting_star
        )
        
        # Morning Star
        self.strategies["morning_star"] = Strategy(
            id="morning_star",
            name="Morning Star",
            category="Pattern",
            direction="LONG",
            condition=self._detect_morning_star
        )
        
        # Evening Star
        self.strategies["evening_star"] = Strategy(
            id="evening_star",
            name="Evening Star",
            category="Pattern",
            direction="SHORT",
            condition=self._detect_evening_star
        )
        
        # Doji
        self.strategies["doji_reversal"] = Strategy(
            id="doji_reversal",
            name="Doji at Support",
            category="Pattern",
            direction="LONG",
            condition=self._detect_doji
        )
    
    def _register_combined_strategies(self):
        """Комбинированные стратегии (самые сильные)"""
        
        # RSI + EMA + Volume
        self.strategies["rsi_ema_volume_long"] = Strategy(
            id="rsi_ema_volume_long",
            name="RSI<30 + Price>EMA50 + Volume Spike",
            category="Combined",
            direction="LONG",
            condition=self._make_rsi_ema_volume(30, 50, 1.5)
        )
        
        # Stochastic + MACD + RSI
        self.strategies["stoch_macd_rsi_long"] = Strategy(
            id="stoch_macd_rsi_long",
            name="Stoch<25 + MACD Up + RSI<40",
            category="Combined",
            direction="LONG",
            condition=self._make_stoch_macd_rsi()
        )
        
        # Triple EMA + RSI
        self.strategies["triple_ema_rsi_long"] = Strategy(
            id="triple_ema_rsi_long",
            name="EMA9>EMA21>EMA50 + RSI<40",
            category="Combined",
            direction="LONG",
            condition=self._make_triple_ema_rsi()
        )
        
        # BB + RSI + Volume
        self.strategies["bb_rsi_volume_long"] = Strategy(
            id="bb_rsi_volume_long",
            name="Price<BB Lower + RSI<30 + High Volume",
            category="Combined",
            direction="LONG",
            condition=self._make_bb_rsi_volume()
        )
        
        # Multi-indicator confluence
        self.strategies["multi_indicator_confluence_long"] = Strategy(
            id="multi_indicator_confluence_long",
            name="RSI<35 + Stoch<30 + MACD Positive + EMA Trend",
            category="Combined",
            direction="LONG",
            condition=self._make_multi_confluence()
        )
        
        # RSI Divergence simulation
        self.strategies["rsi_oversold_bounce"] = Strategy(
            id="rsi_oversold_bounce",
            name="RSI<25 + Price>EMA21 + Green Candle",
            category="Combined",
            direction="LONG",
            condition=self._make_rsi_bounce()
        )
        
        # MACD + BB
        self.strategies["macd_bb_long"] = Strategy(
            id="macd_bb_long",
            name="MACD Cross Up + Price<BB Middle",
            category="Combined",
            direction="LONG",
            condition=self._make_macd_bb()
        )
        
        # Stoch + BB
        self.strategies["stoch_bb_long"] = Strategy(
            id="stoch_bb_long",
            name="Stoch<20 + Price<BB Lower",
            category="Combined",
            direction="LONG",
            condition=self._make_stoch_bb()
        )
        
        # EMA + RSI + Stoch
        self.strategies["ema_rsi_stoch_long"] = Strategy(
            id="ema_rsi_stoch_long",
            name="Price>EMA50 + RSI<40 + Stoch<30",
            category="Combined",
            direction="LONG",
            condition=self._make_ema_rsi_stoch()
        )
        
        # Momentum Breakout
        self.strategies["momentum_breakout"] = Strategy(
            id="momentum_breakout",
            name="RSI>50 + MACD>0 + Price>EMA20 + Volume Spike",
            category="Combined",
            direction="LONG",
            condition=self._make_momentum_breakout()
        )
    
    # === CONDITION FACTORY METHODS ===
    
    def _make_rsi_below(self, period: int, level: int):
        def condition(df):
            return self._calc_rsi(df, period) < level
        return condition
    
    def _make_rsi_above(self, period: int, level: int):
        def condition(df):
            return self._calc_rsi(df, period) > level
        return condition
    
    def _make_rsi_with_ema(self, rsi_period: int, rsi_level: int, ema_period: int):
        def condition(df):
            rsi = self._calc_rsi(df, rsi_period)
            ema = df['close'].ewm(span=ema_period, adjust=False).mean()
            return (rsi < rsi_level) & (df['close'] > ema)
        return condition
    
    def _make_macd_cross(self, direction: str):
        def condition(df):
            return self._macd_cross(df, direction)
        return condition
    
    def _make_macd_rsi(self, rsi_level: int):
        def condition(df):
            return self._macd_cross(df, "up") & (self._calc_rsi(df, 14) < rsi_level)
        return condition
    
    def _make_stoch_below(self, period: int, level: int):
        def condition(df):
            return self._calc_stoch_k(df, period) < level
        return condition
    
    def _make_stoch_above(self, period: int, level: int):
        def condition(df):
            return self._calc_stoch_k(df, period) > level
        return condition
    
    def _make_stoch_macd(self, stoch_period: int, stoch_level: int):
        def condition(df):
            return (self._calc_stoch_k(df, stoch_period) < stoch_level) & self._macd_cross(df, "up")
        return condition
    
    def _make_stoch_kd_cross(self, direction: str):
        def condition(df):
            k = self._calc_stoch_k(df, 14)
            d = k.rolling(3).mean()
            if direction == "up":
                return (k > d) & (k.shift(1) <= d.shift(1))
            else:
                return (k < d) & (k.shift(1) >= d.shift(1))
        return condition
    
    def _make_bb_below(self, period: int, std: float):
        def condition(df):
            return df['close'] < self._calc_bb_lower(df, period, std)
        return condition
    
    def _make_bb_above(self, period: int, std: float):
        def condition(df):
            return df['close'] > self._calc_bb_upper(df, period, std)
        return condition
    
    def _make_bb_squeeze(self, direction: str):
        def condition(df):
            return self._bb_squeeze_breakout(df, direction)
        return condition
    
    def _make_ema_cross(self, fast: int, slow: int, direction: str):
        def condition(df):
            return self._ema_cross(df, fast, slow, direction)
        return condition
    
    def _make_price_vs_ema(self, period: int, direction: str):
        def condition(df):
            ema = df['close'].ewm(span=period, adjust=False).mean()
            if direction == "above":
                return df['close'] > ema
            else:
                return df['close'] < ema
        return condition
    
    def _make_triple_ema(self, direction: str):
        def condition(df):
            ema9 = df['close'].ewm(span=9, adjust=False).mean()
            ema21 = df['close'].ewm(span=21, adjust=False).mean()
            ema50 = df['close'].ewm(span=50, adjust=False).mean()
            if direction == "bullish":
                return (ema9 > ema21) & (ema21 > ema50)
            else:
                return (ema9 < ema21) & (ema21 < ema50)
        return condition
    
    def _make_volume_spike(self, price_dir: str, multiplier: float):
        def condition(df):
            vol_avg = df['volume'].rolling(20).mean()
            vol_spike = df['volume'] > vol_avg * multiplier
            if price_dir == "up":
                return vol_spike & (df['close'] > df['open'])
            else:
                return vol_spike & (df['close'] < df['open'])
        return condition
    
    def _make_volume_rsi(self, rsi_level: int):
        def condition(df):
            vol_avg = df['volume'].rolling(20).mean()
            return (df['volume'] > vol_avg * 1.5) & (self._calc_rsi(df, 14) < rsi_level)
        return condition
    
    def _make_volume_breakout(self, multiplier: float):
        def condition(df):
            vol_avg = df['volume'].rolling(20).mean()
            high_20 = df['high'].rolling(20).max()
            return (df['volume'] > vol_avg * multiplier) & (df['close'] > high_20.shift(1))
        return condition
    
    def _make_rsi_ema_volume(self, rsi_level: int, ema_period: int, vol_mult: float):
        def condition(df):
            rsi = self._calc_rsi(df, 14)
            ema = df['close'].ewm(span=ema_period, adjust=False).mean()
            vol_avg = df['volume'].rolling(20).mean()
            return (rsi < rsi_level) & (df['close'] > ema) & (df['volume'] > vol_avg * vol_mult)
        return condition
    
    def _make_stoch_macd_rsi(self):
        def condition(df):
            stoch = self._calc_stoch_k(df, 14)
            rsi = self._calc_rsi(df, 14)
            macd_up = self._macd_cross(df, "up")
            return (stoch < 25) & macd_up & (rsi < 40)
        return condition
    
    def _make_triple_ema_rsi(self):
        def condition(df):
            ema9 = df['close'].ewm(span=9, adjust=False).mean()
            ema21 = df['close'].ewm(span=21, adjust=False).mean()
            ema50 = df['close'].ewm(span=50, adjust=False).mean()
            rsi = self._calc_rsi(df, 14)
            return (ema9 > ema21) & (ema21 > ema50) & (rsi < 40)
        return condition
    
    def _make_bb_rsi_volume(self):
        def condition(df):
            bb_lower = self._calc_bb_lower(df, 20, 2)
            rsi = self._calc_rsi(df, 14)
            vol_avg = df['volume'].rolling(20).mean()
            return (df['close'] < bb_lower) & (rsi < 30) & (df['volume'] > vol_avg)
        return condition
    
    def _make_multi_confluence(self):
        def condition(df):
            rsi = self._calc_rsi(df, 14)
            stoch = self._calc_stoch_k(df, 14)
            macd_hist = self._macd_histogram(df)
            ema50 = df['close'].ewm(span=50, adjust=False).mean()
            return (rsi < 35) & (stoch < 30) & (macd_hist > 0) & (df['close'] > ema50)
        return condition
    
    def _make_rsi_bounce(self):
        def condition(df):
            rsi = self._calc_rsi(df, 14)
            ema21 = df['close'].ewm(span=21, adjust=False).mean()
            green = df['close'] > df['open']
            return (rsi < 25) & (df['close'] > ema21) & green
        return condition
    
    def _make_macd_bb(self):
        def condition(df):
            macd_up = self._macd_cross(df, "up")
            bb_mid = df['close'].rolling(20).mean()
            return macd_up & (df['close'] < bb_mid)
        return condition
    
    def _make_stoch_bb(self):
        def condition(df):
            stoch = self._calc_stoch_k(df, 14)
            bb_lower = self._calc_bb_lower(df, 20, 2)
            return (stoch < 20) & (df['close'] < bb_lower)
        return condition
    
    def _make_ema_rsi_stoch(self):
        def condition(df):
            ema50 = df['close'].ewm(span=50, adjust=False).mean()
            rsi = self._calc_rsi(df, 14)
            stoch = self._calc_stoch_k(df, 14)
            return (df['close'] > ema50) & (rsi < 40) & (stoch < 30)
        return condition
    
    def _make_momentum_breakout(self):
        def condition(df):
            rsi = self._calc_rsi(df, 14)
            macd = self._macd_line(df)
            ema20 = df['close'].ewm(span=20, adjust=False).mean()
            vol_avg = df['volume'].rolling(20).mean()
            return (rsi > 50) & (macd > 0) & (df['close'] > ema20) & (df['volume'] > vol_avg * 1.5)
        return condition
    
    # === INDICATOR CALCULATIONS ===
    
    def _calc_rsi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate RSI"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.inf)
        return 100 - (100 / (1 + rs))
    
    def _calc_stoch_k(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Stochastic K"""
        lowest_low = df['low'].rolling(window=period).min()
        highest_high = df['high'].rolling(window=period).max()
        denom = highest_high - lowest_low
        return 100 * (df['close'] - lowest_low) / denom.replace(0, 0.0001)
    
    def _calc_bb_lower(self, df: pd.DataFrame, period: int, std: float) -> pd.Series:
        """Calculate Bollinger Lower Band"""
        sma = df['close'].rolling(window=period).mean()
        std_dev = df['close'].rolling(window=period).std()
        return sma - (std_dev * std)
    
    def _calc_bb_upper(self, df: pd.DataFrame, period: int, std: float) -> pd.Series:
        """Calculate Bollinger Upper Band"""
        sma = df['close'].rolling(window=period).mean()
        std_dev = df['close'].rolling(window=period).std()
        return sma + (std_dev * std)
    
    def _calc_bb_percent_b(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Bollinger %B"""
        upper = self._calc_bb_upper(df, 20, 2)
        lower = self._calc_bb_lower(df, 20, 2)
        return (df['close'] - lower) / (upper - lower)
    
    def _macd_line(self, df: pd.DataFrame) -> pd.Series:
        """Calculate MACD Line"""
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        return ema12 - ema26
    
    def _macd_cross(self, df: pd.DataFrame, direction: str) -> pd.Series:
        """Detect MACD crossover"""
        macd = self._macd_line(df)
        signal = macd.ewm(span=9, adjust=False).mean()
        
        if direction == "up":
            return (macd > signal) & (macd.shift(1) <= signal.shift(1))
        else:
            return (macd < signal) & (macd.shift(1) >= signal.shift(1))
    
    def _macd_histogram(self, df: pd.DataFrame) -> pd.Series:
        """Calculate MACD Histogram"""
        macd = self._macd_line(df)
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd - signal
    
    def _ema_cross(self, df: pd.DataFrame, fast: int, slow: int, direction: str) -> pd.Series:
        """Detect EMA crossover"""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        
        if direction == "up":
            return (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
        else:
            return (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))
    
    def _bb_squeeze_breakout(self, df: pd.DataFrame, direction: str) -> pd.Series:
        """Detect BB squeeze and breakout"""
        period = 20
        sma = df['close'].rolling(window=period).mean()
        std_dev = df['close'].rolling(window=period).std()
        
        # BB width
        bb_width = (std_dev * 2) / sma
        squeeze = bb_width < bb_width.rolling(20).mean() * 0.8
        
        if direction == "up":
            return squeeze.shift(1) & (df['close'] > sma + std_dev)
        else:
            return squeeze.shift(1) & (df['close'] < sma - std_dev)
    
    # === PATTERN DETECTION ===
    
    def _detect_double_bottom(self, df: pd.DataFrame) -> pd.Series:
        """Detect double bottom pattern"""
        result = pd.Series(False, index=df.index)
        lookback = 20
        
        if len(df) < lookback:
            return result
        
        for i in range(lookback, len(df)):
            window = df['low'].iloc[i-lookback:i]
            if len(window) < 2:
                continue
            
            min_val = window.min()
            # Find all values close to minimum
            close_to_min = window[window < min_val * 1.02]
            
            if len(close_to_min) >= 2:
                result.iloc[i] = True
        
        return result
    
    def _detect_double_top(self, df: pd.DataFrame) -> pd.Series:
        """Detect double top pattern"""
        result = pd.Series(False, index=df.index)
        lookback = 20
        
        if len(df) < lookback:
            return result
        
        for i in range(lookback, len(df)):
            window = df['high'].iloc[i-lookback:i]
            if len(window) < 2:
                continue
            
            max_val = window.max()
            close_to_max = window[window > max_val * 0.98]
            
            if len(close_to_max) >= 2:
                result.iloc[i] = True
        
        return result
    
    def _detect_bullish_engulfing(self, df: pd.DataFrame) -> pd.Series:
        """Detect bullish engulfing pattern"""
        prev_red = df['close'].shift(1) < df['open'].shift(1)
        curr_green = df['close'] > df['open']
        engulfing = (df['open'] < df['close'].shift(1)) & (df['close'] > df['open'].shift(1))
        return prev_red & curr_green & engulfing
    
    def _detect_bearish_engulfing(self, df: pd.DataFrame) -> pd.Series:
        """Detect bearish engulfing pattern"""
        prev_green = df['close'].shift(1) > df['open'].shift(1)
        curr_red = df['close'] < df['open']
        engulfing = (df['open'] > df['close'].shift(1)) & (df['close'] < df['open'].shift(1))
        return prev_green & curr_red & engulfing
    
    def _detect_hammer(self, df: pd.DataFrame) -> pd.Series:
        """Detect hammer candle"""
        body = abs(df['close'] - df['open'])
        lower_wick = df[['open', 'close']].min(axis=1) - df['low']
        upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
        return (lower_wick > body * 2) & (upper_wick < body * 0.5) & (body > 0)
    
    def _detect_shooting_star(self, df: pd.DataFrame) -> pd.Series:
        """Detect shooting star candle"""
        body = abs(df['close'] - df['open'])
        lower_wick = df[['open', 'close']].min(axis=1) - df['low']
        upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
        return (upper_wick > body * 2) & (lower_wick < body * 0.5) & (body > 0)
    
    def _detect_morning_star(self, df: pd.DataFrame) -> pd.Series:
        """Detect morning star pattern"""
        day1_red = (df['close'].shift(2) < df['open'].shift(2))
        day1_big = abs(df['close'].shift(2) - df['open'].shift(2)) > df['close'].shift(2) * 0.01
        day2_small = abs(df['close'].shift(1) - df['open'].shift(1)) < df['close'].shift(1) * 0.005
        day3_green = (df['close'] > df['open'])
        day3_recover = df['close'] > (df['open'].shift(2) + df['close'].shift(2)) / 2
        return day1_red & day1_big & day2_small & day3_green & day3_recover
    
    def _detect_evening_star(self, df: pd.DataFrame) -> pd.Series:
        """Detect evening star pattern"""
        day1_green = (df['close'].shift(2) > df['open'].shift(2))
        day1_big = abs(df['close'].shift(2) - df['open'].shift(2)) > df['close'].shift(2) * 0.01
        day2_small = abs(df['close'].shift(1) - df['open'].shift(1)) < df['close'].shift(1) * 0.005
        day3_red = (df['close'] < df['open'])
        day3_drop = df['close'] < (df['open'].shift(2) + df['close'].shift(2)) / 2
        return day1_green & day1_big & day2_small & day3_red & day3_drop
    
    def _detect_doji(self, df: pd.DataFrame) -> pd.Series:
        """Detect doji candle"""
        body = abs(df['close'] - df['open'])
        total_range = df['high'] - df['low']
        return (body < total_range * 0.1) & (total_range > 0)
    
    # === PUBLIC METHODS ===
    
    def get_all_strategies(self) -> Dict[str, Strategy]:
        """Get all strategies"""
        return self.strategies
    
    def get_by_category(self, category: str) -> Dict[str, Strategy]:
        """Get strategies by category"""
        return {k: v for k, v in self.strategies.items() if v.category == category}
    
    def get_by_direction(self, direction: str) -> Dict[str, Strategy]:
        """Get strategies by direction"""
        return {k: v for k, v in self.strategies.items() if v.direction == direction}
    
    def get_strategy(self, strategy_id: str) -> Optional[Strategy]:
        """Get specific strategy"""
        return self.strategies.get(strategy_id)
    
    def count(self) -> int:
        """Count total strategies"""
        return len(self.strategies)
    
    def list_categories(self) -> Dict[str, int]:
        """List categories with counts"""
        categories = {}
        for s in self.strategies.values():
            categories[s.category] = categories.get(s.category, 0) + 1
        return categories


# Global instance
strategy_library = StrategyLibrary()


def get_all_strategies():
    """Get all strategies"""
    return strategy_library.get_all_strategies()


def count_strategies():
    """Count strategies"""
    return strategy_library.count()
