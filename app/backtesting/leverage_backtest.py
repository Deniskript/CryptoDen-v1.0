"""
📊 Бэктест с плечами и РЕАЛЬНЫМИ комиссиями Bybit

Учитывает ВСЕ расходы:
├── Taker Fee: 0.055%
├── Maker Fee: 0.02%
├── Funding Rate: каждые 8 часов
└── При плече комиссии умножаются!

Пример 10x плечо, $100 депозит:
├── Позиция: $1000
├── Открытие: $1000 × 0.055% = $0.55
├── Закрытие: $1000 × 0.055% = $0.55
├── Funding (3× в день): $1000 × 0.01% × 3 = $0.30
└── Итого за день: $1.40 = 1.4% от депозита!
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path
import json
import aiohttp


@dataclass
class BacktestConfig:
    """Настройки бэктеста"""
    initial_balance: float = 1000      # Начальный депозит
    leverages: List[int] = None        # Плечи для теста
    taker_fee: float = 0.00055         # 0.055%
    maker_fee: float = 0.0002          # 0.02%
    avg_funding_rate: float = 0.0001   # 0.01% каждые 8ч
    liquidation_threshold: float = 0.9  # Ликвидация при -90% маржи
    position_size_pct: float = 0.15    # 15% от баланса на сделку
    max_hold_hours: int = 24           # Макс время в позиции
    
    def __post_init__(self):
        if self.leverages is None:
            self.leverages = [1, 2, 3, 5, 10]


@dataclass
class TradeResult:
    """Результат сделки"""
    symbol: str
    direction: str           # LONG / SHORT
    entry_price: float
    exit_price: float
    leverage: int
    margin_used: float       # Маржа (депозит)
    position_size: float     # Полный размер позиции
    pnl_gross: float         # До комиссий
    commission: float        # Все комиссии
    funding_paid: float      # Funding за время в позиции
    pnl_net: float           # Чистый PnL
    pnl_pct: float           # % от маржи
    hold_time_hours: float
    exit_reason: str         # TP / SL / TIMEOUT / LIQUIDATION
    liquidated: bool = False


@dataclass  
class BacktestResult:
    """Результат бэктеста для одной конфигурации"""
    symbol: str
    leverage: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_pnl: float
    total_commissions: float
    total_funding: float
    net_pnl: float
    net_pnl_percent: float
    max_drawdown: float
    sharpe_ratio: float
    liquidations: int
    avg_trade_duration: float
    best_trade: float
    worst_trade: float
    profit_factor: float
    final_balance: float
    trades_per_day: float


class LeverageBacktester:
    """
    📊 Бэктестер с учётом плечей и ВСЕХ комиссий Bybit
    
    Особенности:
    - Реальные комиссии Bybit (taker/maker)
    - Funding rate каждые 8 часов
    - Правильный расчёт ликвидации
    - Учёт проскальзывания
    """
    
    BYBIT_BASE_URL = "https://api.bybit.com"
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.results: Dict[str, Dict[int, BacktestResult]] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _fetch_klines(
        self, 
        symbol: str, 
        interval: str = "15", 
        limit: int = 1000,
        end_time: int = None
    ) -> List:
        """Загрузить свечи с Bybit"""
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.BYBIT_BASE_URL}/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": f"{symbol}USDT",
            "interval": interval,
            "limit": limit
        }
        
        if end_time:
            params["end"] = end_time
        
        try:
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                
                if data.get("retCode") == 0:
                    return data.get("result", {}).get("list", [])
                else:
                    print(f"   ⚠️ API Error: {data.get('retMsg')}")
                    return []
        except Exception as e:
            print(f"   ❌ Request error: {e}")
            return []
    
    async def fetch_historical_data(self, symbol: str, days: int = 180) -> pd.DataFrame:
        """Загрузить исторические данные"""
        
        # Проверяем кэш
        cache_dir = Path("/root/crypto-bot/data")
        cache_file = cache_dir / f"{symbol}_leverage_backtest_{days}d.parquet"
        
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                if len(df) > 1000:
                    print(f"   📂 Загружено из кэша: {len(df)} свечей")
                    return df
            except:
                pass
        
        print(f"   📥 Загружаю {symbol} за {days} дней...")
        
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        
        all_klines = []
        current_end = end_time
        
        while current_end > start_time:
            klines = await self._fetch_klines(
                symbol=symbol,
                interval="15",  # 15 минут
                limit=1000,
                end_time=current_end
            )
            
            if not klines:
                break
            
            all_klines.extend(klines)
            
            # Bybit возвращает в обратном порядке
            oldest_ts = int(klines[-1][0])
            current_end = oldest_ts - 1
            
            await asyncio.sleep(0.1)
        
        if not all_klines:
            return pd.DataFrame()
        
        # Создаём DataFrame
        # Bybit формат: [timestamp, open, high, low, close, volume, turnover]
        df = pd.DataFrame(all_klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        df = df.drop_duplicates(subset=['timestamp'])
        
        # Сохраняем в кэш
        try:
            cache_dir.mkdir(exist_ok=True)
            df.to_parquet(cache_file)
        except:
            pass
        
        print(f"   ✅ Загружено {len(df)} свечей для {symbol}")
        
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Рассчитать все индикаторы"""
        
        df = df.copy()
        
        # EMA
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.inf)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Stochastic
        low_14 = df['low'].rolling(14).min()
        high_14 = df['high'].rolling(14).max()
        df['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14 + 0.0001)
        df['stoch_d'] = df['stoch_k'].rolling(3).mean()
        
        # MACD
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp12 - exp26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # Bollinger Bands
        df['bb_mid'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
        
        # ATR для динамического SL/TP
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        df['atr_pct'] = df['atr'] / df['close'] * 100
        
        # Volume
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        return df
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Генерация сигналов на основе комбо стратегий"""
        
        df = df.copy()
        df['signal'] = 0  # 0 = нет, 1 = LONG, -1 = SHORT
        df['signal_strength'] = 0.0
        
        # ==========================================
        # LONG СИГНАЛЫ
        # ==========================================
        
        # 1. RSI Oversold + EMA Uptrend
        long_rsi_ema = (
            (df['rsi'] < 35) &
            (df['close'] > df['ema_50']) &
            (df['ema_9'] > df['ema_21'])
        )
        
        # 2. Stochastic Oversold + MACD Cross Up
        long_stoch_macd = (
            (df['stoch_k'] < 25) &
            (df['macd_hist'] > df['macd_hist'].shift(1)) &
            (df['macd_hist'].shift(1) < 0)
        )
        
        # 3. Bollinger Bounce + Volume Spike
        long_bb_volume = (
            (df['close'] < df['bb_lower'] * 1.01) &
            (df['volume_ratio'] > 1.5) &
            (df['rsi'] < 40)
        )
        
        # Объединяем LONG сигналы
        df.loc[long_rsi_ema, 'signal'] = 1
        df.loc[long_rsi_ema, 'signal_strength'] = 0.7
        
        df.loc[long_stoch_macd, 'signal'] = 1
        df.loc[long_stoch_macd, 'signal_strength'] = 0.8
        
        df.loc[long_bb_volume, 'signal'] = 1
        df.loc[long_bb_volume, 'signal_strength'] = 0.75
        
        # ==========================================
        # SHORT СИГНАЛЫ
        # ==========================================
        
        # 1. RSI Overbought + EMA Downtrend
        short_rsi_ema = (
            (df['rsi'] > 70) &
            (df['close'] < df['ema_50']) &
            (df['ema_9'] < df['ema_21'])
        )
        
        # 2. Stochastic Overbought + MACD Cross Down
        short_stoch_macd = (
            (df['stoch_k'] > 80) &
            (df['macd_hist'] < df['macd_hist'].shift(1)) &
            (df['macd_hist'].shift(1) > 0)
        )
        
        # 3. Bollinger Upper + Volume Spike
        short_bb_volume = (
            (df['close'] > df['bb_upper'] * 0.99) &
            (df['volume_ratio'] > 1.5) &
            (df['rsi'] > 65)
        )
        
        # Объединяем SHORT сигналы
        df.loc[short_rsi_ema, 'signal'] = -1
        df.loc[short_rsi_ema, 'signal_strength'] = 0.7
        
        df.loc[short_stoch_macd, 'signal'] = -1
        df.loc[short_stoch_macd, 'signal_strength'] = 0.85
        
        df.loc[short_bb_volume, 'signal'] = -1
        df.loc[short_bb_volume, 'signal_strength'] = 0.75
        
        # Динамический SL/TP на основе ATR
        df['sl_pct'] = df['atr_pct'] * 2  # 2 ATR для SL
        df['tp_pct'] = df['atr_pct'] * 3  # 3 ATR для TP
        
        # Минимальные значения
        df['sl_pct'] = df['sl_pct'].clip(lower=0.3, upper=2.0)
        df['tp_pct'] = df['tp_pct'].clip(lower=0.5, upper=3.0)
        
        return df
    
    def simulate_trades(
        self, 
        df: pd.DataFrame, 
        symbol: str,
        leverage: int,
        initial_balance: float
    ) -> Tuple[List[TradeResult], List[float]]:
        """Симуляция торговли с полным учётом комиссий"""
        
        trades = []
        balance_history = [initial_balance]
        balance = initial_balance
        position = None
        
        # Пропускаем первые свечи для прогрева индикаторов
        start_idx = 60
        
        for i in range(start_idx, len(df)):
            row = df.iloc[i]
            current_price = row['close']
            signal = row['signal']
            
            # =====================================
            # ПРОВЕРКА ОТКРЫТОЙ ПОЗИЦИИ
            # =====================================
            if position:
                entry_price = position['entry_price']
                direction = position['direction']
                margin = position['margin']
                position_size = position['position_size']
                
                # Расчёт текущего PnL
                if direction == "LONG":
                    pnl_pct = (current_price - entry_price) / entry_price * 100
                else:  # SHORT
                    pnl_pct = (entry_price - current_price) / entry_price * 100
                
                pnl_pct_leveraged = pnl_pct * leverage
                
                # Время в позиции
                bars_in_position = i - position['entry_idx']
                hours_in_position = bars_in_position * 0.25  # 15 мин = 0.25 часа
                
                exit_reason = None
                exit_price = current_price
                
                # 1. ПРОВЕРКА ЛИКВИДАЦИИ
                # Ликвидация при потере 90% маржи
                if pnl_pct_leveraged <= -90:
                    exit_reason = "LIQUIDATION"
                    # При ликвидации теряем почти всю маржу
                    exit_price = entry_price * (1 - 0.9 / leverage) if direction == "LONG" else entry_price * (1 + 0.9 / leverage)
                
                # 2. ПРОВЕРКА SL
                elif pnl_pct <= -position['sl_pct']:
                    exit_reason = "STOP_LOSS"
                    if direction == "LONG":
                        exit_price = entry_price * (1 - position['sl_pct'] / 100)
                    else:
                        exit_price = entry_price * (1 + position['sl_pct'] / 100)
                
                # 3. ПРОВЕРКА TP
                elif pnl_pct >= position['tp_pct']:
                    exit_reason = "TAKE_PROFIT"
                    if direction == "LONG":
                        exit_price = entry_price * (1 + position['tp_pct'] / 100)
                    else:
                        exit_price = entry_price * (1 - position['tp_pct'] / 100)
                
                # 4. ПРОВЕРКА ТАЙМАУТА
                elif hours_in_position >= self.config.max_hold_hours:
                    exit_reason = "TIMEOUT"
                
                # ЗАКРЫТИЕ ПОЗИЦИИ
                if exit_reason:
                    trade = self._close_position(
                        position=position,
                        exit_price=exit_price,
                        exit_idx=i,
                        leverage=leverage,
                        exit_reason=exit_reason,
                        hours_in_position=hours_in_position
                    )
                    trades.append(trade)
                    
                    # Обновляем баланс
                    if trade.liquidated:
                        balance = balance - margin * 0.95  # Теряем 95% маржи
                    else:
                        balance += trade.pnl_net
                    
                    balance = max(balance, 0)  # Не может быть отрицательным
                    balance_history.append(balance)
                    position = None
                    
                    continue
            
            # =====================================
            # ОТКРЫТИЕ НОВОЙ ПОЗИЦИИ
            # =====================================
            if position is None and signal != 0 and balance > 20:
                # Размер маржи: 15% от баланса
                margin = balance * self.config.position_size_pct
                position_size = margin * leverage
                
                # Комиссия на открытие
                open_commission = position_size * self.config.taker_fee
                
                position = {
                    'symbol': symbol,
                    'direction': "LONG" if signal == 1 else "SHORT",
                    'entry_price': current_price,
                    'entry_idx': i,
                    'margin': margin,
                    'position_size': position_size,
                    'sl_pct': row['sl_pct'],
                    'tp_pct': row['tp_pct'],
                    'open_commission': open_commission,
                }
        
        # Закрываем оставшуюся позицию
        if position:
            last_row = df.iloc[-1]
            hours_in_position = (len(df) - position['entry_idx']) * 0.25
            
            trade = self._close_position(
                position=position,
                exit_price=last_row['close'],
                exit_idx=len(df) - 1,
                leverage=leverage,
                exit_reason="END_OF_DATA",
                hours_in_position=hours_in_position
            )
            trades.append(trade)
            balance += trade.pnl_net
            balance_history.append(balance)
        
        return trades, balance_history
    
    def _close_position(
        self, 
        position: Dict, 
        exit_price: float,
        exit_idx: int,
        leverage: int,
        exit_reason: str,
        hours_in_position: float
    ) -> TradeResult:
        """Закрыть позицию и рассчитать результат с ВСЕМИ комиссиями"""
        
        entry_price = position['entry_price']
        direction = position['direction']
        margin = position['margin']
        position_size = position['position_size']
        
        # 1. PnL до комиссий (gross)
        if direction == "LONG":
            price_change_pct = (exit_price - entry_price) / entry_price
        else:
            price_change_pct = (entry_price - exit_price) / entry_price
        
        pnl_gross = position_size * price_change_pct
        
        # 2. Комиссии
        # Открытие (уже посчитана)
        open_commission = position.get('open_commission', position_size * self.config.taker_fee)
        
        # Закрытие
        close_commission = position_size * self.config.taker_fee
        
        total_commission = open_commission + close_commission
        
        # 3. Funding Rate
        # Каждые 8 часов платим funding
        funding_periods = hours_in_position / 8
        funding_paid = position_size * self.config.avg_funding_rate * funding_periods
        
        # 4. Проскальзывание (примерно 0.01%)
        slippage = position_size * 0.0001
        
        # 5. Чистый PnL
        liquidated = exit_reason == "LIQUIDATION"
        
        if liquidated:
            # При ликвидации теряем 95% маржи
            pnl_net = -margin * 0.95
        else:
            pnl_net = pnl_gross - total_commission - funding_paid - slippage
        
        # PnL в процентах от маржи
        pnl_pct = (pnl_net / margin) * 100 if margin > 0 else 0
        
        return TradeResult(
            symbol=position['symbol'],
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            leverage=leverage,
            margin_used=margin,
            position_size=position_size,
            pnl_gross=pnl_gross,
            commission=total_commission,
            funding_paid=funding_paid,
            pnl_net=pnl_net,
            pnl_pct=pnl_pct,
            hold_time_hours=hours_in_position,
            exit_reason=exit_reason,
            liquidated=liquidated
        )
    
    def calculate_metrics(
        self,
        symbol: str,
        leverage: int,
        trades: List[TradeResult],
        balance_history: List[float],
        initial_balance: float,
        total_days: float
    ) -> BacktestResult:
        """Рассчитать метрики"""
        
        if not trades:
            return BacktestResult(
                symbol=symbol, leverage=leverage,
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0, gross_pnl=0, total_commissions=0,
                total_funding=0, net_pnl=0, net_pnl_percent=0,
                max_drawdown=0, sharpe_ratio=0, liquidations=0,
                avg_trade_duration=0, best_trade=0, worst_trade=0,
                profit_factor=0, final_balance=initial_balance,
                trades_per_day=0
            )
        
        winning = [t for t in trades if t.pnl_net > 0]
        losing = [t for t in trades if t.pnl_net <= 0]
        liquidations = [t for t in trades if t.liquidated]
        
        gross_pnl = sum(t.pnl_gross for t in trades)
        total_commission = sum(t.commission for t in trades)
        total_funding = sum(t.funding_paid for t in trades)
        net_pnl = sum(t.pnl_net for t in trades)
        
        final_balance = balance_history[-1] if balance_history else initial_balance
        
        # Max Drawdown
        peak = balance_history[0]
        max_dd = 0
        for balance in balance_history:
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        # Sharpe Ratio
        returns = [t.pnl_pct for t in trades]
        if returns and len(returns) > 1 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(365)
        else:
            sharpe = 0
        
        # Profit Factor
        gross_profit = sum(t.pnl_net for t in winning) if winning else 0
        gross_loss = abs(sum(t.pnl_net for t in losing)) if losing else 0.01
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return BacktestResult(
            symbol=symbol,
            leverage=leverage,
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=len(winning) / len(trades) * 100 if trades else 0,
            gross_pnl=round(gross_pnl, 2),
            total_commissions=round(total_commission, 2),
            total_funding=round(total_funding, 2),
            net_pnl=round(net_pnl, 2),
            net_pnl_percent=round(net_pnl / initial_balance * 100, 2),
            max_drawdown=round(max_dd * 100, 2),
            sharpe_ratio=round(sharpe, 2),
            liquidations=len(liquidations),
            avg_trade_duration=round(np.mean([t.hold_time_hours for t in trades]), 2),
            best_trade=round(max(t.pnl_net for t in trades), 2),
            worst_trade=round(min(t.pnl_net for t in trades), 2),
            profit_factor=round(profit_factor, 2),
            final_balance=round(final_balance, 2),
            trades_per_day=round(len(trades) / total_days, 2) if total_days > 0 else 0
        )
    
    async def run_backtest(self, symbols: List[str] = None, days: int = 180) -> Dict:
        """Запустить полный бэктест"""
        
        if symbols is None:
            symbols = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT"]
        
        print("=" * 80)
        print("📊 БЭКТЕСТ С ПЛЕЧАМИ И РЕАЛЬНЫМИ КОМИССИЯМИ BYBIT")
        print("=" * 80)
        print(f"⏰ Начало: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"💰 Начальный депозит: ${self.config.initial_balance}")
        print(f"📈 Плечи для теста: {self.config.leverages}")
        print(f"🪙 Монеты: {', '.join(symbols)}")
        print(f"📅 Период: {days} дней")
        print()
        print("💸 КОМИССИИ BYBIT:")
        print(f"   Taker Fee: {self.config.taker_fee * 100:.3f}%")
        print(f"   Maker Fee: {self.config.maker_fee * 100:.3f}%")
        print(f"   Avg Funding Rate: {self.config.avg_funding_rate * 100:.3f}% каждые 8ч")
        print("=" * 80)
        
        all_results = {}
        
        async with aiohttp.ClientSession() as session:
            self.session = session
            
            for symbol in symbols:
                print(f"\n{'='*60}")
                print(f"🪙 {symbol}")
                print("=" * 60)
                
                # Загружаем данные
                df = await self.fetch_historical_data(symbol, days=days)
                
                if df.empty or len(df) < 500:
                    print(f"   ❌ Недостаточно данных для {symbol}")
                    continue
                
                # Рассчитываем индикаторы
                df = self.calculate_indicators(df)
                
                # Генерируем сигналы
                df = self.generate_signals(df)
                
                signal_count = (df['signal'] != 0).sum()
                print(f"   📊 Свечей: {len(df)} | Сигналов: {signal_count}")
                
                symbol_results = {}
                
                for leverage in self.config.leverages:
                    print(f"\n   📊 Тест {leverage}x плеча...")
                    
                    trades, balance_history = self.simulate_trades(
                        df, symbol, leverage, self.config.initial_balance
                    )
                    
                    result = self.calculate_metrics(
                        symbol, leverage, trades, balance_history,
                        self.config.initial_balance, days
                    )
                    
                    symbol_results[leverage] = result
                    
                    # Вывод результата
                    if result.net_pnl > 0:
                        emoji = "✅"
                    elif result.liquidations > 0:
                        emoji = "💀"
                    else:
                        emoji = "❌"
                    
                    print(f"      {emoji} {leverage}x: ${result.net_pnl:+.2f} ({result.net_pnl_percent:+.1f}%)")
                    print(f"         Сделок: {result.total_trades} | Win Rate: {result.win_rate:.1f}%")
                    print(f"         Комиссии: ${result.total_commissions:.2f} | Funding: ${result.total_funding:.2f}")
                    print(f"         Max DD: {result.max_drawdown:.1f}% | Ликвидаций: {result.liquidations}")
                    print(f"         Финальный баланс: ${result.final_balance:.2f}")
                
                all_results[symbol] = symbol_results
                
                await asyncio.sleep(0.3)
        
        # Итоговый отчёт
        self._print_summary(all_results)
        
        # Сохраняем результаты
        self._save_results(all_results)
        
        return all_results
    
    def _print_summary(self, all_results: Dict):
        """Итоговый отчёт"""
        
        print("\n" + "=" * 80)
        print("📋 ИТОГОВЫЙ ОТЧЁТ")
        print("=" * 80)
        
        # ==========================================
        # Лучшее плечо для каждой монеты
        # ==========================================
        print("\n🏆 ЛУЧШЕЕ ПЛЕЧО ДЛЯ КАЖДОЙ МОНЕТЫ (с учётом риска):")
        print("-" * 60)
        
        recommendations = {}
        
        for symbol, leverage_results in all_results.items():
            best_leverage = None
            best_score = float('-inf')
            
            for leverage, result in leverage_results.items():
                # Скоринг с учётом риска
                # Штраф за liquidations (критично!)
                # Штраф за высокий drawdown
                # Бонус за profit factor
                
                score = result.net_pnl
                score -= result.liquidations * 200      # Сильный штраф за ликвидации
                score -= result.max_drawdown * 3        # Штраф за просадку
                score += result.profit_factor * 20     # Бонус за profit factor
                score += result.win_rate * 0.5         # Небольшой бонус за win rate
                
                if score > best_score:
                    best_score = score
                    best_leverage = leverage
            
            if best_leverage:
                result = leverage_results[best_leverage]
                recommendations[symbol] = {
                    'leverage': best_leverage,
                    'result': result
                }
                
                if result.net_pnl > 0 and result.liquidations == 0:
                    emoji = "✅"
                elif result.liquidations > 0:
                    emoji = "💀"
                else:
                    emoji = "⚠️"
                
                print(f"{emoji} {symbol:6} → {best_leverage}x плечо")
                print(f"         Net PnL: ${result.net_pnl:+.2f} ({result.net_pnl_percent:+.1f}%)")
                print(f"         WR: {result.win_rate:.0f}% | DD: {result.max_drawdown:.0f}% | Liqs: {result.liquidations}")
        
        # ==========================================
        # Общая статистика по плечам
        # ==========================================
        print("\n" + "-" * 60)
        print("📊 ОБЩАЯ СТАТИСТИКА ПО ПЛЕЧАМ (все монеты):")
        print("-" * 60)
        
        leverage_summary = {}
        
        for leverage in self.config.leverages:
            total_pnl = 0
            total_trades = 0
            total_liquidations = 0
            total_commissions = 0
            total_funding = 0
            profitable_coins = 0
            
            for symbol, leverage_results in all_results.items():
                if leverage in leverage_results:
                    result = leverage_results[leverage]
                    total_pnl += result.net_pnl
                    total_trades += result.total_trades
                    total_liquidations += result.liquidations
                    total_commissions += result.total_commissions
                    total_funding += result.total_funding
                    if result.net_pnl > 0:
                        profitable_coins += 1
            
            leverage_summary[leverage] = {
                'pnl': total_pnl,
                'trades': total_trades,
                'liquidations': total_liquidations,
                'commissions': total_commissions,
                'funding': total_funding,
                'profitable': profitable_coins
            }
            
            if total_pnl > 0 and total_liquidations == 0:
                emoji = "✅"
            elif total_liquidations > 0:
                emoji = "💀"
            else:
                emoji = "❌"
            
            total_fees = total_commissions + total_funding
            print(f"{emoji} {leverage}x: Net ${total_pnl:+.2f}")
            print(f"      Сделок: {total_trades} | Liqs: {total_liquidations} | Профитных: {profitable_coins}/{len(all_results)}")
            print(f"      Комиссии: ${total_commissions:.2f} | Funding: ${total_funding:.2f} | Всего: ${total_fees:.2f}")
        
        # ==========================================
        # Влияние комиссий
        # ==========================================
        print("\n" + "-" * 60)
        print("💸 ВЛИЯНИЕ КОМИССИЙ НА ПРИБЫЛЬ:")
        print("-" * 60)
        
        for leverage in self.config.leverages:
            summary = leverage_summary[leverage]
            
            gross_pnl = 0
            for symbol, results in all_results.items():
                if leverage in results:
                    gross_pnl += results[leverage].gross_pnl
            
            total_fees = summary['commissions'] + summary['funding']
            fee_impact = (total_fees / abs(gross_pnl) * 100) if gross_pnl != 0 else 0
            
            print(f"   {leverage}x: Gross ${gross_pnl:+.2f} → Net ${summary['pnl']:+.2f}")
            print(f"       Комиссии съели: ${total_fees:.2f} ({fee_impact:.1f}% от движения)")
        
        # ==========================================
        # Рекомендации
        # ==========================================
        print("\n" + "=" * 80)
        print("💡 РЕКОМЕНДАЦИИ:")
        print("=" * 80)
        
        # Безопасные
        safe_coins = [
            s for s, r in recommendations.items() 
            if r['leverage'] <= 3 and r['result'].net_pnl > 0 and r['result'].liquidations == 0
        ]
        
        # С осторожностью (средний риск)
        medium_risk = [
            s for s, r in recommendations.items() 
            if r['leverage'] in [3, 5] and r['result'].liquidations == 0
        ]
        
        # Рискованные (высокое плечо)
        risky_coins = [
            s for s, r in recommendations.items() 
            if r['leverage'] >= 5 and r['result'].liquidations == 0
        ]
        
        # Опасные (были ликвидации)
        danger_coins = [
            s for s, r in recommendations.items() 
            if r['result'].liquidations > 0
        ]
        
        # Убыточные
        unprofitable = [
            s for s, r in recommendations.items() 
            if r['result'].net_pnl < 0
        ]
        
        if safe_coins:
            print(f"✅ Безопасные (1-2x, прибыль): {', '.join(safe_coins)}")
        if medium_risk:
            print(f"⚠️ Средний риск (3-5x): {', '.join(medium_risk)}")
        if risky_coins:
            print(f"🔶 Высокий риск (5x+): {', '.join(risky_coins)}")
        if danger_coins:
            print(f"💀 ОПАСНО (были ликвидации!): {', '.join(danger_coins)}")
        if unprofitable:
            print(f"❌ Убыточные: {', '.join(unprofitable)}")
        
        # Итоговая рекомендация
        print("\n" + "-" * 60)
        
        best_leverage_overall = min(
            leverage_summary.keys(),
            key=lambda l: (
                leverage_summary[l]['liquidations'] * 1000 - 
                leverage_summary[l]['pnl'] + 
                leverage_summary[l]['commissions']
            )
        )
        
        best_summary = leverage_summary[best_leverage_overall]
        
        print(f"🎯 ЛУЧШЕЕ ПЛЕЧО OVERALL: {best_leverage_overall}x")
        print(f"   Net PnL: ${best_summary['pnl']:+.2f}")
        print(f"   Ликвидаций: {best_summary['liquidations']}")
        print(f"   Профитных монет: {best_summary['profitable']}/{len(all_results)}")
        
        print("\n" + "=" * 80)
        print(f"⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
    
    def _save_results(self, all_results: Dict):
        """Сохранить результаты в файл"""
        
        report_dir = Path("/root/crypto-bot/reports")
        report_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = report_dir / f"leverage_backtest_{timestamp}.json"
        
        # Конвертируем в сериализуемый формат
        serializable = {}
        for symbol, leverage_results in all_results.items():
            serializable[symbol] = {}
            for leverage, result in leverage_results.items():
                serializable[symbol][str(leverage)] = {
                    'leverage': result.leverage,
                    'total_trades': result.total_trades,
                    'winning_trades': result.winning_trades,
                    'losing_trades': result.losing_trades,
                    'win_rate': result.win_rate,
                    'gross_pnl': result.gross_pnl,
                    'total_commissions': result.total_commissions,
                    'total_funding': result.total_funding,
                    'net_pnl': result.net_pnl,
                    'net_pnl_percent': result.net_pnl_percent,
                    'max_drawdown': result.max_drawdown,
                    'sharpe_ratio': result.sharpe_ratio,
                    'liquidations': result.liquidations,
                    'avg_trade_duration': result.avg_trade_duration,
                    'best_trade': result.best_trade,
                    'worst_trade': result.worst_trade,
                    'profit_factor': result.profit_factor,
                    'final_balance': result.final_balance,
                    'trades_per_day': result.trades_per_day
                }
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'config': {
                'initial_balance': self.config.initial_balance,
                'leverages': self.config.leverages,
                'taker_fee': self.config.taker_fee,
                'maker_fee': self.config.maker_fee,
                'avg_funding_rate': self.config.avg_funding_rate,
            },
            'results': serializable
        }
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n💾 Результаты сохранены: {report_file}")


async def run_leverage_backtest():
    """Запустить бэктест"""
    
    config = BacktestConfig(
        initial_balance=1000,
        leverages=[1, 2, 3, 5, 10],
        taker_fee=0.00055,      # 0.055%
        maker_fee=0.0002,       # 0.02%
        avg_funding_rate=0.0001, # 0.01% каждые 8ч
        position_size_pct=0.15,  # 15% на сделку
        max_hold_hours=24,       # Макс 24ч в позиции
    )
    
    backtester = LeverageBacktester(config)
    
    symbols = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT"]
    
    results = await backtester.run_backtest(symbols=symbols, days=180)
    
    return results


if __name__ == "__main__":
    asyncio.run(run_leverage_backtest())
