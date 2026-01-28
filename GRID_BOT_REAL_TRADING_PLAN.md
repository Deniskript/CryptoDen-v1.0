# 📊 Grid Bot — План перехода на реальную торговлю

> **Дата:** 2026-01-28  
> **Статус:** Анализ текущего состояния  
> **Цель:** Реализовать реальную торговлю через Bybit API v5

---

## 🔍 ТЕКУЩЕЕ СОСТОЯНИЕ

### ✅ Что работает (Paper Trading):

```python
# app/modules/grid_bot.py

class GridBot:
    def __init__(self):
        self.paper_trading = True  # ❌ ЖЁСТКО ЗАКОДИРОВАНО
        self.grids: Dict[str, Grid] = {}
        self.configs: Dict[str, GridConfig] = {}
        self.virtual_orders: List[VirtualOrder] = []
```

**Функциональность:**
- ✅ Виртуальные ордера создаются
- ✅ Сетка рассчитывается корректно
- ✅ Профит считается правильно
- ✅ Уведомления в Telegram работают

**Проблема:** НЕТ реальных ордеров на Bybit!

---

### ❌ Что НЕ работает (Real Trading):

#### 1️⃣ **BybitClient — НЕТ лимитных ордеров:**

```python
# app/trading/bybit/client.py

# ✅ Есть:
async def market_buy(symbol, qty, quote_qty) -> dict
async def market_sell(symbol, qty) -> dict
async def get_order(symbol, order_id) -> dict
async def cancel_order(symbol, order_id) -> dict

# ❌ НЕТ:
async def limit_buy(symbol, price, qty) -> dict    # НУЖЕН!
async def limit_sell(symbol, price, qty) -> dict   # НУЖЕН!
```

**Для Grid Bot нужны:**
- `limit_buy()` — лимитная покупка
- `limit_sell()` — лимитная продажа

#### 2️⃣ **Grid Bot — нет интеграции с Bybit:**

```python
# app/modules/grid_bot.py

async def check_orders(self, current_price: float):
    """Проверить ордера и исполнить"""
    
    # ❌ ТОЛЬКО виртуальные ордера:
    for order in self.virtual_orders:
        if order.status == "pending":
            # Проверяем цену
            # Исполняем виртуально
            # НЕТ вызова bybit.limit_buy/sell!
```

#### 3️⃣ **Нет синхронизации с биржей:**

```python
# Grid Bot НЕ проверяет реальные ордера на Bybit:
# - Открытые ордера
# - Исполненные ордера
# - Отменённые ордера
```

---

## 🎯 ПЛАН РЕАЛИЗАЦИИ

### ЭТАП 1: Добавить лимитные ордера в BybitClient

**Файл:** `app/trading/bybit/client.py`

```python
async def limit_buy(
    self, 
    symbol: str, 
    price: float, 
    qty: float = None,
    quote_qty: float = None
) -> dict:
    """
    Лимитная покупка
    
    Args:
        symbol: BTC, ETH, etc.
        price: Цена лимитного ордера
        qty: Количество базовой валюты (опционально)
        quote_qty: Сумма в USDT (опционально)
    
    Returns:
        {
            'retCode': 0,
            'result': {
                'orderId': '...',
                'orderLinkId': '...'
            }
        }
    """
    
    params = {
        'category': 'spot',
        'symbol': f"{symbol}USDT",
        'side': 'Buy',
        'orderType': 'Limit',
        'price': str(price),
        'timeInForce': 'GTC',  # Good Till Cancel
    }
    
    if quote_qty:
        # Рассчитать qty из quote_qty
        params['qty'] = str(quote_qty / price)
    elif qty:
        params['qty'] = str(qty)
    else:
        return {'retCode': -1, 'retMsg': 'qty or quote_qty required'}
    
    resp = await self._request('POST', '/v5/order/create', params, private=True)
    
    if resp.get('retCode') == 0:
        order_id = resp.get('result', {}).get('orderId')
        logger.info(f"✅ Limit BUY {symbol} @ ${price}: order {order_id}")
    else:
        logger.error(f"❌ Limit BUY failed: {resp}")
    
    return resp


async def limit_sell(
    self, 
    symbol: str, 
    price: float, 
    qty: float
) -> dict:
    """
    Лимитная продажа
    
    Args:
        symbol: BTC, ETH, etc.
        price: Цена лимитного ордера
        qty: Количество базовой валюты
    
    Returns:
        {
            'retCode': 0,
            'result': {'orderId': '...'}
        }
    """
    
    params = {
        'category': 'spot',
        'symbol': f"{symbol}USDT",
        'side': 'Sell',
        'orderType': 'Limit',
        'price': str(price),
        'qty': str(qty),
        'timeInForce': 'GTC',
    }
    
    resp = await self._request('POST', '/v5/order/create', params, private=True)
    
    if resp.get('retCode') == 0:
        order_id = resp.get('result', {}).get('orderId')
        logger.info(f"✅ Limit SELL {symbol} @ ${price}: order {order_id}")
    else:
        logger.error(f"❌ Limit SELL failed: {resp}")
    
    return resp
```

