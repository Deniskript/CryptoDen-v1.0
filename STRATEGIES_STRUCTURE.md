# 📊 Структура стратегий и индикаторов CryptoDen Bot

**Дата анализа:** 2026-01-27  
**Версия:** 1.0

---

## 📁 Структура папки `app/strategies/`

```
app/strategies/
├── __init__.py          # Экспорты модуля
├── checker.py           # StrategyChecker — проверка условий в реальном времени
├── config.py            # Конфигурация 16 рабочих стратегий (BEST_STRATEGIES + SHORT_STRATEGIES)
├── indicators.py        # TechnicalIndicators — библиотека расчёта индикаторов
└── signals.py           # SignalGenerator — генерация торговых сигналов
```

**Итого:** 5 файлов  
**Отдельного `rsi_strategy.py` НЕТ** — все стратегии определены в `config.py`

---

## 🔍 Отсутствующие файлы

### ❌ Нет `app/strategies/rsi_strategy.py`
RSI стратегии определены в `config.py` как:
```python
BEST_STRATEGIES = {
    "BTC": StrategyConfig(
        conditions=[{"indicator": "rsi", "period": 14, "operator": "<", "value": 30}]
    ),
    ...
}
```

### ❌ Нет `app/workers/` папки
Worker — это **не отдельный модуль**, а **режим работы Monitor**.

---

## 🧠 Как работает Worker (в `monitor.py`)

### Концепция Worker
Worker — это роль Monitor'а, когда он **не торгует сам**, а только **генерирует сигналы** по стратегиям.

```python
# app/core/monitor.py, строки 20, 604-678
from app.strategies import strategy_checker, get_enabled_strategies, Signal

# ШАГ 4: Worker ищет сигналы по стратегиям
if not self.is_module_enabled('worker') or director_took_control:
    return  # Worker отдыхает, если Director взял контроль

# Worker проверяет каждую монету через StrategyChecker
for symbol in self.symbols:
    signal = await strategy_checker.check_symbol(symbol, df, price)
    
    if signal:
        logger.info(f"🎯 Worker Signal: {symbol} {signal.direction}")
```

### Режимы работы
```python
# Настройки модулей (строка 84)
'worker': {'enabled': True, 'mode': 'signal'}
```

**2 режима Worker:**
1. **`signal`** — только уведомления (рекомендации)
2. **`trade`** — открывает сделки через AI

---

## 📊 TechnicalIndicators (библиотека индикаторов)

**Файл:** `app/strategies/indicators.py`

### Список всех индикаторов

| Индикатор | Метод | Описание |
|-----------|-------|----------|
| **RSI** | `rsi(series, period=14)` | Relative Strength Index |
| **EMA** | `ema(series, period)` | Exponential Moving Average |
| **SMA** | `sma(series, period)` | Simple Moving Average |
| **Stochastic K** | `stochastic_k(df, period=14)` | Stochastic Oscillator K |
| **Stochastic D** | `stochastic_d(df, k=14, d=3)` | Stochastic Oscillator D |
| **MACD** | `macd(series, fast=12, slow=26, signal=9)` | MACD Line, Signal, Histogram |
| **MACD Cross** | `macd_cross_direction(series)` | "up" или "down" |
| **Bollinger Bands** | `bollinger_bands(series, period=20, std=2)` | Upper, Middle, Lower |
| **ATR** | `atr(df, period=14)` | Average True Range |
| **Volume SMA** | `volume_sma(df, period=20)` | Средний объём |
| **Volume Spike** | `is_volume_spike(df, multiplier=1.5)` | Проверка всплеска объёма |

### Пример использования

```python
from app.strategies.indicators import TechnicalIndicators

indicators = TechnicalIndicators()

# RSI
rsi_value = indicators.rsi(df['close'], period=14)

# EMA
ema_21 = indicators.ema(df['close'], period=21)

# Stochastic
stoch_k = indicators.stochastic_k(df, period=14)

# MACD
macd_line, signal_line, histogram = indicators.macd(df['close'])

# Volume Spike
is_spike = indicators.is_volume_spike(df, multiplier=1.5)
```

---

## 🎯 StrategyChecker (проверка условий)

**Файл:** `app/strategies/checker.py`

### Основные методы

