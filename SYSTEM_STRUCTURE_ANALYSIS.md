# 🤖 CryptoDen — Анализ структуры системы и настроек

> **Дата:** 2026-01-28  
> **Основа:** Текущая конфигурация webapp_settings.json  
> **Цель:** Понять как работает система модулей и AI

---

## 📋 СОДЕРЖАНИЕ

1. [Текущие настройки (webapp_settings.json)](#текущие-настройки)
2. [AI Система](#ai-система)
3. [Модули и режимы](#модули-и-режимы)
4. [Архитектура Director AI](#архитектура-director-ai)
5. [Интеграция с Monitor](#интеграция-с-monitor)
6. [Поток данных](#поток-данных)
7. [Выводы](#выводы)

---

## 📊 ТЕКУЩИЕ НАСТРОЙКИ

### Файл: `data/webapp_settings.json`

```json
{
  "bybit_api_key": "",
  "bybit_api_secret": "",
  "bybit_testnet": true,
  "modules": {
    "arbitrage": {
      "enabled": false,
      "mode": "signal"
    },
    "director": {
      "enabled": true,
      "mode": "signal"
    },
    "funding": {
      "enabled": true,
      "mode": "signal"
    },
    "grid": {
      "enabled": true,
      "mode": "signal"
    },
    "listing": {
      "enabled": true,
      "mode": "signal"
    },
    "worker": {
      "enabled": true,
      "mode": "signal"
    }
  },
  "coins": {
    "ADA": true,
    "AVAX": true,
    "BNB": true,
    "BTC": true,
    "DOGE": true,
    "ETH": true,
    "LINK": true,
    "SOL": true,
    "XRP": true
  },
  "risk_percent": 9,
  "max_trades": 4,
  "ai_enabled": true,
  "ai_confidence": 55,
  "paper_trading": true
}
```

---

## 🔍 РАЗБОР НАСТРОЕК

### 1️⃣ Bybit API (Биржа)

```json
"bybit_api_key": "",         // ❌ НЕ установлен
"bybit_api_secret": "",      // ❌ НЕ установлен
"bybit_testnet": true        // ✅ Testnet режим
```

**Статус:** API ключи **пустые** → реальная торговля **невозможна**

**Что это означает:**
- Бот работает только в Paper Trading режиме
- Все сделки виртуальные
- Нет доступа к реальному балансу на Bybit
- Модули в режиме "auto" будут логировать, но не торговать

---

### 2️⃣ Модули (Торговые стратегии)

```json
"modules": {
  "arbitrage":  { "enabled": false, "mode": "signal" },  // ❌ Отключён
  "director":   { "enabled": true,  "mode": "signal" },  // ✅ Сигналы
  "funding":    { "enabled": true,  "mode": "signal" },  // ✅ Сигналы
  "grid":       { "enabled": true,  "mode": "signal" },  // ✅ Сигналы
  "listing":    { "enabled": true,  "mode": "signal" },  // ✅ Сигналы
  "worker":     { "enabled": true,  "mode": "signal" }   // ✅ Сигналы
}
```

#### Режимы работы модуля:

| Режим | Описание | Действие |
|-------|----------|----------|
| **`signal`** | Только уведомления | Отправляет сообщение в Telegram |
| **`auto`** | Автоматическая торговля | Исполняет сделку через API (требует ключи) |

#### Статус модулей:

| Модуль | Enabled | Режим | Что делает сейчас |
|--------|---------|-------|-------------------|
| **arbitrage** | ❌ | signal | Отключён |
| **director** | ✅ | signal | 🎩 Директор — отправляет уведомления |
| **funding** | ✅ | signal | 💰 Фандинг — отправляет уведомления |
| **grid** | ✅ | signal | 📊 Сетка — отправляет уведомления |
| **listing** | ✅ | signal | 🆕 Листинги — отправляет уведомления |
| **worker** | ✅ | signal | 👷 Стратегии — отправляет уведомления |

---

### 3️⃣ Монеты (Торгуемые активы)

```json
"coins": {
  "ADA": true,   // ✅ Cardano
  "AVAX": true,  // ✅ Avalanche
  "BNB": true,   // ✅ Binance Coin
  "BTC": true,   // ✅ Bitcoin
  "DOGE": true,  // ✅ Dogecoin
  "ETH": true,   // ✅ Ethereum
  "LINK": true,  // ✅ Chainlink
  "SOL": true,   // ✅ Solana
  "XRP": true    // ✅ Ripple
}
```

**Активно:** 9 монет  
**Бот отслеживает:** Все эти монеты на предмет сигналов

---

### 4️⃣ Риск-менеджмент

```json
"risk_percent": 9,        // 9% от баланса на сделку
"max_trades": 4,          // Максимум 4 сделки одновременно
"paper_trading": true     // Виртуальная торговля
```

**Пример:**
- Баланс: $1000
- Размер сделки: $1000 × 9% = **$90 на сделку**
- Максимум открытых: **4 сделки** = $360 максимум

---

### 5️⃣ AI Настройки

```json
"ai_enabled": true,       // ✅ AI включён
"ai_confidence": 55       // Минимум 55% уверенности для сделки
```

**AI модели:**
- **Claude Sonnet 4** — торговые решения (дорого)
- **Claude 3.5 Haiku** — уведомления (дешёво ~$0.02/час)

**Что делает AI:**
1. Анализирует активные позиции
2. Двигает SL/TP
3. Рекомендует закрытие
4. Объясняет сигналы в Telegram

---

## 🧠 AI СИСТЕМА

### AI Модели в проекте:

```
app/core/config.py:
    ai_model = "anthropic/claude-sonnet-4"  # Основная модель

app/intelligence/haiku_explainer.py:
    MODEL = "anthropic/claude-3.5-haiku"    # Уведомления

app/brain/trading_ai.py:
    MODEL = "anthropic/claude-sonnet-4"     # Торговля
```

### Разделение ролей:

| Модель | Где используется | Стоимость | Назначение |
|--------|------------------|-----------|------------|
| **Claude 3.5 Haiku** | `haiku_explainer.py` | ~$0.02/час | Объяснения сигналов, новостей, статусов |
| **Claude Sonnet 4** | `trading_ai.py` | ~$0.10/запрос | Торговые решения, движение SL/TP |

---

## 📦 МОДУЛИ И РЕЖИМЫ

### Структура BaseModule

```python
# app/modules/base_module.py

@dataclass
class ModuleSignal:
    """Сигнал от модуля"""
    module_name: str
    symbol: str
    direction: str  # "LONG" | "SHORT" | "BUY" | "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str
    confidence: float = 0.7
    timestamp: datetime = None

class BaseModule(ABC):
    """Базовый класс для всех торговых модулей"""
    
    name: str = "base"
    enabled: bool = True
    
    @abstractmethod
    async def get_signals(self, market_data: Dict) -> List[ModuleSignal]:
        """Получить сигналы от модуля"""
        pass
    
    @abstractmethod
    async def get_status(self) -> Dict:
        """Статус модуля"""
        pass
```

### Как работает модуль:

```
1. Monitor вызывает module.get_signals(market_data)
   ↓
2. Модуль анализирует данные (цены, индикаторы, новости)
   ↓
3. Если условия выполнены → возвращает List[ModuleSignal]
   ↓
4. Monitor получает сигналы:
   - Режим "signal" → отправляет в Telegram
   - Режим "auto" → исполняет через Bybit API
```

---

## 🎩 АРХИТЕКТУРА DIRECTOR AI

### Файлы Director AI:

```
app/ai/
├── director_ai.py           # 57KB - DirectorAI + DirectorTrader
├── trading_coordinator.py   # 12KB - Координация
└── whale_ai.py              # 26KB - Whale метрики
```

### Director AI - Два режима:

#### 1️⃣ **TAKE_CONTROL** (Директор берёт управление)

```python
# app/ai/director_ai.py - DirectorTrader

async def should_take_control(whale, news, market) -> (bool, direction, reason):
    """
    7 сценариев для TAKE_CONTROL:
    
    1. Fear & Greed < 20 + бычьи новости → LONG
    2. Fear & Greed > 80 + медвежьи новости → SHORT
    3. Массовые ликвидации лонгов ($50M+) → LONG
    4. Массовые ликвидации шортов ($50M+) → SHORT
    5. Funding > 0.1% + Long Ratio > 70% → SHORT
    6. Funding < -0.1% + Long Ratio < 30% → LONG
    7. Extreme Fear (<15) + мало лонгов (<35%) → LONG
    """
    pass
```

**Когда Director активен:**
- Worker (стратегии) ждёт
- Director торгует САМ
- Размер позиции: 20% баланса (больше обычного)

#### 2️⃣ **CONTINUE** (Обычный режим)

```python
# Директор пассивен
# Worker работает с обычными стратегиями
# Размер позиции: 9% баланса (из настроек)
```

---

## 🔄 ИНТЕГРАЦИЯ С MONITOR

### Файл: `app/core/monitor.py`

#### Главный цикл (каждые 60 секунд):

```python
async def _check_for_signals(self):
    """
    ШАГ 0: Собираем данные
    - Whale AI метрики
    - Новости
    - Цены
    
    ШАГ 1: Director AI
    - should_take_control()?
      → YES: Director торгует, Worker ждёт
      → NO: переходим к Worker
    
    ШАГ 2: Grid Bot
    - check_orders() → сигналы
    - mode == "auto" → исполняем
    - mode == "signal" → уведомляем
    
    ШАГ 3: Funding Scalper
    - check_entries() → сигналы
    - mode == "auto" → исполняем
    - mode == "signal" → уведомляем
    
    ШАГ 4: Listing Hunter
    - check_new_listings() → сигналы
    - mode == "auto" → исполняем
    - mode == "signal" → уведомляем
    
    ШАГ 5: Worker (стратегии)
    - Только если Director НЕ контролирует
    - StrategyChecker → сигналы
    - AI анализ → финальное решение
    """
```

#### Логика Director в Monitor:

```python
# Строки 455-493 из app/core/monitor.py

# ШАГ 1: Director AI
director_took_control = False

if self.is_module_enabled('director') and not director_trader.is_controlling:
    try:
        should_take, direction, reason = await director_trader.should_take_control(
            whale_data, news_data, market_data
        )
        
        if should_take:
            director_took_control = True
            
            if self.can_auto_trade('director'):
                # AUTO режим — Director торгует сам
                logger.warning(f"🎩 Director AUTO: {direction} - {reason}")
                
                # Выбираем лучшую монету
                best_symbol = self._choose_best_symbol(direction)
                
                # Рассчитываем размер (20% для Director)
                trade_size = self.current_balance * 0.20
                
                trade = await director_trader.execute_trade(
                    symbol=best_symbol,
                    direction=direction,
                    size_usdt=trade_size,
                    reason=reason
                )
                
                if trade:
                    logger.info(f"🎩 Director opened {best_symbol} {direction}")
                    await self._notify_director_executed(trade, reason)
                    return  # Director управляет
            else:
                # SIGNAL режим — только уведомление
                logger.info(f"🎩 Director SIGNAL: {direction} - {reason}")
                await self._notify_director_signal(direction, reason)
    
    except Exception as e:
        logger.error(f"Director AI error: {e}")

# ШАГ 2: Если Director управляет - Worker ждёт
if director_trader.is_controlling:
    active = len(director_trader.active_trades)
    logger.debug(f"🎩 Director controlling, {active} trades active")
    return  # Выходим, не проверяем Worker
```

---

## 📊 ПОТОК ДАННЫХ

```
┌─────────────────────────────────────────────────────────────┐
│                    WEBAPP SETTINGS                          │
│                  (webapp_settings.json)                     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                   TELEGRAM BOT                              │
│             (_apply_settings method)                        │
│                                                             │
│  • Читает webapp_settings.json                              │
│  • Применяет к market_monitor:                              │
│    - module_settings (enabled/mode)                         │
│    - symbols (монеты)                                       │
│    - risk_percent                                           │
│    - max_trades                                             │
│    - ai_enabled                                             │
│    - has_api_keys (проверка ключей)                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                  MARKET MONITOR                             │
│                  (Главный цикл)                             │
│                                                             │
│  Каждые 60 секунд:                                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. Получить цены с Bybit                            │   │
│  │ 2. Обновить Whale AI метрики (каждые 5 мин)         │   │
│  │ 3. Обновить новости (каждые 5 мин)                  │   │
│  │ 4. Проверить активные позиции с AI                  │   │
│  │ 5. Проверить модули на новые сигналы:               │   │
│  │                                                      │   │
│  │    🎩 Director AI:                                   │   │
│  │       - should_take_control()?                       │   │
│  │       - mode: signal → уведомление                   │   │
│  │       - mode: auto → торговля (20% баланса)         │   │
│  │                                                      │   │
│  │    📊 Grid Bot:                                      │   │
│  │       - check_orders()                               │   │
│  │       - mode: signal → уведомление                   │   │
│  │       - mode: auto → виртуально (нет API)           │   │
│  │                                                      │   │
│  │    💰 Funding:                                       │   │
│  │       - check_entries()                              │   │
│  │       - mode: signal → уведомление                   │   │
│  │       - mode: auto → логирование                     │   │
│  │                                                      │   │
│  │    🆕 Listing:                                       │   │
│  │       - check_new_listings()                         │   │
│  │       - mode: signal → уведомление                   │   │
│  │       - mode: auto → логирование                     │   │
│  │                                                      │   │
│  │    👷 Worker:                                        │   │
│  │       - Только если Director НЕ контролирует         │   │
│  │       - StrategyChecker → сигналы                    │   │
│  │       - AI анализ → финальное решение                │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│                 SMART NOTIFICATIONS                         │
│                                                             │
│  • Получает сигналы от Monitor                              │
│  • Добавляет в очередь с приоритетом                        │
│  • Вызывает Haiku AI для объяснений                         │
│  • Отправляет в Telegram с интервалом 90 сек                │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 ТЕКУЩЕЕ СОСТОЯНИЕ СИСТЕМЫ

### ✅ Что работает:

1. **Уведомления:**
   - ✅ SmartNotifications с AI объяснениями
   - ✅ Haiku AI (~$0.02/час)
   - ✅ Приоритеты и очередь
   - ✅ Интервал 90 сек между сообщениями

2. **Модули (Signal режим):**
   - ✅ Director — отслеживает события
   - ✅ Grid — виртуальные ордера
   - ✅ Funding — отслеживает ставки
   - ✅ Listing — новые листинги
   - ✅ Worker — технические стратегии

3. **AI:**
   - ✅ Claude 3.5 Haiku для уведомлений
   - ✅ Claude Sonnet 4 для торговли (не используется активно)
   - ✅ Whale AI метрики
   - ✅ News Parser

4. **Мониторинг:**
   - ✅ Цикл каждые 60 сек
   - ✅ 9 монет отслеживается
   - ✅ Paper trading активен

### ❌ Что НЕ работает:

1. **Реальная торговля:**
   - ❌ API ключи пустые → нет доступа к бирже
   - ❌ Grid Bot — только виртуально
   - ❌ Funding — только уведомления
   - ❌ Director AUTO — логирование вместо торговли

2. **Auto режим:**
   - ❌ Все модули в "signal" режиме
   - ❌ Auto режим требует API ключи
   - ❌ Без ключей — только уведомления

---

## 🎯 ВЫВОДЫ

### Текущая архитектура:

```
┌───────────────────────────────────────────────────┐
│         CRYPTODEN BOT (Текущее состояние)         │
│                                                   │
│  Режим: SIGNAL ONLY (уведомления)                 │
│  Trading: PAPER ONLY (виртуальный)                │
│  API: НЕТ КЛЮЧЕЙ                                  │
│                                                   │
│  ✅ Работает:                                     │
│     • Мониторинг рынка                            │
│     • Генерация сигналов                          │
│     • AI объяснения                               │
│     • Telegram уведомления                        │
│                                                   │
│  ❌ НЕ работает:                                  │
│     • Реальная торговля                           │
│     • Исполнение ордеров                          │
│     • Auto режим                                  │
└───────────────────────────────────────────────────┘
```

### Для реальной торговли нужно:

1. **Добавить API ключи:**
   ```json
   "bybit_api_key": "YOUR_REAL_KEY",
   "bybit_api_secret": "YOUR_REAL_SECRET",
   "bybit_testnet": false
   ```

2. **Переключить режимы:**
   ```json
   "paper_trading": false,
   "modules": {
     "director": { "mode": "auto" },
     "grid": { "mode": "auto" }
   }
   ```

3. **Доработать модули:**
   - Grid Bot: добавить реальные Bybit ордера
   - Funding: добавить исполнение
   - Listing: добавить авто-торговлю

---

## 🎩 DIRECTOR AI — ПОЛНЫЙ КОД

### Файл: `app/ai/director_ai.py` (1348 строк)

#### Структура классов:

```python
# 1. ENUMS И DATACLASSES
class TradingMode(Enum):
    AUTO = "auto"           # Работник работает сам
    SUPERVISED = "supervised"  # Директор наблюдает
    MANUAL = "manual"       # Директор управляет вручную
    PAUSED = "paused"       # Торговля остановлена

class DirectorDecision(Enum):
    CONTINUE = "continue"           # Работник продолжает
    CLOSE_ALL = "close_all"         # Закрыть все позиции
    CLOSE_LONGS = "close_longs"     # Закрыть только лонги
    CLOSE_SHORTS = "close_shorts"   # Закрыть только шорты
    PAUSE_NEW = "pause_new"         # Не открывать новые
    TAKE_CONTROL = "take_control"   # Директор берёт управление
    REDUCE_SIZE = "reduce_size"     # Уменьшить размер позиций
    AGGRESSIVE_LONG = "aggressive_long"   # Агрессивно лонг
    AGGRESSIVE_SHORT = "aggressive_short" # Агрессивно шорт

@dataclass
class DirectorCommand:
    """Команда от Директора"""
    decision: DirectorDecision
    mode: TradingMode
    reason: str
    details: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    valid_until: datetime = None  # Действует 30 мин

@dataclass
class MarketSituation:
    """Полная картина рынка для анализа"""
    # От Whale AI
    whale_alert_level: str = "calm"
    fear_greed: int = 50
    long_ratio: float = 50
    funding_rate: float = 0
    oi_change_1h: float = 0
    oi_change_24h: float = 0
    
    # От News AI
    news_sentiment: str = "neutral"
    market_mode: str = "NORMAL"
    important_event_soon: bool = False
    
    # Позиции
    open_positions: int = 0
    total_pnl: float = 0
    
    # Риск
    risk_level: str = "normal"  # low, normal, elevated, high, extreme
    risk_score: int = 0  # 0-100
    recommended_action: str = ""

# 2. DIRECTOR AI (АНАЛИТИК)
class DirectorAI:
    """
    🎩 Director AI — Главный аналитик
    
    НЕ торгует сам, только анализирует и даёт команды:
    - Слушает Whale AI
    - Анализирует новости
    - Принимает решения (DirectorCommand)
    - Управляет флагами (allow_new_longs, allow_new_shorts)
    """
    
    async def analyze_situation() -> MarketSituation:
        """Собрать данные от всех источников"""
        pass
    
    def _calculate_risk(situation) -> (risk_score, risk_level):
        """Рассчитать риск 0-100 по метрикам"""
        # 1. Whale alerts (0-40 points)
        # 2. Экстремальный Long/Short (0-20 points)
        # 3. Fear & Greed экстремумы (0-15 points)
        # 4. Важные новости/события (0-20 points)
        # 5. Funding Rate экстремумы (0-15 points)
        # 6. OI резкие изменения (0-10 points)
        pass
    
    async def make_decision() -> DirectorCommand:
        """
        🧠 Главный метод — принятие решения
        
        Логика:
        - risk >= 60 (extreme): CLOSE_ALL, MANUAL mode
        - risk 45-59 (high): CLOSE_LONGS/SHORTS, SUPERVISED
        - risk 25-44 (elevated): REDUCE_SIZE
        - risk < 25 (normal): CONTINUE или AGGRESSIVE
        """
        pass
    
    def can_open_trade(direction: str) -> (bool, reason):
        """Проверка перед открытием сделки Worker"""
        pass

# 3. DIRECTOR TRADER (АКТИВНЫЙ ТРЕЙДЕР)
@dataclass
class DirectorTrade:
    """Сделка открытая Директором лично"""
    id: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    size_usd: float
    reason: str
    opened_at: datetime
    
    # Трейлинг
    trailing_activated: bool = False
    highest_price: float = 0.0
    lowest_price: float = float('inf')
    adjustments_count: int = 0

class DirectorTrader:
    """
    🎩 Director как активный трейдер
    
    Функции:
    - should_take_control() → проверка 7 сценариев
    - execute_trade() → открытие позиции
    - _manage_trade() → цикл управления (каждые 10 сек!)
    - _update_trailing_stop() → динамический SL
    - _check_news_exit() → выход по новостям
    - _check_whale_exit() → выход по метрикам
    - _close_trade() → закрытие позиции
    """
    
    async def should_take_control(whale, news, market) -> (bool, direction, reason):
        """
        🎩 7 СЦЕНАРИЕВ ДЛЯ TAKE_CONTROL:
        
        1. Fear & Greed < 20 + бычьи новости → LONG
        2. Fear & Greed > 80 + медвежьи новости → SHORT
        3. Массовые ликвидации лонгов ($50M+) → LONG
        4. Массовые ликвидации шортов ($50M+) → SHORT
        5. Funding > 0.1% + Long Ratio > 70% → SHORT
        6. Funding < -0.1% + Long Ratio < 30% → LONG
        7. Extreme Fear (<15) + мало лонгов (<35%) → LONG
        8. Extreme Greed (>85) + много лонгов (>65%) → SHORT
        """
        pass
    
    async def execute_trade(symbol, direction, reason, size_usd):
        """
        Открыть позицию Director:
        - Размер: 20% баланса (агрессивно!)
        - SL: ±2%
        - TP: ±4% (2:1 ratio)
        - Запустить _manage_trade() в фоне
        """
        pass
    
    async def _manage_trade(trade: DirectorTrade):
        """
        🎩 Цикл управления (каждые 10 секунд!)
        
        Проверки:
        1. Stop Loss
        2. Take Profit
        3. Trailing Stop
        4. Новости (каждые 60 сек)
        5. Whale метрики
        6. Максимальное время (24 часа)
        """
        pass
    
    async def _update_trailing_stop(trade, current_price):
        """
        Trailing Stop Logic:
        - Активация: после +0.5% профита
        - Дистанция: 0.3% от highest_price
        - LONG: двигаем SL вверх
        - SHORT: двигаем SL вниз
        """
        pass
```

### Ключевые моменты:

#### 1️⃣ **Два класса — две роли:**

| Класс | Роль | Что делает |
|-------|------|------------|
| **DirectorAI** | Аналитик | Анализирует, решает, даёт команды |
| **DirectorTrader** | Трейдер | Открывает позиции, управляет в реалтайме |

#### 2️⃣ **Риск-система (0-100 баллов):**

```python
risk_score = 0
+ 40 points (Whale CRITICAL)
+ 20 points (Long Ratio > 75%)
+ 15 points (Fear & Greed < 15)
+ 20 points (Важное событие скоро)
+ 15 points (Funding > 0.15%)
+ 10 points (OI change 1h > 5%)
= 120 points (максимум)

Уровни:
- 0-24: normal
- 25-44: elevated → REDUCE_SIZE
- 45-59: high → PAUSE_NEW или CLOSE_LONGS/SHORTS
- 60+: extreme → CLOSE_ALL, MANUAL mode
```

#### 3️⃣ **DirectorTrader — агрессивный:**

```python
# Конфиг
config = {
    "check_interval_seconds": 10,  # Проверка каждые 10 сек
    "trailing_activation_percent": 0.5,  # Трейлинг после +0.5%
    "trailing_distance_percent": 0.3,  # Дистанция 0.3%
    "max_position_time_hours": 24,  # Максимум 24 часа
    "aggressive_tp_multiplier": 2.0,  # TP = SL * 2
    "news_check_interval": 60,  # Новости каждые 60 сек
}

# Размер позиции
size_usd = balance * 0.20  # 20% (vs 9% у Worker)

# SL/TP
SL: ±2%
TP: ±4% (2:1 ratio)
```

#### 4️⃣ **7 сценариев TAKE_CONTROL:**

```python
# 1. Extreme Fear + Bullish News
if fear_greed < 20 and news_sentiment == "bullish":
    return True, "LONG", "Extreme fear + bullish news"

# 2. Extreme Greed + Bearish News
if fear_greed > 80 and news_sentiment == "bearish":
    return True, "SHORT", "Extreme greed + bearish news"

# 3. Mass Long Liquidations
if liq_long > 50_000_000 and fear_greed < 25:
    return True, "LONG", "Mass long liquidations"

# 4. Mass Short Liquidations
if liq_short > 50_000_000 and fear_greed > 75:
    return True, "SHORT", "Mass short liquidations"

# 5. Extreme Funding (longs overpay)
if funding_rate > 0.1 and long_ratio > 70:
    return True, "SHORT", "Extreme funding"

# 6. Negative Funding (shorts overpay)
if funding_rate < -0.1 and long_ratio < 30:
    return True, "LONG", "Negative funding"

# 7. Extreme Fear + Low Longs
if fear_greed < 15 and long_ratio < 35:
    return True, "LONG", "Extreme fear + low longs"

# 8. Extreme Greed + High Longs
if fear_greed > 85 and long_ratio > 65:
    return True, "SHORT", "Extreme greed + high longs"
```

#### 5️⃣ **Уведомления в Telegram:**

```python
# При взятии управления
await _notify_take_control(direction, reason)
# → "⚡ CryptoDen взял управление! 📈 ПОКУПКА"

# При передаче управления обратно
await _notify_release_control(pnl_percent, close_reason)
# → "🔓 Управление передано Работнику ✅ +2.5%"
```

---

## 🔄 MONITOR — ПОЛНЫЙ МЕТОД _check_for_signals

### Файл: `app/core/monitor.py`

#### Метод: `async def _check_for_signals(prices)` (строки 408-608+)

```python
async def _check_for_signals(self, prices: Dict[str, float]):
    """
    🔍 Поиск торговых сигналов
    
    ЛОГИКА:
    1. Director проверяет TAKE_CONTROL
    2. Если взял — Worker ждёт
    3. Если нет — проверяем модули
    4. Worker работает только если Director не контролирует
    """
    
    # ========================================
    # 🐋 ШАГ 0: Собираем данные для Director
    # ========================================
    whale_metrics = {}
    if whale_ai.last_metrics:
        m = whale_ai.last_metrics
        whale_metrics = {
            "fear_greed": m.fear_greed_index,
            "long_ratio": m.long_ratio,
            "short_ratio": m.short_ratio,
            "funding_rate": m.funding_rate,
            "oi_change_1h": m.oi_change_1h,
            "oi_change_24h": m.oi_change_24h,
            "liq_long": m.liq_long,
            "liq_short": m.liq_short,
        }
    
    # Собираем контекст новостей
    news_context = {"sentiment": "neutral", "critical_count": 0}
    news = self.market_context.get("news", [])
    if news:
        bearish = sum(1 for n in news if n.get("sentiment", 0) < -0.2)
        bullish = sum(1 for n in news if n.get("sentiment", 0) > 0.2)
        critical = sum(1 for n in news if n.get("importance") == "HIGH")
        
        if bearish > bullish:
            news_context["sentiment"] = "bearish"
        elif bullish > bearish:
            news_context["sentiment"] = "bullish"
        news_context["critical_count"] = critical
    
    # ========================================
    # 🎩 ШАГ 1: Director AI
    # ========================================
    director_took_control = False
    
    if self.is_module_enabled('director') and not director_trader.is_controlling:
        try:
            # Вызываем should_take_control()
            should_take, direction, reason = await director_trader.should_take_control(
                whale_metrics=whale_metrics,
                news_context=news_context,
                market_data={"prices": prices}
            )
            
            if should_take:
                director_took_control = True
                
                if self.can_auto_trade('director'):
                    # AUTO режим — Director торгует сам
                    logger.warning(f"🎩 Director AUTO: {direction} - {reason}")
                    
                    best_symbol = "BTC"
                    trade_size = self.current_balance * 0.20  # 20%
                    
                    trade = await director_trader.execute_trade(
                        symbol=best_symbol,
                        direction=direction,
                        reason=reason,
                        size_usd=trade_size
                    )
                    
                    if trade:
                        logger.info(f"🎩 Director opened {best_symbol}")
                        await self._notify_director_executed(trade, reason)
                        return  # Выходим, Worker не работает
                else:
                    # SIGNAL режим — только уведомление
                    logger.info(f"🎩 Director SIGNAL: {direction} - {reason}")
                    await self._notify_director_signal(direction, reason)
        
        except Exception as e:
            logger.error(f"Director AI error: {e}")
    
    # ========================================
    # 🎩 ШАГ 2: Если Director управляет - ждём
    # ========================================
    if director_trader.is_controlling:
        active = len(director_trader.active_trades)
        logger.debug(f"🎩 Director controlling ({active} trades), Worker waiting...")
        return  # Выходим, Worker НЕ работает
    
    # ========================================
    # 📊 ШАГ 3: Grid Bot
    # ========================================
    if self.is_module_enabled('grid'):
        try:
            grid_signals = await grid_bot.get_signals({"prices": prices})
            
            for signal in grid_signals:
                if self.can_auto_trade('grid'):
                    logger.info(f"📊 Grid AUTO: {signal.direction} {signal.symbol}")
                    await self._execute_grid_trade(signal)
                    await self._notify_grid_executed(signal)
                else:
                    logger.info(f"📊 Grid SIGNAL: {signal.direction} {signal.symbol}")
                    await self._notify_grid_signal(signal)
        
        except Exception as e:
            logger.error(f"Grid Bot error: {e}")
    
    # ========================================
    # 💰 ШАГ 3.5: Funding Scalper
    # ========================================
    if self.is_module_enabled('funding'):
        try:
            funding_signals = await funding_scalper.get_signals({"prices": prices})
            
            for signal in funding_signals:
                if self.can_auto_trade('funding'):
                    logger.info(f"💰 Funding AUTO: {signal.direction}")
                    await self._execute_funding_trade(signal)
                    await self._notify_funding_executed(signal)
                else:
                    logger.info(f"💰 Funding SIGNAL: {signal.direction}")
                    await self._notify_funding_signal(signal)
        
        except Exception as e:
            logger.error(f"Funding Scalper error: {e}")
    
    # ========================================
    # 🔄 ШАГ 3.7: Arbitrage Scanner
    # ========================================
    if self.is_module_enabled('arbitrage'):
        try:
            arb_signals = await arbitrage_scanner.get_signals({"prices": prices})
            
            for signal in arb_signals:
                if self.can_auto_trade('arbitrage'):
                    await self._execute_arbitrage(signal)
                    await self._notify_arbitrage_executed(signal)
                else:
                    await self._notify_arbitrage_signal(signal)
        
        except Exception as e:
            logger.error(f"Arbitrage error: {e}")
    
    # ========================================
    # 🆕 ШАГ 3.8: Listing Hunter
    # ========================================
    if self.is_module_enabled('listing'):
        try:
            listing_signals = await listing_hunter.get_signals({"prices": prices})
            
            for signal in listing_signals:
                # Находим листинг
                listing = None
                for l in listing_hunter.history[-10:]:
                    if l.symbol == signal.symbol:
                        listing = l
                        break
                
                if not listing:
                    continue
                
                # LISTING_SCALP можно автоматизировать
                if listing.listing_type == ListingType.LISTING_SCALP:
                    if self.can_auto_trade('listing'):
                        await self._execute_listing_trade(signal, listing)
                        await self._notify_listing_executed(signal, listing)
                    else:
                        await self._notify_listing_signal(signal, listing)
                else:
                    # PRE_LISTING и LAUNCHPAD — только сигналы
                    await self._notify_listing_signal(signal, listing)
        
        except Exception as e:
            logger.error(f"Listing Hunter error: {e}")
    
    # ========================================
    # 👷 ШАГ 4: Worker (стратегии)
    # ========================================
    if not self.is_module_enabled('worker') or director_took_control:
        return  # Worker не работает
    
    # Worker ищет сигналы по стратегиям...
    # (остальной код)
```

### Ключевые моменты:

#### 1️⃣ **Приоритет Director:**
- Если `director_trader.is_controlling` → Worker ждёт
- Если `director_took_control` → Worker не запускается

#### 2️⃣ **Режимы модулей:**
```python
if self.can_auto_trade('module_name'):
    # AUTO — исполнить сделку
    await self._execute_trade(signal)
else:
    # SIGNAL — только уведомление
    await self._notify_signal(signal)
```

#### 3️⃣ **Порядок проверки:**
1. Director AI (приоритет #1)
2. Grid Bot
3. Funding Scalper
4. Arbitrage Scanner
5. Listing Hunter
6. Worker (стратегии) — ТОЛЬКО если Director не контролирует

---

## 🤖 AI МОДЕЛИ В ПРОЕКТЕ

### Файл: `app/core/config.py`

```python
ai_model: str = Field(
    default="anthropic/claude-sonnet-4", 
    env="AI_MODEL"
)
```

### Использование моделей:

| Файл | Модель | Назначение |
|------|--------|------------|
| `app/core/config.py` | `anthropic/claude-sonnet-4` | Основная модель (торговля) |
| `app/intelligence/haiku_explainer.py` | `anthropic/claude-3.5-haiku` | Уведомления (дешёвая) |
| `app/brain/trading_ai.py` | `anthropic/claude-sonnet-4` | Торговые решения |

### Как обновить модель:

#### Вариант 1: Через `.env`
```bash
# В файле .env
AI_MODEL=anthropic/claude-sonnet-4
```

#### Вариант 2: Напрямую в коде
```python
# app/core/config.py
ai_model: str = Field(default="anthropic/claude-sonnet-4", ...)

# app/intelligence/haiku_explainer.py
MODEL = "anthropic/claude-3.5-haiku"

# app/brain/trading_ai.py
MODEL = "anthropic/claude-sonnet-4"
```

### Доступные модели OpenRouter:

```python
# Топовые модели (дорогие)
"anthropic/claude-sonnet-4"          # $3.00/1M tokens (input)
"anthropic/claude-opus-4"            # $15.00/1M tokens
"openai/gpt-4-turbo"                 # $10.00/1M tokens

# Средние модели
"anthropic/claude-3.5-sonnet"        # $3.00/1M tokens
"openai/gpt-4o"                      # $5.00/1M tokens

# Дешёвые модели (для уведомлений)
"anthropic/claude-3.5-haiku"         # $0.80/1M tokens ✅
"anthropic/claude-3-haiku"           # $0.25/1M tokens
"meta-llama/llama-3.1-8b-instruct"   # $0.06/1M tokens

# Очень дешёвые (качество ниже)
"mistralai/mistral-7b-instruct"      # $0.07/1M tokens
```

### Стоимость текущей конфигурации:

```python
# Sonnet 4 (торговля)
- Редкие запросы (2-3 в час)
- ~$0.50/день = ~$15/месяц

# Haiku 3.5 (уведомления)
- Каждые 90 секунд
- ~$0.02/час = ~$0.50/день = ~$15/месяц

ИТОГО: ~$30/месяц на AI
```

---

**Последнее обновление:** 2026-01-28 03:30 UTC
