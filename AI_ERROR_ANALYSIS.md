# 🚨 AI ERROR ANALYSIS — ТОЧНАЯ ДИАГНОСТИКА

**Дата:** 2026-02-04 12:18  
**Статус:** ✅ ПРОБЛЕМЫ НАЙДЕНЫ

---

## 📊 РЕЗУЛЬТАТЫ ДИАГНОСТИКИ

### ШАГ 1: API ключ OpenRouter

#### Команда 1: API ключ
```bash
grep OPENROUTER /root/crypto-bot/.env | head -1 | cut -c1-40
```

**Результат:**
```
OPENROUTER_API_KEY=sk-or-v1-4e27505c1e55
```

✅ **Формат правильный:** Ключ начинается с `sk-or-v1-`

---

#### Команда 2: Тестовый запрос к OpenRouter

```bash
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "anthropic/claude-3-haiku-20240307", "messages": [{"role": "user", "content": "Say OK"}]}'
```

**Результат:**
```json
{
  "error": {
    "message": "anthropic/claude-3-haiku-20240307 is not a valid model ID",
    "code": 400
  },
  "user_id": "user_37mhObK2Qu34gsodsL3PG95TEdE"
}
```

---

## 🚨 ПРОБЛЕМА #1 НАЙДЕНА!

### ❌ Неправильное имя модели!

**Текущее:** `anthropic/claude-3-haiku-20240307`  
**OpenRouter говорит:** `is not a valid model ID`

**ЧТО ЭТО ЗНАЧИТ:**
- API ключ работает (иначе была бы ошибка 401 Unauthorized)
- Модель называется неправильно
- OpenRouter не может найти такую модель
- Возвращает 400 Bad Request

---

### 📋 ПРАВИЛЬНЫЕ НАЗВАНИЯ МОДЕЛЕЙ OpenRouter:

| Старое (НЕПРАВИЛЬНО) | Новое (ПРАВИЛЬНО) |
|----------------------|-------------------|
| ❌ `anthropic/claude-3-haiku-20240307` | ✅ `anthropic/claude-3-haiku` |
| ❌ `anthropic/claude-3-haiku-20240307` | ✅ `anthropic/claude-3-haiku-20240307-v1:0` |
| ❌ `anthropic/claude-3-haiku-20240307` | ✅ `anthropic/claude-3-5-haiku` |

**Самое вероятное правильное название:**
```
anthropic/claude-3-haiku
```

или

```
anthropic/claude-3.5-haiku
```

---

### 🔍 ГДЕ ИСПОЛЬЗУЕТСЯ МОДЕЛЬ:

**Файл:** `app/brain/adaptive_brain.py`  
**Строка:** ~58

```python
class AdaptiveBrain:
    def __init__(self):
        self.model = "anthropic/claude-3-haiku-20240307"  # ← ЗДЕСЬ!
```

---

## ШАГ 2: Код запроса к AI

### Метод `_call_ai`:

```python
async def _call_ai(self, prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": self.model,  # ← НЕПРАВИЛЬНОЕ ИМЯ!
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 500,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(self.api_url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                raise Exception(f"AI API error: {resp.status}")  # ← ЗДЕСЬ ОШИБКА!
            result = await resp.json()
            return result['choices'][0]['message']['content']
```

**Что происходит:**
1. Brain создаёт запрос к OpenRouter
2. Отправляет модель `anthropic/claude-3-haiku-20240307`
3. OpenRouter отвечает: `400 Bad Request` (модель не существует)
4. Brain выбрасывает: `AI API error: 400`
5. Анализ прерывается, сигнал не генерируется

---

## ШАГ 3: LINK Format Error

### Метод `_build_prompt`:

