"""
💰 FUNDING SCALPER MODULE
Торговля на аномальном Funding Rate

Логика:
- Funding > +0.05% → много лонгов → SHORT (против толпы)
- Funding < -0.05% → много шортов → LONG (против толпы)
- Бонус: получаем Funding payment каждые 8 часов!

Timing:
- Funding начисляется: 00:00, 08:00, 16:00 UTC
- Входим за 30-60 мин до начисления
- Выходим после начисления или по TP/SL
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import aiohttp

from app.core.logger import logger
from app.modules.base_module import BaseModule, ModuleSignal


class FundingSignalType(Enum):
    EXTREME_POSITIVE = "extreme_positive"   # > 0.1% → Strong SHORT
    HIGH_POSITIVE = "high_positive"         # > 0.05% → SHORT
    EXTREME_NEGATIVE = "extreme_negative"   # < -0.1% → Strong LONG
    HIGH_NEGATIVE = "high_negative"         # < -0.05% → LONG
    NEUTRAL = "neutral"                     # -0.05% to +0.05%


@dataclass
class FundingData:
    """Данные Funding Rate для монеты"""
    symbol: str
    funding_rate: float              # Текущий rate (0.0001 = 0.01%)
    funding_rate_percent: float      # В процентах
    next_funding_time: datetime      # Когда следующее начисление
    minutes_to_funding: int          # Минут до начисления
    predicted_rate: float = 0.0      # Предсказанный rate
    signal_type: FundingSignalType = FundingSignalType.NEUTRAL
    
    def __post_init__(self):
        # Определяем тип сигнала
        if self.funding_rate_percent >= 0.1:
            self.signal_type = FundingSignalType.EXTREME_POSITIVE
        elif self.funding_rate_percent >= 0.05:
            self.signal_type = FundingSignalType.HIGH_POSITIVE
        elif self.funding_rate_percent <= -0.1:
            self.signal_type = FundingSignalType.EXTREME_NEGATIVE
        elif self.funding_rate_percent <= -0.05:
            self.signal_type = FundingSignalType.HIGH_NEGATIVE
        else:
            self.signal_type = FundingSignalType.NEUTRAL


@dataclass
class FundingTrade:
    """Сделка Funding Scalper"""
    id: str
    symbol: str
    direction: str                   # LONG или SHORT
    entry_price: float
    current_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    funding_rate: float = 0.0        # Rate при входе
    funding_collected: float = 0.0   # Собранный funding
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    status: str = "open"             # open, closed
    pnl_percent: float = 0.0
    pnl_usdt: float = 0.0


@dataclass
class FundingConfig:
    """Конфигурация Funding Scalper"""
    enabled: bool = True
    
    # Пороги для сигналов
    extreme_threshold: float = 0.1    # > 0.1% = экстремальный
    high_threshold: float = 0.05      # > 0.05% = высокий
    
    # Timing
    entry_minutes_before: int = 45    # Входить за 45 мин до funding
    min_minutes_before: int = 10      # Минимум 10 мин до funding
    max_hold_hours: int = 4           # Максимум держать 4 часа
    
    # Risk management
    sl_percent: float = 1.0           # Stop Loss 1%
    tp_percent: float = 1.5           # Take Profit 1.5%
    position_size_usdt: float = 200   # Размер позиции
    
    # Extreme signals (увеличенные позиции)
    extreme_size_multiplier: float = 1.5  # x1.5 для экстремальных
    
    # Лимиты
    max_positions: int = 3            # Макс одновременных позиций
    cooldown_hours: int = 8           # Кулдаун между сделками на символ


class FundingScalper(BaseModule):
    """
    💰 Funding Scalper
    
    Торгует против толпы когда Funding Rate экстремальный.
    Получает Funding payment как бонус!
    
    Timing (UTC):
    - 00:00 - Funding #1
    - 08:00 - Funding #2  
    - 16:00 - Funding #3
    """
    
    name = "funding_scalper"
    
    # Символы для мониторинга (фьючерсы)
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", 
               "ADAUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT"]
    
    # Funding times (UTC)
    FUNDING_HOURS = [0, 8, 16]
    
    def __init__(self):
        self.enabled = True
        self.config = FundingConfig()
        
        # Кэш funding rates
        self.funding_cache: Dict[str, FundingData] = {}
        self.last_update: Optional[datetime] = None
        
        # Активные позиции
        self.positions: Dict[str, FundingTrade] = {}
        
        # История
        self.history: List[FundingTrade] = []
        
        # Статистика
        self.stats = {
            "total_trades": 0,
            "winning_trades": 0,
            "total_pnl_usdt": 0.0,
            "total_funding_collected": 0.0,
            "today_trades": 0,
            "today_pnl_usdt": 0.0,
        }
        
        # Кулдаун (symbol -> last trade time)
        self.cooldowns: Dict[str, datetime] = {}
        
        # Paper trading
        self.paper_trading = True
        
        logger.info("💰 Funding Scalper initialized")
    
    def _get_next_funding_time(self) -> datetime:
        """Получить время следующего funding"""
        now = datetime.now(timezone.utc)
        
        for hour in self.FUNDING_HOURS:
            funding_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            if funding_time > now:
                return funding_time
        
        # Следующий день 00:00
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    
    def _minutes_to_next_funding(self) -> int:
        """Минут до следующего funding"""
        next_funding = self._get_next_funding_time()
        now = datetime.now(timezone.utc)
        delta = next_funding - now
        return int(delta.total_seconds() / 60)
    
    async def fetch_funding_rates(self) -> Dict[str, FundingData]:
        """Получить Funding Rates с Bybit"""
        
        funding_data = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                # Bybit V5 API - Tickers
                url = "https://api.bybit.com/v5/market/tickers"
                params = {"category": "linear"}
                
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("retCode") == 0:
                            tickers = data.get("result", {}).get("list", [])
                            
                            next_funding = self._get_next_funding_time()
                            minutes_to = self._minutes_to_next_funding()
                            
                            for ticker in tickers:
                                symbol = ticker.get("symbol", "")
                                
                                if symbol not in self.SYMBOLS:
                                    continue
                                
                                funding_rate = float(ticker.get("fundingRate", 0))
                                funding_percent = funding_rate * 100
                                
                                funding_data[symbol] = FundingData(
                                    symbol=symbol,
                                    funding_rate=funding_rate,
                                    funding_rate_percent=funding_percent,
                                    next_funding_time=next_funding,
                                    minutes_to_funding=minutes_to,
                                )
                            
                            logger.debug(f"💰 Fetched funding for {len(funding_data)} symbols")
        
        except Exception as e:
            logger.error(f"Funding fetch error: {e}")
        
        self.funding_cache = funding_data
        self.last_update = datetime.now()
        
        return funding_data
    
    def _should_enter(self, funding: FundingData) -> Tuple[bool, str, str]:
        """
        Проверить нужно ли входить в позицию
        Returns: (should_enter, direction, reason)
        """
        
        # Проверяем timing
        if funding.minutes_to_funding > self.config.entry_minutes_before:
            return False, "", "Too early"
        
        if funding.minutes_to_funding < self.config.min_minutes_before:
            return False, "", "Too late"
        
        # Проверяем кулдаун
        if funding.symbol in self.cooldowns:
            cooldown_until = self.cooldowns[funding.symbol] + timedelta(hours=self.config.cooldown_hours)
            if datetime.now() < cooldown_until:
                return False, "", "Cooldown"
        
        # Проверяем лимит позиций
        if len(self.positions) >= self.config.max_positions:
            return False, "", "Max positions"
        
        # Уже есть позиция по этому символу?
        if funding.symbol in self.positions:
            return False, "", "Position exists"
        
        # Проверяем сигнал
        if funding.signal_type == FundingSignalType.EXTREME_POSITIVE:
            return True, "SHORT", f"Extreme positive funding {funding.funding_rate_percent:.3f}%"
        
        elif funding.signal_type == FundingSignalType.HIGH_POSITIVE:
            return True, "SHORT", f"High positive funding {funding.funding_rate_percent:.3f}%"
        
        elif funding.signal_type == FundingSignalType.EXTREME_NEGATIVE:
            return True, "LONG", f"Extreme negative funding {funding.funding_rate_percent:.3f}%"
        
        elif funding.signal_type == FundingSignalType.HIGH_NEGATIVE:
            return True, "LONG", f"High negative funding {funding.funding_rate_percent:.3f}%"
        
        return False, "", "Neutral funding"
    
    async def check_entries(self, prices: Dict[str, float]) -> List[ModuleSignal]:
        """Проверить возможные входы"""
        
        signals = []
        
        # Обновляем funding rates (каждые 5 мин)
        if not self.last_update or (datetime.now() - self.last_update).seconds > 300:
            await self.fetch_funding_rates()
        
        for symbol, funding in self.funding_cache.items():
            should_enter, direction, reason = self._should_enter(funding)
            
            if not should_enter:
                continue
            
            # Получаем цену
            price = prices.get(symbol, 0)
            if price == 0:
                price = prices.get(symbol.replace("USDT", ""), 0)
            
            if price == 0:
                logger.warning(f"No price for {symbol}")
                continue
            
            # Рассчитываем SL/TP
            if direction == "LONG":
                sl = price * (1 - self.config.sl_percent / 100)
                tp = price * (1 + self.config.tp_percent / 100)
            else:
                sl = price * (1 + self.config.sl_percent / 100)
                tp = price * (1 - self.config.tp_percent / 100)
            
            # Размер позиции
            size = self.config.position_size_usdt
            if funding.signal_type in [FundingSignalType.EXTREME_POSITIVE, 
                                       FundingSignalType.EXTREME_NEGATIVE]:
                size *= self.config.extreme_size_multiplier
            
            # Создаём сигнал
            signal = ModuleSignal(
                module_name=self.name,
                symbol=symbol.replace("USDT", ""),
                direction=direction,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
                reason=reason,
                confidence=0.75 if "Extreme" in reason else 0.65,
            )
            
            signals.append(signal)
            
            # Создаём виртуальную позицию (paper trading)
            if self.paper_trading:
                trade = FundingTrade(
                    id=f"F_{symbol}_{datetime.now().strftime('%H%M%S')}",
                    symbol=symbol,
                    direction=direction,
                    entry_price=price,
                    current_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    funding_rate=funding.funding_rate_percent,
                )
                self.positions[symbol] = trade
                self.cooldowns[symbol] = datetime.now()
                
                logger.info(f"💰 Funding entry: {direction} {symbol} @ {price:.2f} "
                           f"(Funding: {funding.funding_rate_percent:.3f}%)")
        
        return signals
    
    async def check_exits(self, prices: Dict[str, float]) -> List[ModuleSignal]:
        """Проверить выходы из позиций"""
        
        signals = []
        closed_positions = []
        
        for symbol, trade in self.positions.items():
            # Получаем цену
            price = prices.get(symbol, 0)
            if price == 0:
                price = prices.get(symbol.replace("USDT", ""), 0)
            
            if price == 0:
                continue
            
            trade.current_price = price
            
            should_close = False
            close_reason = ""
            
            # Проверяем SL/TP
            if trade.direction == "LONG":
                trade.pnl_percent = (price - trade.entry_price) / trade.entry_price * 100
                
                if price <= trade.stop_loss:
                    should_close = True
                    close_reason = "Stop Loss"
                elif price >= trade.take_profit:
                    should_close = True
                    close_reason = "Take Profit"
            
            else:  # SHORT
                trade.pnl_percent = (trade.entry_price - price) / trade.entry_price * 100
                
                if price >= trade.stop_loss:
                    should_close = True
                    close_reason = "Stop Loss"
                elif price <= trade.take_profit:
                    should_close = True
                    close_reason = "Take Profit"
            
            # Проверяем время (макс hold)
            hold_time = datetime.now() - trade.opened_at
            if hold_time > timedelta(hours=self.config.max_hold_hours):
                should_close = True
                close_reason = "Max hold time"
            
            # Проверяем прошёл ли funding
            minutes_to = self._minutes_to_next_funding()
            if minutes_to > 400:  # Значит funding только что прошёл
                # Добавляем funding к профиту
                if trade.direction == "SHORT" and trade.funding_rate > 0:
                    trade.funding_collected = trade.funding_rate
                elif trade.direction == "LONG" and trade.funding_rate < 0:
                    trade.funding_collected = abs(trade.funding_rate)
                
                # Закрываем после funding + небольшой профит
                if trade.pnl_percent > 0 or hold_time > timedelta(minutes=30):
                    should_close = True
                    close_reason = "Post-funding exit"
            
            if should_close:
                trade.status = "closed"
                trade.closed_at = datetime.now()
                trade.pnl_usdt = (trade.pnl_percent / 100) * self.config.position_size_usdt
                
                closed_positions.append(symbol)
                
                # Обновляем статистику
                self.stats["total_trades"] += 1
                self.stats["total_pnl_usdt"] += trade.pnl_usdt
                self.stats["total_funding_collected"] += trade.funding_collected
                
                if trade.pnl_percent > 0:
                    self.stats["winning_trades"] += 1
                
                if trade.closed_at.date() == datetime.now().date():
                    self.stats["today_trades"] += 1
                    self.stats["today_pnl_usdt"] += trade.pnl_usdt
                
                # В историю
                self.history.append(trade)
                
                # Сигнал о закрытии
                signal = ModuleSignal(
                    module_name=self.name,
                    symbol=trade.symbol.replace("USDT", ""),
                    direction=f"CLOSE_{trade.direction}",
                    entry_price=trade.current_price,
                    stop_loss=0,
                    take_profit=0,
                    reason=f"{close_reason} | PnL: {trade.pnl_percent:+.2f}%",
                )
                signals.append(signal)
                
                logger.info(f"💰 Funding exit: {trade.symbol} {close_reason} "
                           f"PnL: {trade.pnl_percent:+.2f}% (${trade.pnl_usdt:+.2f})")
        
        # Удаляем закрытые позиции
        for symbol in closed_positions:
            del self.positions[symbol]
        
        return signals
    
    async def get_signals(self, market_data: Dict) -> List[ModuleSignal]:
        """Получить сигналы от Funding Scalper"""
        
        if not self.enabled:
            return []
        
        prices = market_data.get("prices", {})
        
        signals = []
        
        # Проверяем выходы
        exit_signals = await self.check_exits(prices)
        signals.extend(exit_signals)
        
        # Проверяем входы
        entry_signals = await self.check_entries(prices)
        signals.extend(entry_signals)
        
        return signals
    
    async def get_status(self) -> Dict:
        """Статус Funding Scalper"""
        
        minutes_to = self._minutes_to_next_funding()
        next_funding = self._get_next_funding_time()
        
        # Топ funding rates
        top_rates = sorted(
            self.funding_cache.values(),
            key=lambda x: abs(x.funding_rate_percent),
            reverse=True
        )[:5]
        
        win_rate = 0
        if self.stats["total_trades"] > 0:
            win_rate = self.stats["winning_trades"] / self.stats["total_trades"] * 100
        
        return {
            "enabled": self.enabled,
            "next_funding_utc": next_funding.strftime("%H:%M"),
            "minutes_to_funding": minutes_to,
            "active_positions": len(self.positions),
            "positions": [
                {
                    "symbol": t.symbol,
                    "direction": t.direction,
                    "pnl_percent": t.pnl_percent,
                    "funding_rate": t.funding_rate,
                }
                for t in self.positions.values()
            ],
            "top_funding_rates": [
                {"symbol": f.symbol, "rate": f.funding_rate_percent}
                for f in top_rates
            ],
            "stats": {
                "total_trades": self.stats["total_trades"],
                "win_rate": win_rate,
                "total_pnl_usdt": self.stats["total_pnl_usdt"],
                "funding_collected": self.stats["total_funding_collected"],
                "today_trades": self.stats["today_trades"],
                "today_pnl_usdt": self.stats["today_pnl_usdt"],
            }
        }
    
    def get_status_text(self) -> str:
        """Текст для Telegram"""
        
        minutes_to = self._minutes_to_next_funding()
        next_funding = self._get_next_funding_time()
        
        # Win rate
        win_rate = 0
        if self.stats["total_trades"] > 0:
            win_rate = self.stats["winning_trades"] / self.stats["total_trades"] * 100
        
        # Топ rates
        top_rates = sorted(
            self.funding_cache.values(),
            key=lambda x: abs(x.funding_rate_percent),
            reverse=True
        )[:5]
        
        rates_text = ""
        for f in top_rates:
            emoji = "🔴" if f.funding_rate_percent > 0 else "🟢"
            rates_text += f"\n   {emoji} {f.symbol}: {f.funding_rate_percent:+.4f}%"
        
        if not rates_text:
            rates_text = "\n   Нет данных (обновляется каждые 5 мин)"
        
        # Позиции
        positions_text = ""
        if self.positions:
            for t in self.positions.values():
                emoji = "🟢" if t.direction == "LONG" else "🔴"
                pnl_emoji = "📈" if t.pnl_percent > 0 else "📉"
                positions_text += f"\n   {emoji} {t.symbol} {t.direction}: {pnl_emoji} {t.pnl_percent:+.2f}%"
        else:
            positions_text = "\n   Нет активных позиций"
        
        text = f"""
💰 *FUNDING SCALPER*

{'🟢 Активен' if self.enabled else '🔴 Остановлен'}

⏰ *Следующий Funding:*
├── Время: {next_funding.strftime('%H:%M')} UTC
└── Через: {minutes_to} мин

📊 *Топ Funding Rates:*{rates_text}

📈 *Позиции:*{positions_text}

📊 *Статистика:*
├── Сделок: {self.stats['total_trades']}
├── Win Rate: {win_rate:.1f}%
├── PnL: ${self.stats['total_pnl_usdt']:+.2f}
└── Funding собрано: ${self.stats['total_funding_collected']:.2f}

📅 *Сегодня:*
├── Сделок: {self.stats['today_trades']}
└── PnL: ${self.stats['today_pnl_usdt']:+.2f}
"""
        return text


# Синглтон
funding_scalper = FundingScalper()
