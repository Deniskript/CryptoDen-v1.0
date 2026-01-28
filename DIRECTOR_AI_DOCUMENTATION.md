# 🎩 DIRECTOR AI — Полная документация

**Дата:** 28 января 2026  
**Версия:** 2.0  
**Файл:** `app/ai/director_ai.py`

---

## 📌 ОБЗОР

**Director AI** — главный управляющий модуль бота, который:
- Анализирует рыночную ситуацию
- Принимает стратегические решения
- Управляет Работником (Worker)
- В критических ситуациях берёт торговлю на себя

---

## 📁 СТРУКТУРА ФАЙЛОВ

```
app/
├── ai/
│   └── director_ai.py        # 🎩 Главный файл (1349 строк)
│       ├── DirectorAI        # Аналитик и менеджер
│       └── DirectorTrader    # Активный трейдер
│
├── core/
│   ├── config.py             # Настройки AI модели
│   ├── constants.py          # Монеты, TP/SL, стратегии
│   └── monitor.py            # Интеграция с монитором
│
└── data/
    └── webapp_settings.json  # Пользовательские настройки
```

---

## ⚙️ КОНФИГУРАЦИЯ

### 1. Список монет (`app/core/constants.py`)

```python
COINS = [
    "BTC",   # Bitcoin
    "ETH",   # Ethereum
    "BNB",   # Binance Coin
    "SOL",   # Solana
    "XRP",   # Ripple
    "ADA",   # Cardano
    "DOGE",  # Dogecoin
    "MATIC", # Polygon
    "LINK",  # Chainlink
    "AVAX",  # Avalanche
]
```

### 2. Стратегии по монетам (`app/core/constants.py`)

```python
DEFAULT_STRATEGIES = {
    "BTC":   {"strategy": "RSI_OVERBOUGHT", "direction": "SHORT", "rsi_period": 21, "rsi_level": 80},
    "ETH":   {"strategy": "STOCH_MACD", "direction": "LONG", "stoch_period": 14, "stoch_level": 25},
    "BNB":   {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "SOL":   {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "XRP":   {"strategy": "RSI_STOCH_EMA", "direction": "LONG", "rsi_level": 40, "stoch_level": 30},
    "ADA":   {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "DOGE":  {"strategy": "STOCH_MACD", "direction": "LONG", "stoch_period": 14, "stoch_level": 30},
    "MATIC": {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "LINK":  {"strategy": "RSI_EMA", "direction": "LONG", "rsi_period": 14, "rsi_level": 30, "ema_period": 50},
    "AVAX":  {"strategy": "DOUBLE_BOTTOM", "direction": "LONG"},
}
```

### 3. Risk Management (`app/core/constants.py`)

```python
DEFAULT_TP_PERCENT = 0.3   # Take Profit +0.3%
DEFAULT_SL_PERCENT = 0.5   # Stop Loss -0.5%
DEFAULT_RR_RATIO = 0.6     # Risk/Reward = 0.6

MAX_OPEN_POSITIONS = 5
MAX_POSITION_SIZE_PERCENT = 20  # Max 20% баланса на позицию
```

### 4. Пользовательские настройки (`data/webapp_settings.json`)

```json
{
  "modules": {
    "director": {"enabled": true, "mode": "signal"}
  },
  "coins": {
    "BTC": true, "ETH": true, "BNB": true,
    "SOL": true, "XRP": true, "ADA": true,
    "DOGE": true, "LINK": true, "AVAX": true
  },
  "risk_percent": 9,
  "max_trades": 4,
  "ai_enabled": true,
  "ai_confidence": 55,
  "paper_trading": true
}
```

### 5. Director Trader Config (`app/ai/director_ai.py:688`)

```python
self.config = {
    "check_interval_seconds": 10,       # Проверка каждые 10 сек
    "trailing_activation_percent": 0.5, # Трейлинг после +0.5%
    "trailing_distance_percent": 0.3,   # Дистанция трейлинга 0.3%
    "max_position_time_hours": 24,      # Макс время в позиции
    "aggressive_tp_multiplier": 2.0,    # TP = 2x SL
    "news_check_interval": 60,          # Новости каждую минуту
}
```

---

## 🧠 КАК DIRECTOR ПРИНИМАЕТ РЕШЕНИЯ

### Архитектура принятия решений