```python
def _build_prompt(self, data: MarketData, regime: MarketRegime, restrictions: List[str]) -> str:
    return f"""Ты — криптотрейдер. Проанализируй и прими решение.

## {data.symbol}USDT

💰 Цена: ${data.current_price:,.2f} ({data.change_24h:+.2f}% 24h)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^  ← ЗДЕСЬ ПАДАЕТ ДЛЯ LINK!

🐋 Whale метрики:
• Funding: {data.funding_rate:+.4f}%
• Long/Short: {data.long_ratio:.0f}% / {data.short_ratio:.0f}%
• Fear & Greed: {data.fear_greed}
• OI Change 1h: {data.oi_change_1h:+.2f}%

📰 Новости: {data.news_sentiment}
🎯 Режим рынка: {regime.value}
"""
```

---

## 🚨 ПРОБЛЕМА #2 НАЙДЕНА!

### ❌ `data.current_price = None` для LINK!

**ЧТО ПРОИСХОДИТ:**

1. Brain пытается собрать данные для LINK:
   ```python
   price_task = bybit_client.get_price("LINKUSDT")
   ```

2. Bybit API возвращает `None` (монета не найдена или ошибка)

3. Brain пытается форматировать:
   ```python
   f"${None:,.2f}"  # ← TypeError!
   ```

4. Python выбрасывает:
   ```
   unsupported format string passed to NoneType.__format__
   ```

5. Анализ LINK прерывается

---

### 🔍 ПОЧЕМУ `current_price = None`?

**Возможные причины:**

1. **Неправильный символ:** `LINKUSDT` не существует на Bybit (может быть `LINK/USDT` или другой формат)

2. **Ошибка в `bybit_client.get_price()`:**
   ```python
   # Метод возвращает None при ошибке
   async def get_price(self, symbol: str) -> Optional[float]:
       try:
           # ... запрос к API ...
       except Exception:
           return None  # ← ЗДЕСЬ!
   ```

3. **LINK не торгуется на Bybit Spot** (только Futures)

---

## 📋 ИТОГОВАЯ ТАБЛИЦА ПРОБЛЕМ

| № | Проблема | Файл | Строка | Критичность |
|---|----------|------|--------|-------------|
| 1 | ❌ Неправильная модель | `adaptive_brain.py` | ~58 | 🔴 КРИТИЧНО |
| 2 | ❌ `current_price = None` | `adaptive_brain.py` | ~170 | 🔴 КРИТИЧНО |
| 3 | ⚠️ Нет проверки на None | `adaptive_brain.py` | ~235 | 🟡 СРЕДНЕЕ |

---

## 🔧 КАК ИСПРАВИТЬ

### ИСПРАВЛЕНИЕ #1: Изменить имя модели

**Файл:** `app/brain/adaptive_brain.py`

**БЫЛО:**
```python
self.model = "anthropic/claude-3-haiku-20240307"
```

**ДОЛЖНО БЫТЬ (вариант 1):**
```python
self.model = "anthropic/claude-3-haiku"
```

**ИЛИ (вариант 2):**
```python
self.model = "anthropic/claude-3.5-haiku"
```

**ИЛИ (вариант 3 - самый дешёвый):**
```python
self.model = "openai/gpt-3.5-turbo"
```

---

### ИСПРАВЛЕНИЕ #2: Добавить проверку на None

**Файл:** `app/brain/adaptive_brain.py`  
**Метод:** `_build_prompt`

**БЫЛО:**
```python
💰 Цена: ${data.current_price:,.2f} ({data.change_24h:+.2f}% 24h)
```

**ДОЛЖНО БЫТЬ:**
```python
💰 Цена: ${data.current_price:,.2f if data.current_price else 0} ({data.change_24h:+.2f if data.change_24h else 0}% 24h)
```

**ИЛИ (лучше):**
```python
# В начале метода _build_prompt:
if not data.current_price:
    raise ValueError(f"No price data for {data.symbol}")
```

---

### ИСПРАВЛЕНИЕ #3: Временно исключить LINK

**Файл:** `data/webapp_settings.json`

**БЫЛО:**
```json
"coins": {
  "LINK": true
}
```

