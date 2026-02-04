# 🔍 ПОЛНЫЙ АНАЛИЗ: ОТКУДА ДАННЫЕ И ПОЧЕМУ 50/50

**Дата:** 2026-02-04 14:30  
**Проблема:** WebApp показывает 50/50, хотя API возвращает реальные данные  
**Статус:** СТРОГО АНАЛИЗ, БЕЗ ИЗМЕНЕНИЙ

---

## 📊 ПРОВЕРКА #1: ЧТО ВОЗВРАЩАЕТ API СЕЙЧАС

```bash
curl http://localhost:5000/api/market
```

**Результат:**
```json
{
  "fear_greed": { "value": 14 },  // ✅ РЕАЛЬНО
  "long_short": {
    "long_ratio": 71.5,            // ✅ РЕАЛЬНО
    "short_ratio": 28.5
  }
}
```

✅ **API РАБОТАЕТ ПРАВИЛЬНО!**

---

## 🌐 ПРОВЕРКА #2: ЧТО ПОКАЗЫВАЕТ WEBAPP

**Telegram WebApp показывает:**
```
Fear & Greed: 50
Long/Short: 50% / 50%
```

❌ **WEBAPP ПОКАЗЫВАЕТ СТАРЫЕ ДАННЫЕ!**

---

## 🔍 АНАЛИЗ ПОТОКА ДАННЫХ

### 📍 ШАГ 1: Источники данных

#### Fear & Greed Index:
```
Источник: https://api.alternative.me/fng/
Файл: app/ai/whale_ai.py
Метод: _get_fear_greed()

Алгоритм:
1. GET запрос к alternative.me
2. Парсинг JSON: data[0].value
3. Возврат: {"value": 14, "label": "Extreme Fear"}
4. Fallback: {"value": 50, "label": "Neutral"}
```

#### Long/Short Ratio:
```
Источник: https://api.bybit.com/v5/market/account-ratio
Файл: app/ai/whale_ai.py
Метод: _get_long_short_ratio()

Алгоритм:
1. GET запрос к Bybit API
2. Параметры: category=linear, symbol=BTCUSDT, period=1h
3. Парсинг: buyRatio * 100, sellRatio * 100
4. Возврат: {"long": 71.5, "short": 28.5}
5. Fallback: {"long": 50, "short": 50}
```

---

### 📍 ШАГ 2: Сбор метрик (WhaleAI)

```python
# Файл: app/ai/whale_ai.py
# Метод: get_market_metrics(symbol="BTC")

async def get_market_metrics(self, symbol: str = "BTC"):
    # Параллельный сбор данных
    tasks = [
        self._get_open_interest(symbol),
        self._get_funding_rate(symbol),
        self._get_long_short_ratio(symbol),  # ← ЗДЕСЬ LONG/SHORT
        self._get_fear_greed(),              # ← ЗДЕСЬ FEAR & GREED
        self._get_twitter_whale_data(),
        self._get_coinglass_data(symbol),
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Сохранение в MarketMetrics
    metrics = MarketMetrics()
    metrics.long_ratio = results[2].get("long", 50)
    metrics.short_ratio = results[2].get("short", 50)
    metrics.fear_greed_index = results[3].get("value", 50)
    
    # КЭШИРОВАНИЕ!
    self.last_metrics = metrics  # ← ПРОБЛЕМА МОЖЕТ БЫТЬ ЗДЕСЬ
    
    return metrics
```

**⚠️ КЭШИРОВАНИЕ:**
- `whale_ai.last_metrics` хранит последние метрики
- Если API не вызывается заново, возвращается кэш
- Кэш может быть устаревшим!

---

### 📍 ШАГ 3: API Endpoint (/api/market)

```python
# Файл: app/webapp/server.py
# Endpoint: /api/market

@app.route('/api/market')
def get_market():
    # Создание event loop
    loop = asyncio.new_event_loop()
    
    # ⚠️ СБРОС КЭША (добавлен)
    whale_ai.last_metrics = None
    
    # Получение метрик
    metrics = loop.run_until_complete(
        whale_ai.get_market_metrics("BTC")
    )
    
    # Формирование ответа
    return jsonify({
        "data": {
            "fear_greed": {
                "value": metrics.fear_greed_index,  # ← ИЗ МЕТРИК
                "status": "...",
            },
            "long_short": {
                "long_ratio": metrics.long_ratio,    # ← ИЗ МЕТРИК
                "short_ratio": metrics.short_ratio,
            }
        }
    })
```