```
┌─────────────────────────────────────────────────────────────────┐
│                    DIRECTOR AI WORKFLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. СБОР ДАННЫХ (параллельно):                                   │
│     ├── consult_friend() → Whale AI метрики                      │
│     ├── check_news() → NewsParser                                │
│     └── get_open_positions() → TradeManager                      │
│                           ↓                                      │
│  2. АНАЛИЗ СИТУАЦИИ:                                             │
│     └── analyze_situation() → MarketSituation                    │
│                           ↓                                      │
│  3. РАСЧЁТ РИСКА:                                                │
│     └── _calculate_risk() → risk_score (0-100)                   │
│                           ↓                                      │
│  4. ПРИНЯТИЕ РЕШЕНИЯ:                                            │
│     └── make_decision() → DirectorCommand                        │
│                           ↓                                      │
│  5. ИСПОЛНЕНИЕ:                                                  │
│     ├── Нормально → Worker продолжает                            │
│     ├── Повышенный риск → Уменьшить размер                       │
│     ├── Высокий риск → Закрыть позиции                           │
│     └── Критично → Director берёт TAKE_CONTROL                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 МЕТРИКИ ДЛЯ АНАЛИЗА

### MarketSituation (строка 60-90)

```python
@dataclass 
class MarketSituation:
    # От Whale AI
    whale_alert_level: str = "calm"  # calm, attention, warning, critical
    whale_message: str = ""
    funding_rate: float = 0          # -0.1 до +0.1+
    long_ratio: float = 50           # 0-100%
    short_ratio: float = 50          # 0-100%
    fear_greed: int = 50             # 0-100
    oi_change_1h: float = 0          # Изменение Open Interest
    oi_change_24h: float = 0
    
    # От News AI
    news_sentiment: str = "neutral"  # bullish, neutral, bearish
    market_mode: str = "NORMAL"      # NORMAL, NEWS_ALERT, WAIT_EVENT
    important_event_soon: bool = False
    event_name: str = ""
    
    # Позиции
    open_positions: int = 0
    long_positions: int = 0
    short_positions: int = 0
    total_pnl: float = 0
    
    # Расчётные
    risk_level: str = "normal"       # normal, elevated, high, extreme
    risk_score: int = 0              # 0-100
```

---

## 🎯 РАСЧЁТ РИСКА (Risk Score 0-100)

### Компоненты риска (`_calculate_risk`, строка 292)

| Фактор | Условие | Очки |
|--------|---------|------|
| **Whale Alert** | critical | +40 |
| | warning | +25 |
| | attention | +10 |
| **Long/Short Ratio** | > 75% или < 25% | +20 |
| | > 70% или < 30% | +15 |
| **Fear & Greed** | < 15 или > 85 | +15 |
| | < 25 или > 75 | +8 |
| **Важные события** | important_event_soon | +20 |
| | WAIT_EVENT mode | +15 |
| | NEWS_ALERT mode | +10 |
| **Funding Rate** | > 0.15% или < -0.15% | +15 |
| | > 0.1% | +10 |
| | > 0.05% | +5 |
| **OI Change 1h** | > 5% | +10 |
| | > 3% | +5 |

### Уровни риска

| Risk Score | Уровень | Действие |
|------------|---------|----------|
| 0-24 | 🟢 **normal** | Worker продолжает |
| 25-44 | 🟡 **elevated** | Уменьшить размер x0.5 |
| 45-59 | 🟠 **high** | Закрыть позиции, пауза |
| 60-100 | 🔴 **extreme** | TAKE_CONTROL |

---

## 📋 РЕШЕНИЯ ДИРЕКТОРА (DirectorDecision)

```python
class DirectorDecision(Enum):
    CONTINUE = "continue"           # Worker продолжает
    CLOSE_ALL = "close_all"         # Закрыть ВСЕ позиции
    CLOSE_LONGS = "close_longs"     # Закрыть только LONG
    CLOSE_SHORTS = "close_shorts"   # Закрыть только SHORT
    PAUSE_NEW = "pause_new"         # Не открывать новые
    TAKE_CONTROL = "take_control"   # Director торгует сам
    REDUCE_SIZE = "reduce_size"     # Размер x0.5
    AGGRESSIVE_LONG = "aggressive_long"   # Размер x1.5, LONG
    AGGRESSIVE_SHORT = "aggressive_short" # Размер x1.5, SHORT
