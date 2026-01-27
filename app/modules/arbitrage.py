"""
🔄 ARBITRAGE MODULE
Арбитраж на одной бирже (Bybit)

Типы арбитража:
1. Triangular - BTC → ETH → USDT → BTC (циклы на споте)
2. Spot-Futures - разница цен спот vs фьючерс
3. Cross-pair - разница между парами (BTC/USDT vs BTC/USDC)

Логика:
- Сканируем все пары каждые 10-30 сек
- Ищем прибыльные циклы (после комиссий!)
- Исполняем мгновенно (3 ордера за <1 сек)
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from itertools import permutations
import aiohttp

from app.core.logger import logger
from app.modules.base_module import BaseModule, ModuleSignal


@dataclass
class ArbitragePath:
    """Путь арбитража (цикл)"""
    path: List[str]              # ["USDT", "BTC", "ETH", "USDT"]
    pairs: List[str]             # ["BTCUSDT", "ETHBTC", "ETHUSDT"]
    sides: List[str]             # ["buy", "buy", "sell"]
    rates: List[float]           # Курсы
    profit_percent: float        # Профит в %
    profit_usdt: float           # Профит в USDT (при $100)
    volume_ok: bool              # Достаточный объём?
    execution_time_ms: int = 0   # Время исполнения


@dataclass
class ArbitrageConfig:
    """Конфигурация арбитража"""
    enabled: bool = True
    
    # Пороги
    min_profit_percent: float = 0.15   # Мин профит после комиссий
    min_profit_usdt: float = 0.10      # Мин профит в USDT
    
    # Комиссии Bybit Spot
    taker_fee: float = 0.1             # 0.1% taker
    maker_fee: float = 0.1             # 0.1% maker (не используем)
    
    # Размер сделки
    trade_size_usdt: float = 100       # Размер цикла
    max_trade_size_usdt: float = 500   # Максимум
    
    # Timing
    scan_interval_seconds: int = 15    # Сканировать каждые 15 сек
    
    # Лимиты
    max_daily_trades: int = 50         # Макс сделок в день
    cooldown_seconds: int = 30         # Пауза между сделками
    
    # Минимальный объём в стакане
    min_volume_usdt: float = 1000      # Мин объём для исполнения


@dataclass
class ArbitrageTrade:
    """Исполненная арбитражная сделка"""
    id: str
    path: List[str]
    pairs: List[str]
    profit_percent: float
    profit_usdt: float
    trade_size_usdt: float
    executed_at: datetime
    execution_time_ms: int
    success: bool
    error: Optional[str] = None


class ArbitrageScanner(BaseModule):
    """
    🔄 Арбитраж сканер
    
    Ищет прибыльные циклы на Bybit Spot:
    - USDT → BTC → ETH → USDT
    - USDT → ETH → BTC → USDT
    - и другие комбинации
    """
    
    name = "arbitrage"
    
    # Базовые валюты
    BASE_CURRENCIES = ["USDT", "BTC", "ETH"]
    
    # Монеты для арбитража
    COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LINK", "AVAX", "MATIC"]
    
    def __init__(self):
        self.enabled = True
        self.config = ArbitrageConfig()
        
        # Кэш цен
        self.prices: Dict[str, Dict] = {}  # {pair: {bid, ask, volume}}
        self.last_scan: Optional[datetime] = None
        
        # Доступные пары на Bybit
        self.available_pairs: Set[str] = set()
        
        # Найденные возможности
        self.opportunities: List[ArbitragePath] = []
        
        # История сделок
        self.trades: List[ArbitrageTrade] = []
        
        # Статистика
        self.stats = {
            "scans_total": 0,
            "opportunities_found": 0,
            "trades_executed": 0,
            "trades_success": 0,
            "total_profit_usdt": 0.0,
            "today_trades": 0,
            "today_profit_usdt": 0.0,
            "best_profit_percent": 0.0,
            "avg_execution_ms": 0,
        }
        
        # Кулдаун
        self.last_trade_time: Optional[datetime] = None
        
        # Paper trading
        self.paper_trading = True
        
        logger.info("🔄 Arbitrage Scanner initialized")
    
    async def fetch_available_pairs(self):
        """Получить список доступных пар на Bybit"""
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.bybit.com/v5/market/instruments-info"
                params = {"category": "spot"}
                
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("retCode") == 0:
                            instruments = data.get("result", {}).get("list", [])
                            
                            for inst in instruments:
                                symbol = inst.get("symbol", "")
                                status = inst.get("status", "")
                                
                                if status == "Trading":
                                    self.available_pairs.add(symbol)
                            
                            logger.info(f"🔄 Found {len(self.available_pairs)} trading pairs")
        
        except Exception as e:
            logger.error(f"Fetch pairs error: {e}")
    
    async def fetch_orderbook_prices(self):
        """Получить bid/ask цены из стаканов"""
        
        try:
            async with aiohttp.ClientSession() as session:
                # Получаем тикеры (там есть bid/ask)
                url = "https://api.bybit.com/v5/market/tickers"
                params = {"category": "spot"}
                
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("retCode") == 0:
                            tickers = data.get("result", {}).get("list", [])
                            
                            for ticker in tickers:
                                symbol = ticker.get("symbol", "")
                                
                                bid = float(ticker.get("bid1Price", 0) or 0)
                                ask = float(ticker.get("ask1Price", 0) or 0)
                                volume = float(ticker.get("volume24h", 0) or 0)
                                last_price = float(ticker.get("lastPrice", 0) or 0)
                                
                                if bid > 0 and ask > 0:
                                    self.prices[symbol] = {
                                        "bid": bid,
                                        "ask": ask,
                                        "mid": (bid + ask) / 2,
                                        "spread": (ask - bid) / bid * 100,
                                        "volume": volume,
                                        "last": last_price,
                                    }
                            
                            logger.debug(f"🔄 Updated prices for {len(self.prices)} pairs")
        
        except Exception as e:
            logger.error(f"Fetch prices error: {e}")
        
        self.last_scan = datetime.now()
    
    def _get_pair_and_side(self, from_coin: str, to_coin: str) -> Tuple[Optional[str], Optional[str], float]:
        """
        Найти пару и сторону для обмена from_coin → to_coin
        Returns: (pair, side, rate)
        
        Примеры:
        - USDT → BTC: пара BTCUSDT, side=buy, rate=1/ask
        - BTC → USDT: пара BTCUSDT, side=sell, rate=bid
        - BTC → ETH: пара ETHBTC, side=buy, rate=1/ask
        - ETH → BTC: пара ETHBTC, side=sell, rate=bid
        """
        
        # Прямая пара: to_coin + from_coin (например BTCUSDT для USDT→BTC)
        direct_pair = f"{to_coin}{from_coin}"
        if direct_pair in self.prices:
            price_data = self.prices[direct_pair]
            # Покупаем to_coin за from_coin
            return direct_pair, "buy", 1 / price_data["ask"]
        
        # Обратная пара: from_coin + to_coin (например BTCUSDT для BTC→USDT)
        reverse_pair = f"{from_coin}{to_coin}"
        if reverse_pair in self.prices:
            price_data = self.prices[reverse_pair]
            # Продаём from_coin за to_coin
            return reverse_pair, "sell", price_data["bid"]
        
        return None, None, 0
    
    def _calculate_triangular_profit(self, path: List[str]) -> Optional[ArbitragePath]:
        """
        Рассчитать профит треугольного арбитража
        path: ["USDT", "BTC", "ETH", "USDT"]
        """
        
        if len(path) < 4 or path[0] != path[-1]:
            return None
        
        pairs = []
        sides = []
        rates = []
        
        total_rate = 1.0
        total_fee = 0.0
        
        for i in range(len(path) - 1):
            from_coin = path[i]
            to_coin = path[i + 1]
            
            pair, side, rate = self._get_pair_and_side(from_coin, to_coin)
            
            if not pair or rate == 0:
                return None
            
            pairs.append(pair)
            sides.append(side)
            rates.append(rate)
            
            total_rate *= rate
            total_fee += self.config.taker_fee  # Комиссия на каждой сделке
        
        # Профит = (конечная сумма / начальная - 1) - комиссии
        profit_before_fees = (total_rate - 1) * 100
        profit_after_fees = profit_before_fees - total_fee
        
        # Профит в USDT при trade_size
        profit_usdt = (profit_after_fees / 100) * self.config.trade_size_usdt
        
        # Проверяем объём
        volume_ok = all(
            self.prices.get(p, {}).get("volume", 0) * self.prices.get(p, {}).get("last", 0) 
            > self.config.min_volume_usdt
            for p in pairs
        )
        
        return ArbitragePath(
            path=path,
            pairs=pairs,
            sides=sides,
            rates=rates,
            profit_percent=profit_after_fees,
            profit_usdt=profit_usdt,
            volume_ok=volume_ok,
        )
    
    def _find_triangular_opportunities(self) -> List[ArbitragePath]:
        """Найти все прибыльные треугольные арбитражи"""
        
        opportunities = []
        
        # Генерируем все возможные треугольники
        # Начинаем с USDT (основная валюта)
        start = "USDT"
        
        for coin1 in self.COINS:
            for coin2 in self.COINS:
                if coin1 == coin2:
                    continue
                
                # Путь: USDT → coin1 → coin2 → USDT
                path = [start, coin1, coin2, start]
                
                arb = self._calculate_triangular_profit(path)
                
                if arb and arb.profit_percent >= self.config.min_profit_percent:
                    if arb.volume_ok:
                        opportunities.append(arb)
        
        # Также проверяем через BTC и ETH как промежуточные
        for base in ["BTC", "ETH"]:
            for coin in self.COINS:
                if coin in ["BTC", "ETH"]:
                    continue
                
                # USDT → BTC → coin → USDT
                path = [start, base, coin, start]
                arb = self._calculate_triangular_profit(path)
                
                if arb and arb.profit_percent >= self.config.min_profit_percent:
                    if arb.volume_ok:
                        opportunities.append(arb)
        
        # Сортируем по профиту
        opportunities.sort(key=lambda x: x.profit_percent, reverse=True)
        
        return opportunities
    
    def _find_spot_futures_opportunities(self) -> List[ArbitragePath]:
        """
        Найти арбитраж Spot vs Futures
        (Требует данных фьючерсов - упрощённая версия)
        """
        # TODO: Реализовать когда добавим фьючерсы
        return []
    
    async def scan_opportunities(self) -> List[ArbitragePath]:
        """Сканировать все арбитражные возможности"""
        
        # Обновляем цены
        await self.fetch_orderbook_prices()
        
        if not self.prices:
            logger.warning("🔄 No prices available")
            return []
        
        self.stats["scans_total"] += 1
        
        # Ищем треугольный арбитраж
        triangular = self._find_triangular_opportunities()
        
        # Ищем spot-futures (TODO)
        # spot_futures = self._find_spot_futures_opportunities()
        
        all_opportunities = triangular
        
        if all_opportunities:
            self.stats["opportunities_found"] += len(all_opportunities)
            
            # Логируем лучшую возможность
            best = all_opportunities[0]
            logger.info(f"🔄 Best arb: {' → '.join(best.path)} = {best.profit_percent:+.3f}%")
        
        self.opportunities = all_opportunities
        
        return all_opportunities
    
    async def execute_arbitrage(self, arb: ArbitragePath) -> Optional[ArbitrageTrade]:
        """Исполнить арбитраж (paper trading)"""
        
        # Проверяем кулдаун
        if self.last_trade_time:
            elapsed = (datetime.now() - self.last_trade_time).seconds
            if elapsed < self.config.cooldown_seconds:
                return None
        
        # Проверяем дневной лимит
        if self.stats["today_trades"] >= self.config.max_daily_trades:
            logger.warning("🔄 Daily trade limit reached")
            return None
        
        start_time = datetime.now()
        
        trade = ArbitrageTrade(
            id=f"ARB_{start_time.strftime('%H%M%S%f')[:10]}",
            path=arb.path,
            pairs=arb.pairs,
            profit_percent=arb.profit_percent,
            profit_usdt=arb.profit_usdt,
            trade_size_usdt=self.config.trade_size_usdt,
            executed_at=start_time,
            execution_time_ms=0,
            success=True,
        )
        
        if self.paper_trading:
            # Симулируем исполнение
            await asyncio.sleep(0.1)  # ~100ms
            
            trade.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            trade.success = True
            
            logger.info(f"🔄 [PAPER] Executed: {' → '.join(arb.path)} "
                       f"+${arb.profit_usdt:.2f} ({arb.profit_percent:+.3f}%)")
        
        else:
            # TODO: Реальное исполнение через BybitClient
            # Нужно:
            # 1. Проверить балансы
            # 2. Выставить 3 market ордера последовательно
            # 3. Проверить исполнение
            pass
        
        # Обновляем статистику
        self.trades.append(trade)
        self.last_trade_time = datetime.now()
        
        self.stats["trades_executed"] += 1
        if trade.success:
            self.stats["trades_success"] += 1
            self.stats["total_profit_usdt"] += trade.profit_usdt
            
            if trade.profit_percent > self.stats["best_profit_percent"]:
                self.stats["best_profit_percent"] = trade.profit_percent
        
        if trade.executed_at.date() == datetime.now().date():
            self.stats["today_trades"] += 1
            self.stats["today_profit_usdt"] += trade.profit_usdt
        
        # Обновляем среднее время
        if self.stats["trades_executed"] > 0:
            total_ms = sum(t.execution_time_ms for t in self.trades)
            self.stats["avg_execution_ms"] = total_ms / len(self.trades)
        
        return trade
    
    async def get_signals(self, market_data: Dict) -> List[ModuleSignal]:
        """Получить сигналы от арбитража"""
        
        if not self.enabled:
            return []
        
        signals = []
        
        # Загружаем пары если нужно
        if not self.available_pairs:
            await self.fetch_available_pairs()
        
        # Сканируем возможности
        opportunities = await self.scan_opportunities()
        
        # Исполняем лучшую возможность
        if opportunities:
            best = opportunities[0]
            
            if best.profit_percent >= self.config.min_profit_percent:
                if best.profit_usdt >= self.config.min_profit_usdt:
                    
                    trade = await self.execute_arbitrage(best)
                    
                    if trade and trade.success:
                        signal = ModuleSignal(
                            module_name=self.name,
                            symbol="ARB",
                            direction="CYCLE",
                            entry_price=0,
                            stop_loss=0,
                            take_profit=0,
                            reason=f"{' → '.join(best.path)} = +${trade.profit_usdt:.2f}",
                            confidence=0.95,
                        )
                        signals.append(signal)
        
        return signals
    
    async def get_status(self) -> Dict:
        """Статус арбитража"""
        
        win_rate = 0
        if self.stats["trades_executed"] > 0:
            win_rate = self.stats["trades_success"] / self.stats["trades_executed"] * 100
        
        return {
            "enabled": self.enabled,
            "paper_trading": self.paper_trading,
            "available_pairs": len(self.available_pairs),
            "cached_prices": len(self.prices),
            "current_opportunities": len(self.opportunities),
            "best_opportunity": {
                "path": self.opportunities[0].path if self.opportunities else [],
                "profit": self.opportunities[0].profit_percent if self.opportunities else 0,
            },
            "stats": {
                "scans_total": self.stats["scans_total"],
                "opportunities_found": self.stats["opportunities_found"],
                "trades_executed": self.stats["trades_executed"],
                "win_rate": win_rate,
                "total_profit_usdt": self.stats["total_profit_usdt"],
                "best_profit_percent": self.stats["best_profit_percent"],
                "avg_execution_ms": self.stats["avg_execution_ms"],
                "today_trades": self.stats["today_trades"],
                "today_profit_usdt": self.stats["today_profit_usdt"],
            }
        }
    
    def get_status_text(self) -> str:
        """Текст для Telegram"""
        
        win_rate = 0
        if self.stats["trades_executed"] > 0:
            win_rate = self.stats["trades_success"] / self.stats["trades_executed"] * 100
        
        # Топ возможности
        top_opps = ""
        for i, opp in enumerate(self.opportunities[:3], 1):
            emoji = "🟢" if opp.profit_percent > 0.2 else "🟡"
            top_opps += f"\n   {emoji} {' → '.join(opp.path)}: {opp.profit_percent:+.3f}%"
        
        if not top_opps:
            top_opps = "\n   Нет прибыльных возможностей"
        
        mode = "📝 Paper" if self.paper_trading else "💰 Live"
        
        text = f"""
🔄 *ARBITRAGE SCANNER*

{'🟢 Активен' if self.enabled else '🔴 Остановлен'} | {mode}

📊 *Текущие возможности:*{top_opps}

📈 *Статистика:*
├── Сканирований: {self.stats['scans_total']}
├── Найдено возможностей: {self.stats['opportunities_found']}
├── Сделок: {self.stats['trades_executed']}
├── Win Rate: {win_rate:.1f}%
├── Лучший профит: {self.stats['best_profit_percent']:.3f}%
└── Среднее время: {self.stats['avg_execution_ms']:.0f}ms

💰 *Профит:*
├── Всего: ${self.stats['total_profit_usdt']:.2f}
└── Сегодня: ${self.stats['today_profit_usdt']:.2f}

⚙️ *Настройки:*
├── Мин профит: {self.config.min_profit_percent}%
├── Размер сделки: ${self.config.trade_size_usdt}
└── Доступных пар: {len(self.available_pairs)}
"""
        return text


# Синглтон
arbitrage_scanner = ArbitrageScanner()