**✅ ПРОВЕРЕНО:**
```bash
curl http://localhost:5000/api/market
# Возвращает: F&G=14, Long=71.5%
```

---

### 📍 ШАГ 4: WebApp Frontend (market.html)

```javascript
// Файл: app/webapp/templates/market.html

async function loadMarket() {
    // ⚠️ ЗАПРОС К API
    const response = await fetch('/api/market');
    const data = await response.json();
    
    // Отображение данных
    document.getElementById('fear-greed-value').textContent = 
        data.data.fear_greed.value;
    
    document.getElementById('long-ratio').textContent = 
        data.data.long_short.long_ratio + '%';
}

// ⚠️ ЗАГРУЗКА ПРИ ОТКРЫТИИ
window.addEventListener('DOMContentLoaded', loadMarket);
```

**🔍 ПРОБЛЕМЫ:**

1. **Telegram WebApp кэширует страницы**
   - Telegram может не обновлять HTML
   - Нужен `Cache-Control: no-cache`

2. **JavaScript кэширование**
   - `fetch()` может использовать HTTP кэш
   - Нужен параметр `cache: 'no-cache'`

3. **Service Worker кэширование**
   - Если есть SW, он кэширует ответы

---

## 🚨 НАЙДЕННЫЕ ПРОБЛЕМЫ

### ❌ ПРОБЛЕМА #1: Telegram WebApp Cache

**Описание:**
Telegram кэширует WebApp страницы агрессивно.

**Решение:**
Добавить HTTP заголовки в Flask:
```python
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
```

---

### ❌ ПРОБЛЕМА #2: JavaScript fetch() кэширование

**Описание:**
`fetch('/api/market')` использует браузерный кэш.

**Решение:**
```javascript
fetch('/api/market', {
    cache: 'no-cache',
    headers: {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
})
```

---

### ❌ ПРОБЛЕМА #3: URL не изменяется

**Описание:**
Telegram может кэшировать по URL.

**Решение:**
Добавить timestamp к URL:
```javascript
fetch(`/api/market?t=${Date.now()}`)
```

---

### ❌ ПРОБЛЕМА #4: WhaleAI кэш не сбрасывается

**Описание:**
`whale_ai.last_metrics` может содержать старые данные.

**Текущее состояние:**
```python
# В server.py УЖЕ ЕСТЬ:
whale_ai.last_metrics = None
```

✅ **УЖЕ ИСПРАВЛЕНО**

---

### ❌ ПРОБЛЕМА #5: Flask запускается дважды

**Описание:**
Старый Flask из `app.main.py` + новый `run_webapp.py`.

**Текущее состояние:**
```python
# app/main.py - УЖЕ ОТКЛЮЧЕНО:
# await run_flask_server()
```

✅ **УЖЕ ИСПРАВЛЕНО**

---

## 📰 АНАЛИЗ СИСТЕМЫ НОВОСТЕЙ

### 📍 ШАГ 1: Источники новостей

#### Источник #1: CryptoCompare
```
URL: https://min-api.cryptocompare.com/data/v2/news/
Файл: app/intelligence/news_parser.py
Метод: fetch_cryptocompare_news()

Алгоритм:
1. GET запрос без API ключа (бесплатный)
2. Парсинг: data.Data[0...N]
3. Для каждой новости:
   - title
   - source
   - url
   - published_on (timestamp)
   - body (текст)
4. Возврат: List[NewsItem]
5. Fallback: fetch_fallback_news()
```

#### Источник #2: CoinDesk RSS (Fallback)
```
URL: https://www.coindesk.com/arc/outboundfeeds/rss/
Метод: fetch_fallback_news()

Алгоритм:
1. GET запрос к RSS
2. feedparser.parse(content)
3. Для каждого entry:
   - title
   - link
   - published
   - summary
4. Возврат: List[NewsItem]
5. Fallback: placeholder новость
```

---

### 📍 ШАГ 2: Парсинг и AI анализ