```python
class StrategyChecker:
    async def check_symbol(self, symbol: str, df: pd.DataFrame, current_price: float) -> Optional[Signal]
    async def _check_single_strategy(self, symbol, df, price, strategy) -> Optional[Signal]
    def _check_condition(self, condition: dict, df, price) -> tuple[bool, str]
```

### Как проверяется условие

```python
# Пример проверки RSI < 30
condition = {"indicator": "rsi", "period": 14, "operator": "<", "value": 30}

# StrategyChecker вызывает:
actual_value = self.indicators.rsi(df['close'], period)
met = actual_value < 30  # Проверка оператора
```

### Поддерживаемые индикаторы в условиях

```python
# RSI
{"indicator": "rsi", "period": 14, "operator": "<", "value": 30}

# Stochastic K
{"indicator": "stoch_k", "period": 14, "operator": "<", "value": 25}

# Price vs EMA
{"indicator": "price_vs_ema", "period": 50, "operator": ">", "value": 0}

# MACD Cross
{"indicator": "macd_cross", "operator": "==", "value": "up"}

# Volume Spike
{"indicator": "volume_spike", "multiplier": 1.5, "operator": ">", "value": True}

# Stochastic Overbought
{"indicator": "stoch_overbought", "operator": ">", "value": 80}

# Stochastic Falling
{"indicator": "stoch_falling", "operator": "==", "value": True}

# MACD Bearish
{"indicator": "macd_bearish", "operator": "==", "value": True}
```

---

## 📋 16 рабочих стратегий (config.py)

### LONG стратегии (9 активных)

```python
BEST_STRATEGIES = {
    "BTC": {
        "name": "RSI(14) < 30 + Price > EMA(21)",
        "conditions": [
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
            {"indicator": "price_vs_ema", "period": 21, "operator": ">", "value": 0},
        ],
        "tp_percent": 0.3,
        "sl_percent": 0.5,
        "win_rate": 65.0,
    },
    
    "ETH": {
        "name": "RSI(14) < 35 + Price > EMA(50)",
        "conditions": [
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 35},
            {"indicator": "price_vs_ema", "period": 50, "operator": ">", "value": 0},
        ],
        "tp_percent": 0.3,
        "sl_percent": 0.5,
        "win_rate": 63.1,
    },
    
    "BNB": {
        "name": "RSI<30 + Price>EMA50 + Volume Spike",
        "conditions": [
            {"indicator": "rsi", "period": 14, "operator": "<", "value": 30},
            {"indicator": "price_vs_ema", "period": 50, "operator": ">", "value": 0},
            {"indicator": "volume_spike", "multiplier": 1.5, "operator": ">", "value": True},
        ],
        "tp_percent": 0.3,
        "sl_percent": 0.5,
        "win_rate": 71.5,
    },
    
    "ADA": {"name": "RSI(14) < 30 + Price > EMA(21)", "win_rate": 70.5},
    "DOGE": {"name": "Stoch(14) < 25 + MACD Cross Up", "win_rate": 67.6},
    "LINK": {"name": "RSI(14) < 30 + Price > EMA(50)", "win_rate": 66.7},
    "AVAX": {"name": "RSI(14) < 30 + Price > EMA(21)", "win_rate": 71.3},
    "SOL": {"name": "RSI(21) > 80 SHORT", "win_rate": 65.0},  # SHORT в LONG блоке
    "XRP": {"name": "RSI(14) > 80 SHORT", "win_rate": 63.3},  # SHORT в LONG блоке
}
```

### SHORT стратегии (7 активных)

```python
SHORT_STRATEGIES = {
    "BTC_SHORT": {
        "name": "Stoch Reversal Short",
        "conditions": [
            {"indicator": "stoch_overbought", "operator": ">", "value": 80},
            {"indicator": "stoch_falling", "operator": "==", "value": True},
            {"indicator": "price_vs_ema", "period": 50, "operator": "<", "value": 0},
        ],
        "win_rate": 63.9,
    },
    
    "ETH_SHORT": {"name": "Stoch Reversal Short", "win_rate": 62.7},
    "SOL_SHORT": {"name": "Stoch Reversal Short", "win_rate": 67.2},
    "ADA_SHORT": {"name": "Stoch Reversal Short", "win_rate": 69.4},
    "LINK_SHORT": {"name": "Stoch + MACD Short", "win_rate": 65.7},
    "AVAX_SHORT": {"name": "Stoch Reversal Short", "win_rate": 65.9},
    "BNB_SHORT": {"name": "RSI>70 + MACD Short", "win_rate": 66.2},
}
```