```

---

## ⚡ 7 СЦЕНАРИЕВ TAKE_CONTROL

Director берёт управление в критических ситуациях:

### 1. Экстремальный страх + бычьи новости → LONG

```python
if fear_greed < 20 and news_sentiment == "bullish" and critical_count > 0:
    return True, "LONG", "Extreme fear + bullish news = STRONG BUY"
```

### 2. Экстремальная жадность + медвежьи новости → SHORT

```python
if fear_greed > 80 and news_sentiment == "bearish" and critical_count > 0:
    return True, "SHORT", "Extreme greed + bearish news = STRONG SELL"
```

### 3. Массовые ликвидации лонгов ($50M+) → LONG

```python
if liq_long > 50_000_000 and fear_greed < 25:
    return True, "LONG", "Mass long liquidations = potential reversal"
```

### 4. Массовые ликвидации шортов → SHORT

```python
if liq_short > 50_000_000 and fear_greed > 75:
    return True, "SHORT", "Mass short liquidations = potential reversal"
```

### 5. Экстремальный Funding (+0.1%) + много лонгов → SHORT

```python
if funding_rate > 0.1 and long_ratio > 70:
    return True, "SHORT", "Extreme funding rate = longs overextended"
```

### 6. Отрицательный Funding + мало лонгов → LONG

```python
if funding_rate < -0.1 and long_ratio < 30:
    return True, "LONG", "Negative funding = shorts overextended"
```

### 7. Extreme Fear (<15) + мало лонгов (<35%) → LONG

```python
if fear_greed < 15 and long_ratio < 35:
    return True, "LONG", "Extreme fear + low long ratio = BUY opportunity"
```

---

## 📈 ЛОГИКА ВХОДА В СДЕЛКУ

### При TAKE_CONTROL (`execute_trade`, строка 859)

```python
# Размер позиции
size_usd = balance * 0.20  # 20% от баланса (агрессивно!)

# Минимум $50
if size_usd < 50:
    return None

# Stop Loss / Take Profit
if direction == "LONG":
    stop_loss = current_price * 0.98    # -2%
    take_profit = current_price * 1.04  # +4% (Risk:Reward = 1:2)
else:
    stop_loss = current_price * 1.02    # +2%
    take_profit = current_price * 0.96  # -4%
```

### При обычной торговле Worker (`app/core/constants.py`)

```python
DEFAULT_TP_PERCENT = 0.3   # +0.3%
DEFAULT_SL_PERCENT = 0.5   # -0.5%
```

---

## 📰 КАК ИСПОЛЬЗУЮТСЯ НОВОСТИ

### 1. Получение новостей (`check_news`, строка 160)

```python
async def check_news(self) -> Dict:
    from app.intelligence.news_parser import news_parser
    
    context = await news_parser.get_market_context()
    mode = context.get("market_mode", "NORMAL")  
    news = context.get("news", [])
    
    # Анализ sentiment
    for item in news:
        s = item.get("sentiment", "").lower()
        if s in ["bearish", "negative"]:
            sentiment = "bearish"
        elif s in ["bullish", "positive"]:
            sentiment = "bullish"
        
        # Важные события
        if importance in ["HIGH", "CRITICAL"]:
            important_event = True
            event_name = item.get("title", "")
```

### 2. Market Modes

| Mode | Описание | Risk добавка |
|------|----------|--------------|
| NORMAL | Обычный режим | 0 |
| NEWS_ALERT | Важные новости | +10 |
| WAIT_EVENT | Ждём событие (FOMC, CPI) | +15 |

### 3. Critical Events (`app/core/constants.py`)

```python
CRITICAL_EVENTS = [
    "FOMC", "CPI", "NFP", "FED", "SEC",
    "hack", "exploit", "bankruptcy"
]
```

---

## 🤖 КАК ИСПОЛЬЗУЕТСЯ AI

### 1. AI Model Configuration

```python
# app/core/config.py
ai_model = "anthropic/claude-sonnet-4.5"

# app/ai/director_ai.py использует Whale AI для получения метрик
# AI напрямую не вызывается в DirectorAI
# Вместо этого используются данные от Whale AI
```

### 2. Whale AI Integration

```python
async def consult_friend(self) -> Dict:
    from app.ai.whale_ai import whale_ai, check_whale_activity
    
    alert = await check_whale_activity("BTC")
    metrics = whale_ai.last_metrics
    
    return {
        "alert_level": alert.level.value,
        "message": alert.message,
        "recommendation": alert.recommendation,
        "funding_rate": metrics.funding_rate,
        "long_ratio": metrics.long_ratio,
        "fear_greed": metrics.fear_greed_index,
        # ...
    }
