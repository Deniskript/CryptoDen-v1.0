"""
📊 GRID BOT MODULE
Сетка ордеров для стабильного заработка в любом рынке

Логика:
1. Ставим сетку BUY ордеров ниже текущей цены
2. Ставим сетку SELL ордеров выше текущей цены
3. Когда BUY срабатывает → ставим SELL выше
4. Когда SELL срабатывает → ставим BUY ниже
5. = Собираем профит на каждом движении!

Real Trading:
- Paper mode: виртуальные ордера (по умолчанию)
- Real mode: лимитные ордера на Bybit через API
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
import uuid

from app.core.logger import logger
from app.modules.base_module import BaseModule, ModuleSignal

if TYPE_CHECKING:
    from app.trading.bybit.client import BybitClient


class GridOrderStatus(Enum):
    PENDING = "pending"      # Ждёт исполнения
    FILLED = "filled"        # Исполнен
    CANCELLED = "cancelled"  # Отменён


class GridOrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class GridOrder:
    """Ордер в сетке"""
    id: str
    symbol: str
    side: GridOrderSide
    price: float
    quantity: float
    status: GridOrderStatus = GridOrderStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    
    # Связанный ордер (BUY → SELL или SELL → BUY)
    linked_order_id: Optional[str] = None
    
    # Real trading: ID ордера на бирже
    exchange_order_id: Optional[str] = None


@dataclass
class GridConfig:
    """Конфигурация Grid Bot для монеты"""
    symbol: str
    enabled: bool = True
    
    # Диапазон сетки
    upper_price: float = 0.0      # Верхняя граница
    lower_price: float = 0.0      # Нижняя граница
    
    # Параметры сетки
    grid_count: int = 10          # Количество уровней
    grid_step_percent: float = 0.5  # Шаг сетки в %
    
    # Размер позиции
    order_size_usdt: float = 50.0  # Размер каждого ордера
    
    # Профит
    profit_per_grid: float = 0.3   # Профит с каждой сетки %
    
    # Лимиты
    max_open_orders: int = 20      # Макс открытых ордеров
    min_profit_usdt: float = 0.1   # Мин профит для сделки


@dataclass
class GridTrade:
    """Закрытая сделка Grid"""
    id: str
    symbol: str
    buy_price: float
    sell_price: float
    quantity: float
    profit_usdt: float
    profit_percent: float
    opened_at: datetime
    closed_at: datetime


class GridBot(BaseModule):
    """
    📊 Grid Bot - Сетка ордеров
    
    Работает в любом рынке:
    - Боковик: ИДЕАЛЬНО (много сделок)
    - Тренд вверх: Продаём дороже
    - Тренд вниз: Покупаем дешевле
    """
    
    name = "grid_bot"
    
    def __init__(self):
        self.enabled = True
        
        # Конфигурации для каждой монеты
        self.configs: Dict[str, GridConfig] = {}
        
        # Активные ордера
        self.orders: Dict[str, GridOrder] = {}
        
        # История сделок
        self.trades: List[GridTrade] = []
        
        # Статистика
        self.stats = {
            "total_trades": 0,
            "total_profit_usdt": 0.0,
            "today_trades": 0,
            "today_profit_usdt": 0.0,
            "last_trade_time": None,
        }
        
        # Paper trading (виртуальные ордера) - по умолчанию
        self.paper_trading = True
        
        # Real trading: Bybit client
        self.bybit: Optional['BybitClient'] = None
        
        # Маппинг: grid_order_id -> exchange_order_id
        self.real_orders: Dict[str, str] = {}
        
        # Инициализация дефолтных конфигов
        self._init_default_configs()
        
        logger.info("📊 Grid Bot initialized")
    
    def _init_default_configs(self):
        """Дефолтные конфигурации для монет"""
        
        # BTC - большой шаг, большие ордера
        self.configs["BTC"] = GridConfig(
            symbol="BTC",
            grid_count=10,
            grid_step_percent=0.3,      # 0.3% шаг = $300 при $100k
            order_size_usdt=100.0,
            profit_per_grid=0.2,
        )
        
        # ETH - средний шаг
        self.configs["ETH"] = GridConfig(
            symbol="ETH",
            grid_count=10,
            grid_step_percent=0.4,
            order_size_usdt=75.0,
            profit_per_grid=0.25,
        )
        
        # Альты - больший шаг (волатильнее)
        for symbol in ["SOL", "BNB", "XRP", "ADA", "DOGE", "LINK", "AVAX"]:
            self.configs[symbol] = GridConfig(
                symbol=symbol,
                grid_count=8,
                grid_step_percent=0.5,
                order_size_usdt=50.0,
                profit_per_grid=0.3,
            )
    
    # ═══════════════════════════════════════════════════════════
    # REAL TRADING METHODS
    # ═══════════════════════════════════════════════════════════
    
    def set_trading_mode(self, paper_trading: bool, bybit_client: Optional['BybitClient'] = None):
        """
        Переключить режим торговли
        
        Args:
            paper_trading: True = виртуально, False = реально
            bybit_client: Клиент Bybit для реальной торговли
        """
        self.paper_trading = paper_trading
        self.bybit = bybit_client
        
        mode = "PAPER" if paper_trading else "REAL"
        logger.info(f"📊 Grid Bot: режим {mode}")
        
        if not paper_trading and not bybit_client:
            logger.warning("⚠️ Real trading включён, но Bybit client не передан!")
            self.paper_trading = True
    
    async def _create_real_order(self, order: GridOrder) -> bool:
        """
        Создать реальный ордер на бирже
        
        Returns:
            True если успешно, False если ошибка
        """
        if self.paper_trading or not self.bybit:
            return True  # В paper mode всегда успех
        
        try:
            symbol = f"{order.symbol}USDT"
            qty = round(order.quantity, 6)  # Округляем для биржи
            
            if order.side == GridOrderSide.BUY:
                result = await self.bybit.limit_buy(symbol, order.price, qty)
            else:
                result = await self.bybit.limit_sell(symbol, order.price, qty)
            
            if result and result.get("orderId"):
                # Сохраняем связь grid_order -> exchange_order
                exchange_id = result["orderId"]
                self.real_orders[order.id] = exchange_id
                order.exchange_order_id = exchange_id
                logger.info(f"📊 Real order created: {order.side.value.upper()} {symbol} @ ${order.price:.2f}")
                return True
            else:
                logger.error(f"❌ Failed to create real order: {order.side.value} {order.symbol}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error creating real order: {e}")
            return False
    
    async def _cancel_real_order(self, order: GridOrder) -> bool:
        """
        Отменить реальный ордер на бирже
        """
        if self.paper_trading or not self.bybit:
            return True
        
        try:
            exchange_order_id = self.real_orders.get(order.id) or order.exchange_order_id
            
            if not exchange_order_id:
                return True  # Нет реального ордера
            
            symbol = f"{order.symbol}USDT"
            result = await self.bybit.cancel_order(symbol, exchange_order_id)
            
            if result:
                # Удаляем из маппинга
                if order.id in self.real_orders:
                    del self.real_orders[order.id]
                logger.info(f"📊 Real order cancelled: {exchange_order_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error cancelling real order: {e}")
            return False
    
    async def sync_with_exchange(self, symbol: str) -> int:
        """
        Синхронизировать Grid с биржей — проверить исполненные ордера
        
        Returns:
            Количество исполненных ордеров
        """
        if self.paper_trading or not self.bybit:
            return 0
        
        filled_count = 0
        
        for order_id, order in list(self.orders.items()):
            if order.symbol != symbol or order.status != GridOrderStatus.PENDING:
                continue
            
            exchange_order_id = self.real_orders.get(order.id) or order.exchange_order_id
            
            if not exchange_order_id:
                continue
            
            try:
                status = await self.bybit.get_order_status(f"{symbol}USDT", exchange_order_id)
                
                if status == "Filled":
                    order.status = GridOrderStatus.FILLED
                    order.filled_at = datetime.now()
                    filled_count += 1
                    logger.info(f"📊 Order filled on exchange: {order.side.value.upper()} {symbol} @ ${order.price:.2f}")
                    
                    # Создаём обратный ордер
                    config = self.configs.get(symbol)
                    if config:
                        await self._create_counter_order_async(order, config)
                    
                    # Если это SELL после BUY — фиксируем профит
                    if order.side == GridOrderSide.SELL and order.linked_order_id:
                        self._record_trade(order)
                        
                elif status == "Cancelled":
                    order.status = GridOrderStatus.CANCELLED
                    if order.id in self.real_orders:
                        del self.real_orders[order.id]
                    
            except Exception as e:
                logger.error(f"❌ Error syncing order {order.id}: {e}")
        
        return filled_count
    
    async def _create_counter_order_async(self, filled_order: GridOrder, config: GridConfig):
        """Создать обратный ордер после исполнения (async версия для real trading)"""
        
        if filled_order.side == GridOrderSide.BUY:
            # После BUY создаём SELL выше
            sell_price = filled_order.price * (1 + config.profit_per_grid / 100)
            
            order = GridOrder(
                id=str(uuid.uuid4())[:8],
                symbol=filled_order.symbol,
                side=GridOrderSide.SELL,
                price=round(sell_price, 2),
                quantity=filled_order.quantity,
                linked_order_id=filled_order.id,
            )
            self.orders[order.id] = order
            
            # Создать реальный ордер
            if not self.paper_trading:
                await self._create_real_order(order)
            
            logger.debug(f"📊 Created SELL @ ${sell_price:.2f} (profit target)")
        
        else:
            # После SELL создаём BUY ниже
            buy_price = filled_order.price * (1 - config.profit_per_grid / 100)
            
            order = GridOrder(
                id=str(uuid.uuid4())[:8],
                symbol=filled_order.symbol,
                side=GridOrderSide.BUY,
                price=round(buy_price, 2),
                quantity=filled_order.quantity,
            )
            self.orders[order.id] = order
            
            # Создать реальный ордер
            if not self.paper_trading:
                await self._create_real_order(order)
            
            logger.debug(f"📊 Created BUY @ ${buy_price:.2f}")
    
    async def cancel_all_orders(self, symbol: str = None) -> int:
        """
        Отменить все ордера Grid
        
        Args:
            symbol: Отменить только для этого символа (или все если None)
        
        Returns:
            Количество отменённых ордеров
        """
        cancelled = 0
        
        for order_id, order in list(self.orders.items()):
            if order.status != GridOrderStatus.PENDING:
                continue
            
            if symbol and order.symbol != symbol:
                continue
            
            # Отменяем на бирже
            if await self._cancel_real_order(order):
                order.status = GridOrderStatus.CANCELLED
                cancelled += 1
        
        logger.info(f"📊 Cancelled {cancelled} orders" + (f" for {symbol}" if symbol else ""))
        return cancelled
    
    # ═══════════════════════════════════════════════════════════
    # GRID MANAGEMENT
    # ═══════════════════════════════════════════════════════════
    
    async def setup_grid(self, symbol: str, current_price: float):
        """Настроить сетку вокруг текущей цены"""
        
        if symbol not in self.configs:
            logger.warning(f"Grid: No config for {symbol}")
            return
        
        config = self.configs[symbol]
        
        # Рассчитываем границы
        step = config.grid_step_percent / 100
        half_grids = config.grid_count // 2
        
        config.upper_price = current_price * (1 + step * half_grids)
        config.lower_price = current_price * (1 - step * half_grids)
        
        mode_str = "PAPER" if self.paper_trading else "REAL"
        logger.info(f"📊 Grid {symbol} ({mode_str}): ${config.lower_price:.2f} - ${config.upper_price:.2f}")
        
        # Создаём начальные ордера
        await self._create_initial_orders(symbol, current_price)
    
    async def _create_initial_orders(self, symbol: str, current_price: float):
        """Создать начальную сетку ордеров"""
        
        config = self.configs[symbol]
        step = config.grid_step_percent / 100
        
        # Отменяем старые реальные ордера
        if not self.paper_trading:
            await self.cancel_all_orders(symbol)
        
        # Удаляем старые ордера этого символа из памяти
        self.orders = {k: v for k, v in self.orders.items() 
                       if v.symbol != symbol or v.status == GridOrderStatus.FILLED}
        
        new_orders = []
        
        # BUY ордера ниже цены
        for i in range(1, config.grid_count // 2 + 1):
            buy_price = round(current_price * (1 - step * i), 2)
            
            order = GridOrder(
                id=str(uuid.uuid4())[:8],
                symbol=symbol,
                side=GridOrderSide.BUY,
                price=buy_price,
                quantity=round(config.order_size_usdt / buy_price, 6),
            )
            self.orders[order.id] = order
            new_orders.append(order)
        
        # SELL ордера выше цены
        for i in range(1, config.grid_count // 2 + 1):
            sell_price = round(current_price * (1 + step * i), 2)
            
            order = GridOrder(
                id=str(uuid.uuid4())[:8],
                symbol=symbol,
                side=GridOrderSide.SELL,
                price=sell_price,
                quantity=round(config.order_size_usdt / sell_price, 6),
            )
            self.orders[order.id] = order
            new_orders.append(order)
        
        # Создаём реальные ордера если не paper mode
        if not self.paper_trading:
            real_created = 0
            for order in new_orders:
                if await self._create_real_order(order):
                    real_created += 1
            logger.info(f"📊 Grid {symbol}: Created {real_created} REAL orders on Bybit")
        
        buy_count = sum(1 for o in self.orders.values() 
                       if o.symbol == symbol and o.side == GridOrderSide.BUY 
                       and o.status == GridOrderStatus.PENDING)
        sell_count = sum(1 for o in self.orders.values() 
                        if o.symbol == symbol and o.side == GridOrderSide.SELL
                        and o.status == GridOrderStatus.PENDING)
        
        logger.info(f"📊 Grid {symbol}: {buy_count} BUY + {sell_count} SELL orders active")
    
    async def check_orders(self, symbol: str, current_price: float) -> List[ModuleSignal]:
        """
        Проверить исполнение ордеров
        
        - Real mode: синхронизирует с биржей
        - Paper mode: проверяет по текущей цене
        
        Возвращает сигналы для исполненных сделок
        """
        signals = []
        
        if symbol not in self.configs or not self.configs[symbol].enabled:
            return signals
        
        config = self.configs[symbol]
        
        # Real trading: синхронизируем с биржей
        if not self.paper_trading:
            filled_count = await self.sync_with_exchange(symbol)
            
            if filled_count > 0:
                # Генерируем сигналы для уведомлений о заполненных ордерах
                for order_id, order in self.orders.items():
                    if order.symbol == symbol and order.status == GridOrderStatus.FILLED:
                        if order.filled_at and (datetime.now() - order.filled_at).total_seconds() < 120:
                            signal = ModuleSignal(
                                module_name=self.name,
                                symbol=symbol,
                                direction="BUY" if order.side == GridOrderSide.BUY else "SELL",
                                entry_price=order.price,
                                stop_loss=0,
                                take_profit=0,
                                reason=f"Grid {order.side.value.upper()} @ ${order.price:.2f} (REAL)",
                            )
                            signals.append(signal)
            
            return signals
        
        # Paper trading: проверяем по цене
        for order_id, order in list(self.orders.items()):
            if order.symbol != symbol or order.status != GridOrderStatus.PENDING:
                continue
            
            filled = False
            
            # BUY срабатывает когда цена <= order.price
            if order.side == GridOrderSide.BUY and current_price <= order.price:
                filled = True
                logger.info(f"📊 Grid BUY filled (paper): {symbol} @ ${order.price:.2f}")
            
            # SELL срабатывает когда цена >= order.price
            elif order.side == GridOrderSide.SELL and current_price >= order.price:
                filled = True
                logger.info(f"📊 Grid SELL filled (paper): {symbol} @ ${order.price:.2f}")
            
            if filled:
                order.status = GridOrderStatus.FILLED
                order.filled_at = datetime.now()
                
                # Создаём обратный ордер
                self._create_counter_order(order, config)
                
                # Если это SELL после BUY — фиксируем профит
                if order.side == GridOrderSide.SELL and order.linked_order_id:
                    self._record_trade(order)
                
                # Создаём сигнал для уведомления
                signal = ModuleSignal(
                    module_name=self.name,
                    symbol=symbol,
                    direction="BUY" if order.side == GridOrderSide.BUY else "SELL",
                    entry_price=order.price,
                    stop_loss=0,  # Grid не использует SL
                    take_profit=0,
                    reason=f"Grid {order.side.value.upper()} @ ${order.price:.2f}",
                )
                signals.append(signal)
        
        return signals
    
    def _create_counter_order(self, filled_order: GridOrder, config: GridConfig):
        """Создать обратный ордер после исполнения"""
        
        if filled_order.side == GridOrderSide.BUY:
            # После BUY создаём SELL выше
            sell_price = filled_order.price * (1 + config.profit_per_grid / 100)
            
            order = GridOrder(
                id=str(uuid.uuid4())[:8],
                symbol=filled_order.symbol,
                side=GridOrderSide.SELL,
                price=sell_price,
                quantity=filled_order.quantity,
                linked_order_id=filled_order.id,
            )
            self.orders[order.id] = order
            
            logger.debug(f"📊 Created SELL @ {sell_price:.2f} (profit target)")
        
        else:
            # После SELL создаём BUY ниже
            buy_price = filled_order.price * (1 - config.profit_per_grid / 100)
            
            order = GridOrder(
                id=str(uuid.uuid4())[:8],
                symbol=filled_order.symbol,
                side=GridOrderSide.BUY,
                price=buy_price,
                quantity=filled_order.quantity,
            )
            self.orders[order.id] = order
            
            logger.debug(f"📊 Created BUY @ {buy_price:.2f}")
    
    def _record_trade(self, sell_order: GridOrder):
        """Записать закрытую сделку"""
        
        if not sell_order.linked_order_id:
            return
        
        buy_order = self.orders.get(sell_order.linked_order_id)
        if not buy_order:
            return
        
        profit_percent = (sell_order.price - buy_order.price) / buy_order.price * 100
        profit_usdt = sell_order.quantity * (sell_order.price - buy_order.price)
        
        trade = GridTrade(
            id=str(uuid.uuid4())[:8],
            symbol=sell_order.symbol,
            buy_price=buy_order.price,
            sell_price=sell_order.price,
            quantity=sell_order.quantity,
            profit_usdt=profit_usdt,
            profit_percent=profit_percent,
            opened_at=buy_order.filled_at or buy_order.created_at,
            closed_at=sell_order.filled_at or datetime.now(),
        )
        
        self.trades.append(trade)
        
        # Обновляем статистику
        self.stats["total_trades"] += 1
        self.stats["total_profit_usdt"] += profit_usdt
        self.stats["last_trade_time"] = datetime.now()
        
        # Статистика за сегодня
        if trade.closed_at.date() == datetime.now().date():
            self.stats["today_trades"] += 1
            self.stats["today_profit_usdt"] += profit_usdt
        
        logger.info(f"📊 Grid trade closed: {sell_order.symbol} +${profit_usdt:.2f} (+{profit_percent:.2f}%)")
    
    async def get_signals(self, market_data: Dict) -> List[ModuleSignal]:
        """Получить сигналы от Grid Bot"""
        
        if not self.enabled:
            return []
        
        signals = []
        prices = market_data.get("prices", {})
        
        for symbol, price in prices.items():
            # Убираем USDT из символа если есть
            clean_symbol = symbol.replace("USDT", "")
            
            if clean_symbol not in self.configs:
                continue
            
            config = self.configs[clean_symbol]
            
            if not config.enabled:
                continue
            
            # Если сетка не настроена — настраиваем
            if config.upper_price == 0:
                await self.setup_grid(clean_symbol, price)
            
            # Проверяем ордера
            order_signals = await self.check_orders(clean_symbol, price)
            signals.extend(order_signals)
        
        return signals
    
    async def get_status(self) -> Dict:
        """Статус Grid Bot"""
        
        pending_orders = sum(1 for o in self.orders.values() 
                           if o.status == GridOrderStatus.PENDING)
        
        buy_orders = sum(1 for o in self.orders.values() 
                        if o.status == GridOrderStatus.PENDING 
                        and o.side == GridOrderSide.BUY)
        
        sell_orders = sum(1 for o in self.orders.values() 
                         if o.status == GridOrderStatus.PENDING 
                         and o.side == GridOrderSide.SELL)
        
        real_orders_count = len(self.real_orders)
        
        return {
            "enabled": self.enabled,
            "paper_trading": self.paper_trading,
            "trading_mode": "PAPER" if self.paper_trading else "REAL",
            "pending_orders": pending_orders,
            "buy_orders": buy_orders,
            "sell_orders": sell_orders,
            "real_orders_on_exchange": real_orders_count,
            "total_trades": self.stats["total_trades"],
            "total_profit_usdt": self.stats["total_profit_usdt"],
            "today_trades": self.stats["today_trades"],
            "today_profit_usdt": self.stats["today_profit_usdt"],
            "last_trade_time": self.stats["last_trade_time"],
            "active_symbols": [s for s, c in self.configs.items() if c.enabled],
        }
    
    def get_status_text(self) -> str:
        """Текст для Telegram"""
        
        pending_orders = sum(1 for o in self.orders.values() 
                           if o.status == GridOrderStatus.PENDING)
        
        buy_orders = sum(1 for o in self.orders.values() 
                        if o.status == GridOrderStatus.PENDING 
                        and o.side == GridOrderSide.BUY)
        
        sell_orders = sum(1 for o in self.orders.values() 
                         if o.status == GridOrderStatus.PENDING 
                         and o.side == GridOrderSide.SELL)
        
        active_symbols = [s for s, c in self.configs.items() if c.enabled]
        real_orders_count = len(self.real_orders)
        
        mode_text = "🟢 PAPER" if self.paper_trading else "🔴 REAL TRADING"
        
        text = f"""
📊 *GRID BOT STATUS*

{'✅ Активен' if self.enabled else '❌ Остановлен'} | {mode_text}

📈 *Сегодня:*
├── Сделок: {self.stats['today_trades']}
└── Профит: ${self.stats['today_profit_usdt']:.2f}

📊 *Всего:*
├── Сделок: {self.stats['total_trades']}
└── Профит: ${self.stats['total_profit_usdt']:.2f}

🔄 *Ордера:*
├── BUY: {buy_orders}
├── SELL: {sell_orders}
└── На бирже: {real_orders_count}

🎯 *Монеты:* {', '.join(active_symbols)}
"""
        return text
    
    def reset_today_stats(self):
        """Сброс дневной статистики (вызывать в полночь)"""
        self.stats["today_trades"] = 0
        self.stats["today_profit_usdt"] = 0.0


# Синглтон
grid_bot = GridBot()