---

## 🔄 Как работает проверка стратегии (flow)

```
1. Monitor.py (_main_cycle)
        ↓
2. Загрузка OHLCV данных для символа
        ↓
3. strategy_checker.check_symbol(symbol, df, price)
        ↓
4. Проверка LONG стратегии → get_strategy(symbol)
        ↓
5. Проверка каждого условия через _check_condition()
        ↓
6. Вызов indicators.rsi() / indicators.ema() / и т.д.
        ↓
7. Все условия TRUE? → Генерация Signal
        ↓
8. Signal → AI analyze (если ai_enabled)
        ↓
9. AI Decision → Открытие сделки
```

---

## 📝 Упоминания Worker/RSI/Strategy в monitor.py

**Найдено 30 упоминаний:**

```python
# Строка 20: Импорт strategy_checker
from app.strategies import strategy_checker, get_enabled_strategies, Signal

# Строка 84: Настройка Worker
'worker': {'enabled': True, 'mode': 'signal'}

# Строки 292-294: Получение RSI для Dashboard
"BTC_rsi": await self._get_rsi("BTC"),
"ETH_rsi": await self._get_rsi("ETH"),
"SOL_rsi": await self._get_rsi("SOL"),

# Строки 414-415: Логика Worker vs Director
# Если да - Director торгует, Worker отдыхает
# Если нет - Worker ищет сигналы по стратегиям

# Строка 500: Director контролирует → Worker ждёт
logger.debug(f"🎩 Director controlling ({active} trades), Worker waiting...")

# Строка 604: Проверка включён ли Worker
if not self.is_module_enabled('worker') or director_took_control:

# Строка 673: Worker проверяет стратегии
signal = await strategy_checker.check_symbol(symbol, df, price)

# Строка 678: Лог Worker сигнала
logger.info(f"🎯 Worker Signal: {symbol} {signal.direction}")

# Строка 702: Передача strategy_signal в AI
strategy_signal={
    'strategy_name': signal.strategy_name,
    ...
}

# Строка 729: Уведомление о Worker Trade
f"🧠 *Worker Trade*\n\n"

# Строка 1204: Функция уведомления Worker
async def _notify_worker_signal(self, signal):
    """👷 Worker — рекомендация (signal mode)"""

# Строка 1213: Шаблон уведомления
👷 *RSI STRATEGY — СИГНАЛ*

# Строка 1223: Название стратегии
📊 Стратегия: {signal.strategy_name if hasattr(signal, 'strategy_name') else 'RSI + EMA'}

# Строки 1326-1370: Использование RSI в Dashboard
btc_rsi = indicators.get("BTC_rsi", 50)
...
if 40 <= rsi <= 60:
    reasons.append(f"• RSI в нейтральной зоне ({rsi:.0f})")
```

---

## 🎯 Выводы

### ✅ Что есть
1. **Модульная архитектура** — все стратегии в `config.py`, проверка в `checker.py`, индикаторы в `indicators.py`
2. **16 рабочих стратегий** — 9 LONG + 7 SHORT, все протестированы на 2024-2025
3. **11 индикаторов** — RSI, EMA, Stochastic, MACD, Bollinger, ATR, Volume
4. **Worker режим** — встроен в Monitor, может работать в `signal` (уведомления) или `trade` (торговля)
5. **Strategy Checker** — универсальный валидатор условий для любых стратегий

### ❌ Чего нет
1. **`rsi_strategy.py`** — все RSI стратегии в `config.py`
2. **`workers/` папка** — Worker это роль Monitor, не отдельный модуль
3. **Отдельные файлы для каждой стратегии** — все в одном `config.py`

### 📦 Структура оптимальна для:
- Быстрого добавления новых стратегий (просто добавь в `config.py`)
- Переиспользования индикаторов (библиотека `indicators.py`)
- Единообразной проверки условий (`StrategyChecker`)
- Масштабирования (легко добавить новые индикаторы)

---

**Файл создан:** 2026-01-27  
**Автор:** CryptoDen Bot Analysis System