```

---

## 🔄 РЕЖИМЫ РАБОТЫ

### TradingMode

```python
class TradingMode(Enum):
    AUTO = "auto"           # 🤖 Worker работает сам
    SUPERVISED = "supervised"  # 👀 Director наблюдает
    MANUAL = "manual"       # 🎩 Director торгует сам
    PAUSED = "paused"       # ⏸️ Торговля остановлена
```

### Переключение режимов

| Условие | Новый режим | Действия |
|---------|-------------|----------|
| risk < 25 | AUTO | Worker свободен |
| risk 25-44 | SUPERVISED | size x0.5 |
| risk 45-59 | SUPERVISED | Блокировка новых сделок |
| risk >= 60 | MANUAL | Director берёт управление |

---

## 📊 СТАТИСТИКА DIRECTOR

```python
# DirectorAI
decisions_made = 0          # Всего решений
interventions = 0           # Вмешательств
successful_interventions = 0

# DirectorTrader
stats = {
    "total_trades": 0,
    "winning_trades": 0,
    "total_pnl_percent": 0.0,
    "best_trade": 0.0,
    "worst_trade": 0.0,
    "avg_hold_time_minutes": 0.0,
}
```

---

## 🔔 УВЕДОМЛЕНИЯ В TELEGRAM

### При TAKE_CONTROL

```
⚡ *CryptoDen взял управление!*

📈 Направление: *ПОКУПКА*
📊 Причина: _Экстремальный страх + позитивные новости_

🤖 Автоматическое управление позицией
🔄 Проверка каждые 10 сек
```

### При Release Control

```
🔓 *Управление передано Работнику*

✅ Результат: *+2.45%*
📝 Причина выхода: _Достигнут Take Profit 🎯_

👷 Работник продолжает по стратегиям
```

---

## 🎯 ИТОГОВАЯ СХЕМА

```
┌──────────────────────────────────────────────────────────────┐
│                     DIRECTOR AI FLOW                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│     ┌─────────┐    ┌──────────┐    ┌─────────────┐          │
│     │Whale AI │    │News AI   │    │TradeManager │          │
│     └────┬────┘    └────┬─────┘    └──────┬──────┘          │
│          │              │                  │                 │
│          └──────────────┼──────────────────┘                 │
│                         ▼                                    │
│              ┌──────────────────────┐                        │
│              │  analyze_situation() │                        │
│              └──────────┬───────────┘                        │
│                         ▼                                    │
│              ┌──────────────────────┐                        │
│              │  _calculate_risk()   │                        │
│              │  Risk Score: 0-100   │                        │
│              └──────────┬───────────┘                        │
│                         ▼                                    │
│    ┌────────────────────┼────────────────────┐               │
│    │                    │                    │               │
│    ▼                    ▼                    ▼               │
│ 🟢 0-24             🟡 25-44            🔴 45-100            │
│ CONTINUE            REDUCE_SIZE         PAUSE/CLOSE         │
│                                              │               │
│                                              ▼               │
│                                    ┌─────────────────┐       │
│                                    │ Risk >= 60?    │       │
│                                    └────────┬────────┘       │
│                                             │ YES            │
│                                             ▼                │
│                                    ┌─────────────────┐       │
│                                    │ TAKE_CONTROL   │       │
│                                    │ DirectorTrader │       │
│                                    └─────────────────┘       │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 📝 БЫСТРАЯ СПРАВКА

### Файлы для изменения настроек:

| Что изменить | Файл | Строка |
|--------------|------|--------|
| Список монет | `app/core/constants.py` | 12 |
| TP/SL по умолчанию | `app/core/constants.py` | 44-45 |
| Стратегии | `app/core/constants.py` | 30-41 |
| AI модель | `app/core/config.py` | 27 |
| Пользовательские настройки | `data/webapp_settings.json` | — |
| Director SL/TP | `app/ai/director_ai.py` | 904-909 |
| Пороги риска | `app/ai/director_ai.py` | 359-366 |
| TAKE_CONTROL условия | `app/ai/director_ai.py` | 816-857 |

---

*Документация создана: 28.01.2026*