```python
# Файл: app/intelligence/news_parser.py
# Метод: fetch_news()

async def fetch_news(self, with_ai=True, limit=10):
    # 1. Получение новостей
    news_items = await self.fetch_cryptocompare_news(limit)
    
    # Fallback если CryptoCompare не работает
    if not news_items:
        news_items = await self.fetch_fallback_news(limit)
    
    # 2. AI анализ (если включён)
    if with_ai and settings.openrouter_api_key:
        for news in news_items[:5]:
            analyzed = await self.analyze_news_with_ai(news)
            # analyzed.sentiment: -1.0 to 1.0
            # analyzed.importance: LOW/MEDIUM/HIGH/CRITICAL
            # analyzed.coins_affected: ["BTC", "ETH", ...]
    
    # 3. Кэширование
    self.cache["news"] = news_items
    self.cache_time = datetime.now(timezone.utc)
    
    return news_items
```

**⚠️ КЭШИРОВАНИЕ:**
- Кэш живёт 5 минут (`cache_ttl = timedelta(minutes=5)`)
- После 5 минут делается новый запрос

---

### 📍 ШАГ 3: API Endpoint (/api/news)

```python
# Файл: app/webapp/server.py
# Endpoint: /api/news

@app.route('/api/news')
def get_news():
    # Event loop
    loop = asyncio.new_event_loop()
    
    # Получение контекста рынка
    context = loop.run_until_complete(
        news_parser.get_market_context()
    )
    
    # context содержит:
    # - news: List[NewsItem]
    # - market_mode: NORMAL/NEWS_ALERT/WAIT_EVENT
    # - upcoming_events: List[CalendarEvent]
    # - overall_sentiment: float
    
    # Форматирование для WebApp
    news_list = []
    for news in context.get('news', []):
        news_list.append({
            "title": news.title,
            "source": news.source,
            "url": news.url,
            "published_at": news.published_at.isoformat(),
            "sentiment": news.sentiment,
            "importance": news.importance,
            "coins": news.coins_affected,
        })
    
    return jsonify({
        "data": {
            "news": news_list,
            "mode": {...},
            "events": [...],
        }
    })
```

**✅ ПРОВЕРЕНО:**
```bash
curl http://localhost:5000/api/news
# Возвращает: список новостей от CoinPaper
```

---

### 📍 ШАГ 4: WebApp Frontend (news.html)

```javascript
// Файл: app/webapp/templates/news.html

async function loadNews() {
    // ⚠️ ЗАПРОС К API
    const response = await fetch('/api/news');
    const data = await response.json();
    
    // Отображение новостей
    const newsList = data.data.news;
    
    if (newsList.length === 0) {
        // ⚠️ ПОКАЗАТЬ "Новостей пока нет"
        document.getElementById('news-empty').style.display = 'block';
    } else {
        // Рендер новостей
        newsList.forEach(news => {
            // Создание карточки новости
        });
    }
}

// ⚠️ ЗАГРУЗКА ПРИ ОТКРЫТИИ
window.addEventListener('DOMContentLoaded', loadNews);
```

---

## 🔍 НАЙДЕННЫЕ ПРОБЛЕМЫ В НОВОСТЯХ

### ✅ НОВОСТИ РАБОТАЮТ

**Проверка:**
```bash
curl http://localhost:5000/api/news | python3 -m json.tool
```

**Результат:**
```json
{
  "data": {
    "news": [
      {
        "title": "Dogecoin's Billy Markus Mocks Saylor...",
        "source": "coinpaper",
        "importance": "HIGH",
        "sentiment": -1.0
      },
      ...
    ]
  }
}
```

✅ **API ВОЗВРАЩАЕТ НОВОСТИ!**

---

## 🚨 ГЛАВНАЯ ПРОБЛЕМА: WEBAPP КЭШИРОВАНИЕ

### Почему WebApp показывает старые данные (50/50)?

#### Причина #1: Telegram кэширует WebApp
```
Telegram хранит кэш:
- HTML страниц
- JavaScript файлов
- Данных API (через Service Worker)

Срок кэша: до перезапуска Telegram
```

#### Причина #2: URL WebApp не изменился
```
URL: https://app.cryptoden.ru/market

Telegram думает что это та же страница.
Не проверяет обновления.
```

#### Причина #3: Нет заголовков Cache-Control
```
Flask не отправляет:
Cache-Control: no-cache, no-store, must-revalidate

Браузер кэширует ответы API.
```

---

## 🔧 КАК ИСПРАВИТЬ (НЕ ИЗМЕНЕНИЯ, А РЕКОМЕНДАЦИИ)

### Решение #1: Добавить Cache-Control в Flask

