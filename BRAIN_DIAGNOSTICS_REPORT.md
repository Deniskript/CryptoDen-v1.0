# 🔍 BRAIN DIAGNOSTICS REPORT

**Дата:** 2026-02-04 12:13  
**Статус:** ❌ КРИТИЧЕСКИЕ ОШИБКИ ОБНАРУЖЕНЫ

---

## 📊 РЕЗУЛЬТАТЫ ДИАГНОСТИКИ

### 1️⃣ Статус бота и модулей

#### API `/api/status`:
```
❌ 404 Not Found
```
**Вывод:** Endpoint не существует

#### API `/api/brain/status`:
```json
{
  "data": {
    "cache_size": 1,
    "coins_dynamic": 0,
    "coins_top20": 20,
    "min_confidence": 65,
    "model": "anthropic/claude-3-haiku-20240307",
    "name": "Adaptive Brain v3.0",
    "thresholds": {
      "fear_extreme_high": 80,
      "fear_extreme_low": 20,
      "funding_extreme": 0.1,
      "long_ratio_max": 70,
      "short_ratio_max": 70
    }
  },
  "success": true
}
```

**✅ Выводы:**
- Brain модуль инициализирован
- Модель: Claude 3 Haiku
- Min confidence: 65%
- 20 монет в top20
- 0 динамических монет

---

### 2️⃣ Последние логи Brain

```
[ERROR] app.brain.adaptive_brain:_ai_analyze:289 | AI analyze error: AI API error: 400
[ERROR] app.brain.adaptive_brain:_ai_analyze:289 | AI analyze error: AI API error: 400
[ERROR] app.brain.adaptive_brain:_ai_analyze:289 | AI analyze error: AI API error: 400
[ERROR] app.brain.adaptive_brain:analyze:128 | Brain analyze error for LINK: unsupported format string passed to NoneType.__format__
[ERROR] app.brain.adaptive_brain:_ai_analyze:289 | AI analyze error: AI API error: 400
...
(спам продолжается каждые 2-3 секунды)
```

**🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ:**

1. **AI API Error 400** (массовый спам)
   - OpenRouter API возвращает 400 Bad Request
   - Brain НЕ МОЖЕТ получить ответ от AI
   - Ошибка повторяется каждые 2-3 секунды

2. **Format String Error для LINK**
   - `unsupported format string passed to NoneType.__format__`
   - Попытка форматирования None значения
   - Ошибка специфична для символа LINK

---

### 3️⃣ Настройки Brain

```json
{
  "modules": {
    "brain": {
      "enabled": true,
      "mode": "signal"
    },
    "momentum": {
      "enabled": true,
      "mode": "auto"
    },
    "listing": {
      "enabled": true,
      "mode": "signal"
    },
    "grid": {
      "enabled": true,
      "mode": "signal"
    },
    "funding": {
      "enabled": true,
      "mode": "signal"
    },
    "arbitrage": {
      "enabled": false,
      "mode": "signal"
    }
  },
  "coins": {
    "BTC": true,
    "ETH": true,
    "BNB": true,
    "SOL": true,
    "XRP": true,
    "ADA": true,
    "DOGE": true,
    "LINK": true,
    "AVAX": true
  },
  "ai_confidence": 55,
  "risk_percent": 9,
  "max_trades": 4,
  "paper_trading": true,
  "ai_enabled": true
}
```

**✅ Выводы:**
- Brain включён (enabled=true)
- Режим: signal (только уведомления)
- AI Confidence: 55% (не слишком высоко)
- 9 монет активны
- Paper trading: true
- AI enabled: true

---

### 4️⃣ Код условий генерации сигнала

```python
async def analyze(self, symbol: str) -> BrainDecision:
    """Главный метод анализа"""
    try:
        if self._is_cached(symbol):
            return self._cache[symbol]
        
        market_data = await self._collect_market_data(symbol)
        regime = self._detect_regime(market_data)
        restrictions = self._check_restrictions(market_data)
        
        if self._has_critical_restriction(restrictions, market_data):
            decision = BrainDecision(
                action=TradeAction.WAIT,
                symbol=symbol,
                confidence=0,
                regime=regime,
                reasoning="Критические ограничения активны",
                restrictions=restrictions,
                source="brain"
            )
            self._save_to_cache(symbol, decision)
```

**Логика:**
- Проверка кэша
- Сбор данных рынка
- Детекция режима рынка
- Проверка ограничений
- Если есть критические ограничения → WAIT
- Если нет → AI анализ
- Если `confidence >= MIN_CONFIDENCE` (65%) → генерация сигнала

---

### 5️⃣ Статистика сделок

```json
{
  "trades": [
    {
      "id": "BTC_LONG_20260131_172531",
      "symbol": "BTC",
      "direction": "LONG",
      "entry": 79100,
      "exit": 77888.4,
      "pnl_percent": -1.53,
      "pnl_usd": -1.38,
      "result": "LOSS",
      "confidence": 78,
      "opened_at": "2026-01-31T17:25:31",
      "closed_at": "2026-01-31T18:39:10"
    },
    {
      "id": "ETH_LONG_20260131_180606",
      "symbol": "ETH",
      "direction": "LONG",
      "entry": 2405,
      "exit": 2326.97,
      "pnl_percent": -3.24,
      "pnl_usd": -2.92,
      "result": "LOSS",
      "confidence": 73,
      "opened_at": "2026-01-31T18:06:06",
      "closed_at": "2026-01-31T19:18:24"
    }
  ]
}
```

**Выводы:**
- Всего 2 сделки (обе 31 января)
- Обе убыточные (-1.53% и -3.24%)
- Confidence был высокий (78% и 73%)
- **С 31 января НЕТ НОВЫХ СДЕЛОК** (4 дня!)

---