---

### ЭТАП 2: Обновить GridBot для реальной торговли

**Файл:** `app/modules/grid_bot.py`

#### 2.1. Добавить режим торговли:

```python
class GridBot:
    def __init__(self):
        # ❌ БЫЛО:
        # self.paper_trading = True
        
        # ✅ СТАЛО:
        self.paper_trading = True  # По умолчанию paper
        self.bybit_client = None  # Будет установлен извне
```

#### 2.2. Добавить метод установки режима:

```python
def set_trading_mode(self, paper_trading: bool, bybit_client=None):
    """
    Установить режим торговли
    
    Args:
        paper_trading: True = виртуальная, False = реальная
        bybit_client: BybitClient instance (для реальной торговли)
    """
    self.paper_trading = paper_trading
    
    if not paper_trading and bybit_client:
        self.bybit_client = bybit_client
        logger.info("📊 Grid Bot: REAL TRADING MODE")
    else:
        logger.info("📊 Grid Bot: PAPER TRADING MODE")
```

#### 2.3. Обновить метод create_orders():

```python
async def create_orders(self, symbol: str):
    """
    Создать ордера для сетки
    
    - Paper: виртуальные ордера
    - Real: лимитные ордера на Bybit
    """
    
    if symbol not in self.grids:
        return
    
    grid = self.grids[symbol]
    
    if self.paper_trading:
        # ✅ Виртуальные ордера (как сейчас)
        self._create_virtual_orders(grid)
    else:
        # ✅ Реальные ордера на Bybit
        await self._create_real_orders(grid)


async def _create_real_orders(self, grid: Grid):
    """Создать реальные лимитные ордера на Bybit"""
    
    if not self.bybit_client:
        logger.error("❌ Grid: No Bybit client for real trading!")
        return
    
    config = self.configs.get(grid.symbol)
    if not config:
        return
    
    # Создаём BUY ордера (ниже текущей цены)
    for level in grid.buy_levels:
        if level.order_id:
            continue  # Ордер уже создан
        
        resp = await self.bybit_client.limit_buy(
            symbol=grid.symbol,
            price=level.price,
            quote_qty=config.order_size_usdt
        )
        
        if resp.get('retCode') == 0:
            level.order_id = resp['result']['orderId']
            level.status = "open"
            logger.info(f"📊 Grid BUY: {grid.symbol} @ ${level.price:.2f}")
        else:
            logger.error(f"❌ Grid BUY failed: {resp.get('retMsg')}")
    
    # Создаём SELL ордера (выше текущей цены)
    for level in grid.sell_levels:
        if level.order_id:
            continue
        
        # Нужно знать qty (сколько монет продаём)
        qty = config.order_size_usdt / level.price
        
        resp = await self.bybit_client.limit_sell(
            symbol=grid.symbol,
            price=level.price,
            qty=qty
        )
        
        if resp.get('retCode') == 0:
            level.order_id = resp['result']['orderId']
            level.status = "open"
            logger.info(f"📊 Grid SELL: {grid.symbol} @ ${level.price:.2f}")
        else:
            logger.error(f"❌ Grid SELL failed: {resp.get('retMsg')}")
```

#### 2.4. Добавить синхронизацию с биржей:

```python
async def sync_with_exchange(self, symbol: str):
    """
    Синхронизировать ордера с Bybit
    
    Проверяем:
    - Какие ордера исполнены
    - Какие ордера отменены
    - Какие ордера ещё открыты
    """
    
    if self.paper_trading or not self.bybit_client:
        return
    
    if symbol not in self.grids:
        return
    
    grid = self.grids[symbol]
    
    # Получить открытые ордера с Bybit
    open_orders = await self.bybit_client.get_open_orders(symbol)
    
    if not open_orders:
        return
    
    open_order_ids = {o.get('orderId') for o in open_orders}
    
    # Проверяем BUY уровни
    for level in grid.buy_levels:
        if not level.order_id:
            continue
        
        if level.order_id not in open_order_ids:
            # Ордер исполнен или отменён
            order_info = await self.bybit_client.get_order(symbol, level.order_id)
            
            status = order_info.get('result', {}).get('orderStatus')
            
            if status == 'Filled':
                level.status = "filled"
                logger.info(f"✅ Grid BUY filled: {symbol} @ ${level.price:.2f}")
                
                # Создаём ордер на продажу
                await self._create_sell_order_after_buy(grid, level)
            
            elif status in ['Cancelled', 'Rejected']:
                level.status = "cancelled"
                level.order_id = None
    
    # Проверяем SELL уровни
    for level in grid.sell_levels:
        if not level.order_id:
            continue
        
        if level.order_id not in open_order_ids:
            order_info = await self.bybit_client.get_order(symbol, level.order_id)
            
            status = order_info.get('result', {}).get('orderStatus')
            
            if status == 'Filled':
                level.status = "filled"
                logger.info(f"✅ Grid SELL filled: {symbol} @ ${level.price:.2f}")
                
                # Профит зафиксирован
                profit = level.expected_profit
                logger.info(f"💰 Grid profit: ${profit:.2f}")
            
            elif status in ['Cancelled', 'Rejected']:
                level.status = "cancelled"
                level.order_id = None
```

---

### ЭТАП 3: Интеграция с Master Strategist

**Файл:** `app/core/monitor.py`

```python
# В методе _check_for_signals():

# ========================================
# 📊 ШАГ 3: Grid Bot (с учётом Master Strategist)
# ========================================
grid_enabled_by_master = master_grid_settings.get("enabled", True)
grid_mode_by_master = master_grid_settings.get("mode", "balanced")

if self.is_module_enabled('grid') and grid_enabled_by_master:
    try:
        # Применяем режим от Master
        grid_config = master_strategist.get_grid_config()
        
        # ✅ НОВОЕ: Устанавливаем режим торговли
        if self.can_auto_trade('grid') and self.has_api_keys:
            # REAL TRADING
            grid_bot.set_trading_mode(
                paper_trading=False,
                bybit_client=self.bybit
            )
        else:
            # PAPER TRADING
            grid_bot.set_trading_mode(paper_trading=True)
        
        if grid_config.get("enabled", True):
            # Генерируем сигналы
            grid_signals = await grid_bot.get_signals({"prices": prices})
            
            # Синхронизируем с биржей (если real)
            for symbol in grid_bot.grids.keys():
                await grid_bot.sync_with_exchange(symbol)
```

---

### ЭТАП 4: Безопасность и риски

#### 4.1. Проверки перед реальной торговлей:

```python
def _validate_real_trading(self, symbol: str) -> tuple[bool, str]:
    """
    Проверить готовность к реальной торговле
    
    Returns:
        (can_trade, reason)
    """
    
    # 1. Проверить API ключи
    if not self.bybit_client:
        return False, "No Bybit client"
    
    # 2. Проверить баланс
    balance = await self.bybit_client.get_balance("USDT")
    if not balance or balance < 100:
        return False, f"Insufficient balance: ${balance:.2f}"
    
    # 3. Проверить конфиг
    if symbol not in self.configs:
        return False, f"No config for {symbol}"
    
    config = self.configs[symbol]
    
    # 4. Проверить размер ордера
    if config.order_size_usdt < 10:
        return False, f"Order size too small: ${config.order_size_usdt}"
    
    # 5. Проверить лимиты (не больше 20 ордеров на символ)
    grid = self.grids.get(symbol)
    if grid:
        total_orders = len(grid.buy_levels) + len(grid.sell_levels)
        if total_orders > 20:
            return False, f"Too many orders: {total_orders}"
    
    return True, "OK"
```

#### 4.2. Лимиты:

```python
REAL_TRADING_LIMITS = {
    "min_order_size_usdt": 10,      # Минимум $10 на ордер
    "max_orders_per_symbol": 20,    # Максимум 20 ордеров
    "max_total_exposure": 1000,     # Максимум $1000 в сетке
    "min_balance_usdt": 100,        # Минимум $100 баланс
}
```

---

## ⚙️ НАСТРОЙКИ GRID BOT

### Режимы от Master Strategist:

| Режим | Grid Step | Grid Count | Order Size | Profit/Grid |
|-------|-----------|------------|------------|-------------|
| **Aggressive** | 1.0% | 10 | $100 | 0.3% |
| **Balanced** | 1.5% | 7 | $75 | 0.5% |
| **Conservative** | 2.0% | 5 | $50 | 0.7% |

### Применение:

```python
# Master Strategist решает режим
strategy = await master_strategist.analyze_market(market_data)

if strategy.market_condition == "sideways":
    # Боковик — Grid aggressive
    grid_config = {
        "grid_step_percent": 1.0,
        "grid_count": 10,
        "profit_per_grid": 0.3,
    }
elif strategy.market_condition in ["bullish", "bearish"]:
    # Тренд — Grid conservative
    grid_config = {
        "grid_step_percent": 2.0,
        "grid_count": 5,
        "profit_per_grid": 0.7,
    }
else:
    # high_vol, dangerous — Grid OFF
    grid_config = {"enabled": False}
```

---

## 📋 ЧЕКЛИСТ РЕАЛИЗАЦИИ

### Phase 1: Подготовка (30 мин)
- [ ] Добавить `limit_buy()` в BybitClient
- [ ] Добавить `limit_sell()` в BybitClient
- [ ] Протестировать лимитные ордера на testnet

### Phase 2: Grid Bot Real Trading (1 час)
- [ ] Добавить `set_trading_mode()` в GridBot
- [ ] Реализовать `_create_real_orders()`
- [ ] Реализовать `sync_with_exchange()`
- [ ] Добавить `_validate_real_trading()`

### Phase 3: Интеграция (30 мин)
- [ ] Обновить `monitor.py` для real/paper режима
- [ ] Добавить проверку API ключей
- [ ] Добавить настройки в WebApp

### Phase 4: Тестирование (1 час)
- [ ] Тест на testnet с $10
- [ ] Проверить создание ордеров
- [ ] Проверить исполнение ордеров
- [ ] Проверить синхронизацию

### Phase 5: Production (по готовности)
- [ ] Переключить на mainnet
- [ ] Установить лимиты
- [ ] Мониторинг 24/7

---

## 🚨 ВАЖНЫЕ ЗАМЕЧАНИЯ

### 1️⃣ **Testnet сначала!**
```python
# В .env:
BYBIT_TESTNET=true  # ОБЯЗАТЕЛЬНО для первых тестов!
```

### 2️⃣ **Начать с маленьких сумм:**
```python
# Первый запуск:
order_size_usdt = 10  # $10 на ордер
grid_count = 3        # Только 3 уровня
```

### 3️⃣ **Мониторинг обязателен:**
```python
# Логировать каждое действие:
- Создание ордера
- Исполнение ордера
- Отмена ордера
- Баланс до/после
```

### 4️⃣ **Stop Loss для всей сетки:**
```python
# Если просадка > 10%:
if total_loss > balance * 0.10:
    await grid_bot.cancel_all_orders(symbol)
    await grid_bot.close_all_positions(symbol)
```

---

## 💰 ОЖИДАЕМАЯ ДОХОДНОСТЬ

### Консервативная оценка:

```
Баланс: $1000
Режим: Balanced (1.5% шаг, 0.5% профит)
Активность: 30% времени в боковике

Доход:
- 1 исполнение в день × 0.5% профит × $100 = $0.50/день
- 30 исполнений в месяц = $15/месяц
- ROI: 1.5% в месяц
```

### Оптимистичная оценка (волатильный рынок):

```
Режим: Aggressive (1% шаг, 0.3% профит)
Активность: 60% времени

Доход:
- 3 исполнения в день × 0.3% × $200 = $1.80/день
- 90 исполнений в месяц = $54/месяц
- ROI: 5.4% в месяц
```

---

**Последнее обновление:** 2026-01-28 03:45 UTC
