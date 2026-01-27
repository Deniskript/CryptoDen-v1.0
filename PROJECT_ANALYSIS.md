# 📊 CryptoDen Bot — Полный Анализ Проекта

> **Дата:** 2026-01-27  
> **Цель:** Понять текущую архитектуру для внедрения Director TAKE_CONTROL

---

## 📋 СОДЕРЖАНИЕ

1. [Архитектура системы](#архитектура-системы)
2. [Торговый клиент](#1-торговый-клиент-bybitclientpy)
3. [Менеджер сделок](#2-менеджер-сделок-trade_managerpy)
4. [Director AI](#3-director-ai-director_aipy)
5. [Whale AI](#4-whale-ai-whale_aipy)
6. [Координатор](#5-координатор-trading_coordinatorpy)
7. [Главный цикл](#6-главный-цикл-monitorpy)
8. [Telegram Bot](#7-telegram-bot-telegram_botpy)
9. [Проверка стратегий](#8-проверка-стратегий-checkerpy)
10. [Выводы и рекомендации](#выводы-и-рекомендации)

---

## 🏗️ АРХИТЕКТУРА СИСТЕМЫ

```
┌─────────────────────────────────────────────────────────────┐
│                    TELEGRAM USER                             │
│                         ↓                                    │
│              ┌─────────────────────┐                         │
│              │   Telegram Bot      │                         │
│              │  (Commands + WebApp)│                         │
│              └──────────┬──────────┘                         │
│                         ↓                                    │
│              ┌─────────────────────┐                         │
│              │   MarketMonitor     │ ← Главный цикл (60 сек) │
│              │   _check_for_signals│                         │
│              └──────────┬──────────┘                         │
│                         │                                    │
│         ┌───────────────┼───────────────┐                    │
│         ↓               ↓               ↓                    │
│   ┌───────────┐   ┌───────────┐   ┌───────────┐              │
│   │ Whale AI  │   │DirectorAI │   │ StrategyChk│              │
│   │(Метрики)  │   │(Решения)  │   │ (Сигналы)  │              │
│   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘              │
│         └───────────────┼───────────────┘                    │
│                         ↓                                    │
│              ┌─────────────────────┐                         │
│              │TradingCoordinator   │ ← Фильтрация            │
│              │  (Оркестрация)      │                         │
│              └──────────┬──────────┘                         │
│                         ↓                                    │
│              ┌─────────────────────┐                         │
│              │   TradeManager      │ ← Управление сделками   │
│              │ SL/TP/Trailing Stop │                         │
│              └──────────┬──────────┘                         │
│                         ↓                                    │
│              ┌─────────────────────┐                         │
│              │   BybitClient       │ ← API Bybit             │
│              │  (Исполнение)       │                         │
│              └─────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### **ВАЖНО! Новая функция:**

```
┌─────────────────────────────────────────────────────────────┐
│              ┌─────────────────────┐                         │
│              │   DirectorTrader    │ ← 🆕 НОВОЕ!              │
│              │  (TAKE_CONTROL)     │                         │
│              │  Открывает СВОИ     │                         │
│              │  сделки когда:      │                         │
│              │  - F&G < 20 + news  │                         │
│              │  - Массовые ликв.   │                         │
│              │  - Extreme funding  │                         │
│              └──────────┬──────────┘                         │
│                         ↓                                    │
│              ┌─────────────────────┐                         │
│              │   BybitClient       │ ← Прямо к бирже!        │
│              └─────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. ТОРГОВЫЙ КЛИЕНТ (`bybit/client.py`)

### ✅ ЧТО ЕСТЬ:

```python
class BybitClient:
    # Публичные методы
    async def get_price(symbol: str) → float
    async def get_prices(symbols: List[str]) → Dict[str, float]
    async def get_all_spot_prices() → Dict[str, float]
    
    # Приватные методы (требуют API ключи)
    async def get_balance(coin: str = "USDT") → float
    async def get_all_balances() → Dict[str, float]
    
    # Торговые методы
    async def market_buy(symbol, qty=None, quote_qty=None) → dict
    async def market_sell(symbol, qty) → dict
    
    # Управление ордерами
    async def get_order(symbol, order_id) → dict
    async def get_open_orders(symbol) → List[dict]
    async def cancel_order(symbol, order_id) → dict
```

### 🎯 ДЛЯ DIRECTOR TRADER:

**Уже готово для использования:**
- ✅ `market_buy()` — открыть LONG
- ✅ `market_sell()` — закрыть LONG (продать монету)
- ✅ `get_price()` — текущая цена
- ✅ `get_balance()` — баланс USDT и монет

**Проблемы:**
- ❌ **SHORT на споте не поддерживается** (нужна маржа)
- ⚠️ Нет лимитных ордеров (только market)

### 💡 РЕКОМЕНДАЦИЯ:

Для SHORT на споте:
```python
# В DirectorTrader добавить проверку:
if direction == "SHORT" and market_monitor.paper_trading == False:
    logger.warning("SHORT на споте не поддерживается")
    return None  # Не открываем SHORT в LIVE
```

---

## 2. МЕНЕДЖЕР СДЕЛОК (`trade_manager.py`)

### ✅ ЧТО ЕСТЬ:

```python
@dataclass
class Trade:
    # Базовые поля
    id, symbol, direction, entry_price, current_price
    stop_loss, take_profit, quantity, value_usdt
    
    # Trailing Stop (встроенный!)
    trailing_stop_enabled = True
    trailing_stop_percent = 0.3  # Активация после +0.3%
    trailing_stop_distance = 0.2  # Дистанция 0.2%
    highest_price, lowest_price, trailing_stop_price
    
    # Методы
    def update_price(new_price)
    def _update_trailing_stop(new_price)
    def should_close() → CloseReason  # TP, SL, Trailing

class TradeManager:
    active_trades: Dict[str, Trade]
    
    # Лимиты
    max_trades_per_symbol = 1
    max_total_trades = 5
    
    # Методы
    async def open_trade(signal, value) → Trade
    async def close_trade(trade_id, reason) → Trade
    async def update_prices(prices) → List[Trade]  # Автозакрытие
```

### 🎯 ДЛЯ DIRECTOR TRADER:

**Вопрос:** Использовать `TradeManager` для Director или создать отдельный?

**Вариант A (использовать TradeManager):**
```python
# В DirectorTrader.execute_trade():
signal = Signal(
    symbol=symbol,
    direction=direction,
    entry_price=current_price,
    ...
)

trade = await trade_manager.open_trade(signal, size_usd)
```

**✅ Плюсы:**
- Встроенный Trailing Stop
- Автоматическое SL/TP
- Единый список сделок

**❌ Минусы:**
- TradeManager имеет лимиты (max 5 сделок)
- Director может конфликтовать с Worker

**Вариант B (отдельный DirectorTrade):**
```python
@dataclass
class DirectorTrade:  # УЖЕ ЕСТЬ В director_ai.py!
    id, symbol, direction, entry_price, ...
    
    # Своё управление
    async def _manage_trade()  # Каждые 10 сек
    async def _update_trailing_stop()
```

### 💡 РЕКОМЕНДАЦИЯ:

**Использовать отдельный `DirectorTrade`** (как уже реализовано):
- ✅ Независимый от Worker
- ✅ Свои лимиты (3 сделки max)
- ✅ Свой таск управления (`asyncio.create_task`)
- ✅ Не конфликтует с `TradeManager`

---

## 3. DIRECTOR AI (`director_ai.py`)

### ✅ ЧТО ЕСТЬ:

#### **A) DirectorAI (Принятие решений):**

```python
class DirectorAI:
    # Режимы
    current_mode: TradingMode  # AUTO, SUPERVISED, MANUAL, PAUSED
    
    # Флаги
    allow_new_longs: bool
    allow_new_shorts: bool
    size_multiplier: float
    
    # Методы
    async def consult_friend() → Dict  # Whale AI
    async def check_news() → Dict      # News AI
    async def get_open_positions() → Dict
    async def analyze_situation() → MarketSituation
    async def make_decision() → DirectorCommand
    
    # Решения
    DirectorDecision:
        CONTINUE, CLOSE_ALL, CLOSE_LONGS, CLOSE_SHORTS,
        PAUSE_NEW, TAKE_CONTROL, REDUCE_SIZE,
        AGGRESSIVE_LONG, AGGRESSIVE_SHORT
```

#### **B) DirectorTrader (🆕 Активная торговля):**

```python
class DirectorTrader:
    active_trades: Dict[str, DirectorTrade]
    is_controlling: bool
    
    # Настройки
    config = {
        "check_interval_seconds": 10,
        "trailing_activation_percent": 0.5,
        "trailing_distance_percent": 0.3,
        "max_position_time_hours": 24,
    }
    
    # Методы
    async def should_take_control(whale_metrics, news_context, market_data) 
        → (should_take, direction, reason)
    
    async def execute_trade(symbol, direction, reason, size_usd)
        → DirectorTrade
    
    async def _manage_trade(trade)  # Цикл каждые 10 сек
    async def _update_trailing_stop(trade, price)
    async def _check_news_exit(trade) → (should_close, reason)
    async def _check_whale_exit(trade) → reason
    async def _close_trade(trade, reason)
```

### 🎯 7 СЦЕНАРИЕВ TAKE_CONTROL:

1. **F&G < 20 + Bullish News** → LONG
2. **F&G > 80 + Bearish News** → SHORT
3. **Long Liquidations > $50M + F&G < 25** → LONG
4. **Short Liquidations > $50M + F&G > 75** → SHORT
5. **Funding > 0.1% + Long Ratio > 70%** → SHORT
6. **Funding < -0.1% + Long Ratio < 30%** → LONG
7. **F&G < 15 + Long Ratio < 35%** → LONG

### ✅ ЧТО УЖЕ РЕАЛИЗОВАНО:

```python
# 1. Проверка условий
should_take, direction, reason = await director_trader.should_take_control(...)

# 2. Открытие позиции
trade = await director_trader.execute_trade(symbol, direction, reason)

# 3. Управление в реалтайме
asyncio.create_task(director_trader._manage_trade(trade))

# 4. Trailing Stop (встроен в _manage_trade)
# 5. Проверка новостей каждые 60 сек
# 6. Проверка Whale метрик
# 7. Закрытие по SL/TP/Trailing/News/Whale
```

### ⚠️ ЧТО НУЖНО ДОБАВИТЬ:

**В `monitor.py` → `_check_for_signals()`:**

```python
# ПЕРЕД проверкой стратегий:

# 1. Проверить нужен ли TAKE_CONTROL
if not director_trader.is_controlling:
    should_take, direction, reason = await director_trader.should_take_control(
        whale_metrics=whale_metrics,
        news_context=news_context,
        market_data={"prices": prices}
    )
    
    if should_take:
        logger.warning(f"🎩 TAKE_CONTROL: {reason}")
        
        # Открываем позицию Director
        trade = await director_trader.execute_trade(
            symbol="BTC",  # Или выбрать лучший символ
            direction=direction,
            reason=reason
        )
        
        return  # Director управляет, Worker отдыхает

# 2. Если Director управляет - Worker не работает
if director_trader.is_controlling:
    logger.debug("🎩 Director controlling, Worker waiting...")
    return

# 3. Дальше идёт обычная проверка стратегий...
```

---

## 4. WHALE AI (`whale_ai.py`)

### ✅ ЧТО ЕСТЬ:

```python
@dataclass
class MarketMetrics:
    # Open Interest
    open_interest, oi_change_1h, oi_change_24h
    
    # Funding
    funding_rate, funding_sentiment
    
    # Long/Short Ratio
    long_ratio, short_ratio, ls_sentiment
    
    # Liquidations
    liquidations_1h, liq_long, liq_short
    
    # Fear & Greed
    fear_greed_index, fear_greed_label
    
    # Whale Activity (Twitter)
    whale_net_flow, whale_sentiment

class WhaleAI:
    last_metrics: MarketMetrics
    
    # Методы
    async def get_market_metrics(symbol) → MarketMetrics
    async def analyze(symbol) → WhaleAlert
    def get_trading_bias() → "BULLISH" | "BEARISH" | "NEUTRAL"
```

### 🎯 ДЛЯ DIRECTOR TRADER:

**УЖЕ ГОТОВО!** Whale AI предоставляет все нужные метрики:

```python
# В monitor._check_for_signals():

from app.ai.whale_ai import whale_ai

# Получить метрики
if whale_ai.last_metrics:
    m = whale_ai.last_metrics
    whale_metrics = {
        "fear_greed": m.fear_greed_index,
        "long_ratio": m.long_ratio,
        "funding_rate": m.funding_rate,
        "oi_change_1h": m.oi_change_1h,
        "liq_long": m.liq_long,
        "liq_short": m.liq_short,
    }

# Передать в DirectorTrader
should_take, direction, reason = await director_trader.should_take_control(
    whale_metrics=whale_metrics,
    ...
)
```

### ⚠️ ВАЖНО:

Whale AI метрики НЕ обновляются автоматически в monitor!

**НУЖНО ДОБАВИТЬ:**

```python
# В monitor._main_cycle():

# 8. Обновляем Whale AI метрики (каждые 5 мин)
if should_update_whale_metrics():
    from app.ai.whale_ai import whale_ai
    await whale_ai.get_market_metrics("BTC")
```

---

## 5. КООРДИНАТОР (`trading_coordinator.py`)

### ✅ ЧТО ЕСТЬ:

```python
class TradingCoordinator:
    # Методы
    async def get_director_guidance() → dict
    async def filter_signal(signal, guidance) → (allowed, reason)
    async def process_signal(signal, guidance) → TradingAction
    async def check_for_close_orders(guidance) → List[TradingAction]
    async def execute_close_action(action) → bool
```

### 🎯 ТЕКУЩАЯ ЛОГИКА:

```
1. Director принимает решение
2. Coordinator фильтрует сигналы Worker через Director
3. Если Director говорит "close_all" — закрывает позиции Worker
```

### ⚠️ ЧТО ИЗМЕНИТСЯ С DIRECTOR TRADER:

**Coordinator НЕ управляет сделками Director!**

```python
# Coordinator управляет:
✅ Сделками Worker (через TradeManager)

# Coordinator НЕ управляет:
❌ Сделками Director (DirectorTrader самостоятельный!)
```

### 💡 ИЗМЕНЕНИЯ:

```python
# В monitor._check_for_signals():

# 1. СНАЧАЛА проверяем Director TAKE_CONTROL
if not director_trader.is_controlling:
    should_take, direction, reason = await director_trader.should_take_control(...)
    if should_take:
        # Director открывает СВОЮ сделку
        await director_trader.execute_trade(...)
        return  # ← Выходим! Worker не работает

# 2. Если Director управляет - Worker НЕ проверяет стратегии
if director_trader.is_controlling:
    return

# 3. ПОТОМ идёт обычная логика Worker
guidance = await trading_coordinator.get_director_guidance()
# ... check strategies ...
# ... filter through coordinator ...
```

---

## 6. ГЛАВНЫЙ ЦИКЛ (`monitor.py`)

### ✅ ТЕКУЩАЯ ЛОГИКА `_check_for_signals()`:

```python
async def _check_for_signals(prices):
    # 1. Получить руководство от Director
    guidance = await get_director_guidance()
    
    # 2. Если Director говорит "close_all" — закрыть
    if guidance['decision'] == 'close_all':
        close_actions = await coordinator.check_for_close_orders(guidance)
        for action in close_actions:
            await coordinator.execute_close_action(action)
        return
    
    # 3. Проверить можно ли открывать
    if guidance['decision'] in ['pause_new', 'take_control']:
        return
    
    # 4. Worker проверяет стратегии
    for symbol, price in prices.items():
        df = load_cache(symbol)
        signal = await strategy_checker.check_symbol(symbol, df, price)
        
        if signal:
            # Фильтруем через Coordinator
            allowed, reason = await coordinator.filter_signal(signal, guidance)
            
            if allowed:
                # AI анализирует
                ai_decision = await trading_ai.analyze(...)
                
                if ai_decision.action == OPEN:
                    trade_size = get_trade_size() * ai_decision.size_mult * guidance['size_mult']
                    await execute_signal(signal, trade_size)
```

### 🎯 НОВАЯ ЛОГИКА (С DIRECTOR TRADER):

```python
async def _check_for_signals(prices):
    from app.ai.whale_ai import whale_ai
    
    # ========================================
    # 🐋 ШАГ 0: Собираем данные для Director
    # ========================================
    whale_metrics = {}
    if whale_ai.last_metrics:
        m = whale_ai.last_metrics
        whale_metrics = {
            "fear_greed": m.fear_greed_index,
            "long_ratio": m.long_ratio,
            "funding_rate": m.funding_rate,
            "liq_long": m.liq_long,
            "liq_short": m.liq_short,
        }
    
    news_context = {}
    news = self.market_context.get("news", [])
    if news:
        bearish = sum(1 for n in news if n.get("sentiment", 0) < -0.2)
        bullish = sum(1 for n in news if n.get("sentiment", 0) > 0.2)
        critical = sum(1 for n in news if n.get("importance") == "HIGH")
        
        news_context = {
            "sentiment": "bearish" if bearish > bullish else "bullish" if bullish > bearish else "neutral",
            "critical_count": critical,
        }
    
    # ========================================
    # 🎩 ШАГ 1: Проверить нужен ли TAKE_CONTROL
    # ========================================
    if not director_trader.is_controlling:
        should_take, direction, reason = await director_trader.should_take_control(
            whale_metrics=whale_metrics,
            news_context=news_context,
            market_data={"prices": prices}
        )
        
        if should_take:
            logger.warning(f"🎩 TAKE_CONTROL: {reason}")
            
            # Director берёт управление!
            best_symbol = "BTC"  # Или выбрать динамически
            
            trade = await director_trader.execute_trade(
                symbol=best_symbol,
                direction=direction,
                reason=reason
            )
            
            if trade:
                logger.info(f"🎩 Director opened {best_symbol} {direction}")
                return  # ← Director управляет, Worker отдыхает
    
    # ========================================
    # 🎩 ШАГ 2: Если Director управляет - выходим
    # ========================================
    if director_trader.is_controlling:
        logger.debug("🎩 Director controlling, Worker waiting...")
        return
    
    # ========================================
    # 🎩 ШАГ 3: Обычная логика Worker
    # ========================================
    guidance = await get_director_guidance()
    
    # ... (старый код) ...
```

### ⚠️ ВАЖНО - ГДЕ ВСТАВИТЬ:

**В файле `monitor.py`, строка ~324-330:**

```python
async def _check_for_signals(self, prices: Dict[str, float]):
    """
    🔍 Поиск торговых сигналов
    
    ОБНОВЛЕНО: Теперь Director может брать TAKE_CONTROL!
    """
    
    # ← ЗДЕСЬ ВСТАВИТЬ НОВЫЙ КОД (ШАГ 0-2)
    
    # Текущий код начинается с:
    # guidance = await get_director_guidance()
```

---

## 7. TELEGRAM BOT (`telegram_bot.py`)

### ✅ ЧТО ЕСТЬ:

```python
class TelegramBot:
    # Команды
    /start, /help, /ai, /director, /whale, /market, /debug
    
    # Reply Keyboard
    📊 Статус, 📈 Сделки, 📰 Новости, 📋 История
    
    # WebApp Data Handler
    async def handle_webapp_data(message):
        # start_bot, stop_bot, update_settings
    
    # Уведомления
    async def notify_signal(signal)
    async def notify_trade_opened(trade)
    async def notify_trade_closed(trade)
    async def notify_error(error)
```

### 🎯 ДЛЯ DIRECTOR TRADER:

**НУЖНО ДОБАВИТЬ:**

```python
@self.dp.message(Command("director_trades"))
async def cmd_director_trades(message: types.Message):
    """🎩 Сделки Director Trader"""
    if not self._is_admin(message.from_user.id):
        return
    
    try:
        from app.ai.director_ai import director_trader
        
        text = director_trader.get_status_text()
        
        await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Director trades error: {e}")
        await message.answer(f"❌ *Ошибка:* {e}", parse_mode=ParseMode.MARKDOWN)
```

**УЖЕ РЕАЛИЗОВАНО В КОДЕ!** (строка 590-605)

---

## 8. ПРОВЕРКА СТРАТЕГИЙ (`checker.py`)

### ✅ ЧТО ЕСТЬ:

```python
class StrategyChecker:
    # Методы
    async def check_symbol(symbol, df, price) → Signal
    async def check_all_symbols(market_data) → List[Signal]
    
    # Лимиты
    max_signals_per_day = 3 на монету
    min_time_between_signals = 60 мин
    max_total_signals_per_day = 15
```

### 🎯 ДЛЯ DIRECTOR TRADER:

**ВАЖНО:** Director НЕ использует `StrategyChecker`!

```python
# Worker использует:
signal = await strategy_checker.check_symbol(symbol, df, price)

# Director использует:
should_take, direction, reason = await director_trader.should_take_control(
    whale_metrics=...,  # Без стратегий!
    news_context=...,
    market_data=...
)
```

**Две независимые системы:**

| Система | Источник сигналов | Проверка | Управление |
|---------|-------------------|----------|------------|
| **Worker** | StrategyChecker | RSI, EMA, MACD | TradeManager |
| **Director** | Market conditions | F&G, Funding, News | DirectorTrader |

---

## 💡 ВЫВОДЫ И РЕКОМЕНДАЦИИ

### ✅ ЧТО УЖЕ ГОТОВО:

1. **DirectorTrader класс** — полностью реализован (строка 666-1348 в `director_ai.py`)
2. **7 сценариев TAKE_CONTROL** — все реализованы
3. **Управление позицией** — цикл каждые 10 сек, trailing stop, проверка новостей/whale
4. **Telegram команда** `/director_trades` — готова
5. **Уведомления** — `_notify_take_control()`, `_notify_release_control()` — готовы

### ⚠️ ЧТО НУЖНО ДОБАВИТЬ:

#### **1. В `monitor.py` → `_check_for_signals()` (строка ~325):**

```python
# ПЕРЕД существующим кодом добавить:

from app.ai.whale_ai import whale_ai

# ШАГ 0: Собрать данные
whale_metrics = {...}  # Из whale_ai.last_metrics
news_context = {...}   # Из self.market_context

# ШАГ 1: Проверить TAKE_CONTROL
if not director_trader.is_controlling:
    should_take, direction, reason = await director_trader.should_take_control(...)
    if should_take:
        trade = await director_trader.execute_trade(...)
        return

# ШАГ 2: Если Director управляет - выход
if director_trader.is_controlling:
    return

# ШАГ 3: Обычная логика Worker продолжается...
```

#### **2. В `monitor.py` → `_main_cycle()` (строка ~187):**

```python
# Добавить обновление Whale AI метрик:

# 9. Обновляем Whale AI (каждые 5 мин)
if self.check_count % 5 == 0:  # Каждые 5 циклов = 5 минут
    from app.ai.whale_ai import whale_ai
    try:
        await whale_ai.get_market_metrics("BTC")
    except Exception as e:
        logger.error(f"Whale AI update error: {e}")
```

#### **3. В `monitor.py` → импорты (строка ~27):**

```python
from app.ai.director_ai import director_trader
```

### 🎯 ФИНАЛЬНАЯ СХЕМА:

```
ЦИКЛ MONITOR (60 сек):

1. Получить цены ✅
2. Обновить новости (5 мин) ✅
3. Обновить Whale AI (5 мин) ← ДОБАВИТЬ
4. Обновить активные позиции (Worker) ✅
5. Проверить активные позиции AI ✅
6. _check_for_signals():
   
   А) Director TAKE_CONTROL? ← ДОБАВИТЬ
      - Да → Director открывает сделку → return
      - Нет → продолжить
   
   Б) Director управляет? ← ДОБАВИТЬ
      - Да → return
      - Нет → продолжить
   
   В) Worker ищет сигналы ✅
      - Проверка стратегий
      - Фильтрация через Coordinator
      - AI анализ
      - Открытие сделки
```

### 📝 СВОДКА ИЗМЕНЕНИЙ:

| Файл | Строка | Что добавить | Сложность |
|------|--------|--------------|-----------|
| `monitor.py` | ~27 | `from app.ai.director_ai import director_trader` | Легко |
| `monitor.py` | ~230 | Обновление Whale AI метрик | Легко |
| `monitor.py` | ~325 | Логика TAKE_CONTROL (ШАГ 0-2) | Средне |

**ВРЕМЯ РЕАЛИЗАЦИИ:** ~30 минут

---

## 🚀 ПЛАН ДЕЙСТВИЙ:

1. ✅ **Понять текущую архитектуру** — ГОТОВО (этот документ)
2. ⏳ **Добавить 3 изменения в `monitor.py`** — 30 мин
3. ⏳ **Тестировать** — 1 час
4. ⏳ **Commit + Push** — 5 мин

**ВСЕГО: ~2 часа работы**

---

**КОНЕЦ ДОКУМЕНТА**