### 6️⃣ Текущий статус бота

```json
{
  "running": true,
  "balance": 1000.0,
  "active_trades": 0,
  "paper_trading": true,
  "ai_enabled": true,
  "symbols": [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "DOGE", "LINK", "AVAX",
    "BTC_SHORT", "ETH_SHORT", "SOL_SHORT",
    "ADA_SHORT", "LINK_SHORT", "AVAX_SHORT", "BNB_SHORT"
  ],
  "last_update": "2026-02-04T12:13:04.801408"
}
```

**✅ Бот работает:**
- running: true
- Баланс: $1000
- Активных сделок: 0
- AI включён
- 16 символов в отслеживании

---

## 🎯 ГЛАВНЫЕ ПРИЧИНЫ ОТСУТСТВИЯ СИГНАЛОВ

### 🚨 1. КРИТИЧНО: AI API Error 400

**Проблема:**
```
ERROR | AI analyze error: AI API error: 400
```

**Что это значит:**
- OpenRouter API возвращает 400 Bad Request
- Brain НЕ МОЖЕТ получить ответ от AI модели
- БЕЗ AI анализа НЕТ СИГНАЛОВ!

**Возможные причины:**
1. ❌ **Неправильный API ключ OpenRouter**
2. ❌ **Неправильный формат запроса к API**
3. ❌ **Закончился лимит OpenRouter**
4. ❌ **Неправильное имя модели** (`claude-3-haiku-20240307`)
5. ❌ **Слишком длинный промпт** (превышает лимит токенов)

---

### 🚨 2. КРИТИЧНО: Format Error для LINK

**Проблема:**
```
ERROR | Brain analyze error for LINK: unsupported format string passed to NoneType.__format__
```

**Что это значит:**
- Попытка форматирования None значения
- Скорее всего цена или индикатор = None
- Brain крашится при анализе LINK

**Где искать:**
- Метод `_collect_market_data()` для LINK
- Проверить что `bybit_client.get_price("LINK")` возвращает
- Проверить индикаторы для LINK

---

### ⚠️ 3. Возможно: Критические ограничения

**Что проверяет Brain перед генерацией сигнала:**
1. Fear & Greed < 20 или > 80
2. Long Ratio < 30 или > 70
3. Funding Rate < -0.1 или > 0.1

**Текущие данные:**
- Fear & Greed: 14 (экстремальный страх) ✅ Подходит для LONG!
- Long Ratio: 70.8% ⚠️ Много лонгов = запрет на LONG!
- Funding: +0.0089 (нейтрально)

**Вывод:**
Даже если бы AI работал, Brain мог бы блокировать LONG сигналы из-за высокого Long Ratio!

---

## 📋 ИТОГОВАЯ ТАБЛИЦА

| Компонент | Статус | Проблема |
|-----------|--------|----------|
| **Бот running** | ✅ TRUE | - |
| **Brain enabled** | ✅ TRUE | - |
| **AI enabled** | ✅ TRUE | - |
| **Min confidence** | ✅ 55% | Не слишком высоко |
| **AI API** | ❌ **ERROR 400** | **Не работает!** |
| **LINK анализ** | ❌ **Format Error** | **Крашится!** |
| **Long Ratio** | ⚠️ 70.8% | Блокирует LONG |
| **Сигналы** | ❌ 0 за 4 дня | Из-за ошибок |

---

## 🔧 ЧТО НУЖНО ИСПРАВИТЬ

### 1️⃣ ПРИОРИТЕТ 1: Исправить AI API Error 400

**Проверить:**
```bash
# 1. API ключ OpenRouter
grep OPENROUTER_API_KEY /root/crypto-bot/.env

# 2. Тестовый запрос к OpenRouter
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-3-haiku-20240307",
    "messages": [{"role": "user", "content": "test"}]
  }'
```

**Возможные решения:**
- Проверить что API ключ валидный
- Проверить баланс OpenRouter
- Изменить модель на более новую
- Уменьшить длину промпта

---

### 2️⃣ ПРИОРИТЕТ 2: Исправить Format Error для LINK

**Найти где падает:**
```bash
# Найти строку 128 в adaptive_brain.py
sed -n '120,135p' /root/crypto-bot/app/brain/adaptive_brain.py

# Проверить что возвращает get_price для LINK
python3 -c "
import asyncio
from app.trading.bybit.client import bybit_client
print(asyncio.run(bybit_client.get_price('LINK')))
"
```

---

### 3️⃣ ПРИОРИТЕТ 3: Отключить LINK временно

Если LINK крашит Brain, временно исключить:
```json
// В webapp_settings.json:
"coins": {
  "LINK": false  // Отключить
}
```

---

## 📊 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ ПОСЛЕ ИСПРАВЛЕНИЯ

После исправления AI API:
- Brain сможет анализировать рынок
- Появятся логи типа:
  ```
  [INFO] Brain: Analyzing BTC, RSI=55, F&G=14
  [INFO] Brain: BTC regime=ACCUMULATION, confidence=72%
  ```
- При confidence >= 65% → генерация сигналов
- Частота: **1-5 сигналов в день** (при экстремальных условиях)

---

## 🎯 ГЛАВНЫЙ ВЫВОД

**ПОЧЕМУ НЕТ СИГНАЛОВ:**

1. ❌ **AI API возвращает 400 ошибку** → Brain не может анализировать
2. ❌ **LINK крашит Brain** → анализ прерывается
3. ⚠️ **Long Ratio 70.8%** → даже если бы работало, блокировал бы LONG

**ИТОГО:**  
Brain **ФИЗИЧЕСКИ НЕ МОЖЕТ** генерировать сигналы из-за ошибок!

**ПЕРВЫЙ ШАГ:**  
Исправить AI API Error 400!

---

**Конец отчёта**