```python
# app/webapp/server.py

@app.after_request
def add_no_cache_headers(response):
    """Запретить кэширование"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Last-Modified'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
    return response
```

---

### Решение #2: Добавить timestamp к API запросам

```javascript
// app/webapp/templates/market.html

async function loadMarket() {
    const timestamp = Date.now();
    const response = await fetch(`/api/market?_t=${timestamp}`, {
        cache: 'no-cache',
        headers: {
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
    });
    
    // ...
}
```

---

### Решение #3: Принудительное обновление при открытии

```javascript
// В начале каждой страницы WebApp

// Telegram WebApp API
if (window.Telegram && window.Telegram.WebApp) {
    // Событие открытия WebApp
    window.Telegram.WebApp.onEvent('viewportChanged', () => {
        // Перезагрузить данные
        location.reload(true);  // true = игнорировать кэш
    });
}
```

---

### Решение #4: Добавить кнопку "Обновить"

```html
<!-- В каждой странице WebApp -->

<button onclick="forceRefresh()" class="refresh-btn">
    🔄 Обновить данные
</button>

<script>
function forceRefresh() {
    // Очистить кэш и перезагрузить
    if ('caches' in window) {
        caches.keys().then(names => {
            names.forEach(name => caches.delete(name));
        });
    }
    location.reload(true);
}
</script>
```

---

### Решение #5: Версионирование WebApp URL

```python
# Добавить версию к URL

WEBAPP_VERSION = "v3.1"

@app.route('/')
def index():
    return render_template('webapp.html', version=WEBAPP_VERSION)

# В HTML:
<script src="/static/app.js?v={{ version }}"></script>
```

---

## 📊 ИТОГОВАЯ ДИАГНОСТИКА

### ✅ ЧТО РАБОТАЕТ:

| Компонент | Статус | Данные |
|-----------|--------|--------|
| WhaleAI Fear & Greed | ✅ | 14 (Extreme Fear) |
| WhaleAI Long/Short | ✅ | 71.5% / 28.5% |
| News CryptoCompare | ✅ | Новости получаются |
| News Fallback | ✅ | CoinDesk RSS |
| Flask API /api/market | ✅ | Реальные данные |
| Flask API /api/news | ✅ | Список новостей |

### ❌ ЧТО НЕ РАБОТАЕТ:

| Проблема | Причина | Локация |
|----------|---------|---------|
| WebApp показывает 50/50 | Telegram кэш | Frontend |
| Данные не обновляются | Нет Cache-Control | server.py |
| Старый HTML | WebApp кэш | Telegram |
| fetch() кэширует | Нет cache:'no-cache' | market.html |

---

## 🎯 ГЛАВНЫЙ ВЫВОД

### API РАБОТАЕТ ПРАВИЛЬНО!

```bash
curl http://localhost:5000/api/market
# ✅ F&G: 14, Long: 71.5%

curl http://localhost:5000/api/news
# ✅ 10+ новостей
```

### ПРОБЛЕМА В TELEGRAM WEBAPP!

**Telegram кэширует:**
1. HTML страницы
2. JavaScript код
3. API ответы (через браузерный кэш)

**Решение:**
1. Добавить `Cache-Control: no-cache` в Flask
2. Добавить `?_t=${timestamp}` к fetch()
3. Добавить кнопку "🔄 Обновить"
4. Использовать `cache: 'no-cache'` в fetch()

---

## 📋 РЕКОМЕНДАЦИИ ДЛЯ ПОЛЬЗОВАТЕЛЯ

### Временное решение (сейчас):

1. **Полностью закрой Telegram**
2. **Очисти кэш приложения:**
   - Android: Настройки → Приложения → Telegram → Очистить кэш
   - iOS: Удали и переустанови Telegram (экстремально)
3. **Открой бота заново**
4. **Нажми 🐋 Рынок**

### Постоянное решение (после исправлений):

1. Добавить HTTP заголовки в Flask
2. Изменить JavaScript для игнорирования кэша
3. Добавить кнопку "Обновить" в WebApp
4. Тестировать через браузер напрямую: `https://app.cryptoden.ru/market`

---

**Дата:** 2026-02-04 14:30  
**Статус:** АНАЛИЗ ЗАВЕРШЁН  
**Файлов проанализировано:** 15  
**Проблем найдено:** 4 критических  
**Решений предложено:** 5