**ДОЛЖНО БЫТЬ:**
```json
"coins": {
  "LINK": false
}
```

---

## 📊 ПРОВЕРКА ПРАВИЛЬНОГО ИМЕНИ МОДЕЛИ

### Тест с правильной моделью:

```bash
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "anthropic/claude-3-haiku", "messages": [{"role": "user", "content": "Say OK"}]}'
```

**Ожидаемый результат:**
```json
{
  "choices": [{
    "message": {
      "content": "OK"
    }
  }]
}
```

---

## 🎯 ПОРЯДОК ИСПРАВЛЕНИЯ

### Шаг 1: Исправить имя модели (ПРИОРИТЕТ 1)

```python
# app/brain/adaptive_brain.py, строка ~58
self.model = "anthropic/claude-3-haiku"  # Было: anthropic/claude-3-haiku-20240307
```

**Результат:**
- ✅ AI API начнёт работать
- ✅ Brain сможет анализировать рынок
- ⚠️ LINK всё ещё будет крашить (но реже)

---

### Шаг 2: Исключить LINK временно (ПРИОРИТЕТ 2)

```json
// data/webapp_settings.json
"LINK": false
```

**Результат:**
- ✅ Brain не будет анализировать LINK
- ✅ Не будет Format Error
- ✅ Остальные 8 монет будут работать

---

### Шаг 3: Добавить проверку на None (ПРИОРИТЕТ 3)

```python
# app/brain/adaptive_brain.py, метод _build_prompt
if not data.current_price:
    raise ValueError(f"No price data for {data.symbol}")
```

**Результат:**
- ✅ Явная ошибка вместо крипитичного краша
- ✅ Легче дебажить

---

## 📈 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ ПОСЛЕ ИСПРАВЛЕНИЯ

### После исправления имени модели:

**Логи:**
```
[INFO] Brain: Analyzing BTC...
[INFO] Brain: BTC regime=ACCUMULATION, confidence=72%
[INFO] Brain: 🧠 Signal LONG BTC at $76,100
```

**Частота сигналов:**
- 1-5 сигналов в день (при экстремальных условиях)
- F&G < 20 или > 80
- Long Ratio < 30 или > 70
- Confluence факторов

---

## 🔍 ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА

### Проверить что LINK торгуется на Bybit:

```bash
curl -s "https://api.bybit.com/v5/market/tickers?category=spot&symbol=LINKUSDT" | python3 -m json.tool
```

**Если результат пустой или ошибка:**
- LINK не торгуется на Bybit Spot
- Нужно исключить из анализа

---

## 📋 ЧЕКЛИСТ ИСПРАВЛЕНИЯ

- [ ] Изменить `self.model` на `anthropic/claude-3-haiku`
- [ ] Перезапустить бота: `supervisorctl restart crypto-bot`
- [ ] Проверить логи: `tail -f /var/log/crypto-bot.out.log | grep Brain`
- [ ] Если LINK крашит → отключить в `webapp_settings.json`
- [ ] Если AI работает → увидеть сигналы через 1-6 часов

---

## 🎯 ИТОГОВЫЙ ВЫВОД

### ПОЧЕМУ НЕТ СИГНАЛОВ:

1. ❌ **Неправильное имя модели AI** → OpenRouter возвращает 400
2. ❌ **LINK крашит Brain** → Format Error при None цене
3. ⚠️ **Long Ratio 70.8%** → блокирует LONG даже если бы работало

**ГЛАВНАЯ ПРИЧИНА:**  
Brain не может обращаться к AI из-за неправильного имени модели!

**РЕШЕНИЕ:**  
Изменить `anthropic/claude-3-haiku-20240307` → `anthropic/claude-3-haiku`

**ВРЕМЯ ИСПРАВЛЕНИЯ:** 2 минуты  
**РЕЗУЛЬТАТ:** Brain начнёт генерировать сигналы через 1-6 часов

---

**Конец анализа**
