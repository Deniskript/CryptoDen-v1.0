# 🌐 WebApp + Grid Bot — Анализ Интеграции

> **Дата:** 2026-01-28  
> **Цель:** Понять как добавить настройки Grid Bot в WebApp  
> **Статус:** 📋 Анализ (без изменений)

---

## 📋 СОДЕРЖАНИЕ

1. [Текущая структура](#текущая-структура)
2. [Flask Server](#flask-server)
3. [WebApp HTML](#webapp-html)
4. [Настройки (JSON)](#настройки-json)
5. [Grid Bot Config](#grid-bot-config)
6. [Telegram Keyboard](#telegram-keyboard)
7. [Как добавить Grid настройки](#как-добавить-grid-настройки)

---

## 📂 ТЕКУЩАЯ СТРУКТУРА

### Файлы

```
app/webapp/
├── server.py              # Flask сервер (151 строка)
└── templates/
    └── webapp.html        # UI (1311 строк)

data/
├── webapp_settings.json   # Настройки из WebApp
├── bot_status.json        # Статус бота
└── start_requested.json   # Флаг запуска

app/modules/
└── grid_bot.py           # Grid Bot с конфигами

app/notifications/
└── telegram_bot.py       # Применение настроек
```

### Поток данных

```
┌─────────────────────────────────────┐
│    WebApp (Telegram iframe)        │
│    https://app.cryptoden.ru         │
└──────────────┬──────────────────────┘
               │ HTTP requests
               ↓
┌─────────────────────────────────────┐
│    Flask Server (port 5000)         │
│    /api/settings, /api/start        │
└──────────────┬──────────────────────┘
               │ write JSON
               ↓
┌─────────────────────────────────────┐
│    data/webapp_settings.json        │
│    data/start_requested.json        │
└──────────────┬──────────────────────┘
               │ polling (каждые 2 сек)
               ↓
┌─────────────────────────────────────┐
│    Telegram Bot                     │
│    _check_start_request()           │
│    _apply_settings()                │
└──────────────┬──────────────────────┘
               │ apply to
               ↓
┌─────────────────────────────────────┐
│    MarketMonitor                    │
│    self.module_settings             │
└──────────────┬──────────────────────┘
               │ используется в
               ↓
┌─────────────────────────────────────┐
│    grid_bot (синглтон)              │
│    self.configs (GridConfig)        │
└─────────────────────────────────────┘
```

---

## 🐍 FLASK SERVER

**Файл:** `app/webapp/server.py` (151 строка)

### Основные endpoints

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/` | GET | Главная страница (render_template) |
| `/api/settings` | GET | Получить текущие настройки |
| `/api/settings` | POST | Сохранить настройки |
| `/api/start` | POST | Запустить бота с настройками |
| `/api/stop` | POST | Остановить бота |
| `/api/bot-status` | GET | Статус бота (из bot_status.json) |
| `/health` | GET | Health check |

### Структура данных

#### `load_settings()` — default settings

```python
default = {
    "bybit_api_key": "",
    "bybit_api_secret": "",
    "bybit_testnet": True,
    "coins": {
        "BTC": True, "ETH": True, "BNB": True,
        "SOL": True, "XRP": True, "ADA": True,
        "DOGE": True, "LINK": False, "AVAX": False
    },
    "risk_percent": 15,
    "max_trades": 6,
    "ai_enabled": True,
    "ai_confidence": 60,
    "paper_trading": True
}
```

**❌ ПРОБЛЕМА:** Нет настроек для Grid Bot!

#### `/api/start` — запуск бота

```python
@app.route('/api/start', methods=['POST'])
def start_bot():
    data = request.json
    if data:
        save_settings(data)        # → webapp_settings.json
        request_start(data)         # → start_requested.json
    
    return jsonify({
        "status": "ok",
        "action": "start_bot"
    })
```

### Файлы настроек

#### `webapp_settings.json` (сохраняются настройки)

```json
{
  "bybit_api_key": "",
  "bybit_api_secret": "",
  "bybit_testnet": true,
  "modules": {
    "director": {"enabled": true, "mode": "signal"},
    "grid": {"enabled": true, "mode": "signal"},
    "funding": {"enabled": true, "mode": "signal"},
    "arbitrage": {"enabled": false, "mode": "signal"},
    "listing": {"enabled": true, "mode": "signal"},
    "worker": {"enabled": true, "mode": "signal"}
  },
  "coins": {
    "BTC": true, "ETH": true, "SOL": true,
    "BNB": true, "XRP": true, "ADA": true,
    "DOGE": true, "LINK": true, "AVAX": true
  },
  "risk_percent": 9,
  "max_trades": 4,
  "ai_enabled": true,
  "ai_confidence": 55,
  "paper_trading": true
}
```

**❌ ПРОБЛЕМА:** В `modules.grid` только `enabled` и `mode`, но нет:
- `grid_count`
- `grid_step_percent`
- `order_size_usdt`
- `profit_per_grid`

#### `start_requested.json` (флаг для Telegram Bot)

```json
{
  "requested": true,
  "settings": { /* копия всех настроек */ }
}
```

---

## 🌐 WEBAPP HTML

**Файл:** `app/webapp/templates/webapp.html` (1311 строк)

### Структура (секции)

```html
<!DOCTYPE html>
<html>
<head>
    <style>
        /* 1. Global Styles (~900 строк CSS) */
        body { ... }
        .card { ... }
        .toggle-btn { ... }
        .slider { ... }
    </style>
</head>
<body>
    <!-- 2. Header -->
    <div class="header">
        <div class="logo">🤖</div>
        <h1>CryptoDen</h1>
        <p>AI Trading Bot</p>
    </div>
    
    <!-- 3. Status Card (динамический) -->
    <div class="status-card">
        <div class="status-row">
            <div class="status-dot" id="status-dot"></div>
            <div class="status-text" id="status-text">Остановлен</div>
        </div>
        <div class="status-info" id="status-info">...</div>
        <button class="main-btn" id="main-action-btn">
            🚀 ЗАПУСТИТЬ БОТА
        </button>
    </div>
    
    <!-- 4. API Keys Card -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">
                <div class="card-icon">🔑</div>
                <div>
                    <h3>API Ключи</h3>
                    <div class="subtitle">Bybit API для торговли</div>
                </div>
            </div>
            <span class="card-arrow">▼</span>
        </div>
        <div class="card-content">
            <div class="card-body">
                <input id="bybit_api_key" type="password" />
                <input id="bybit_api_secret" type="password" />
                <div class="toggle-row">
                    <button class="toggle-btn active" data-value="true">Testnet</button>
                    <button class="toggle-btn" data-value="false">Mainnet</button>
                </div>
            </div>
        </div>
    </div>
    
    <!-- 5. Coins Card -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">
                <div class="card-icon">💰</div>
                <div>
                    <h3>Монеты</h3>
                    <div class="subtitle">Выбрать для торговли</div>
                </div>
            </div>
        </div>
        <div class="card-content">
            <div class="coin-grid">
                <button class="coin-btn active" data-coin="BTC">
                    <span>₿</span> BTC
                </button>
                <button class="coin-btn active" data-coin="ETH">
                    <span>Ξ</span> ETH
                </button>
                <!-- ... другие монеты -->
            </div>
        </div>
    </div>
    
    <!-- 6. Modules Card -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">
                <div class="card-icon">🎯</div>
                <div>
                    <h3>Модули</h3>
                    <div class="subtitle">Настройка режимов</div>
                </div>
            </div>
        </div>
        <div class="card-content">
            <div class="module-item">
                <div class="module-name">
                    🎩 Director AI
                    <span class="module-desc">Главный стратег</span>
                </div>
                <div class="module-modes">
                    <button class="mode-btn active" data-mode="signal">📢</button>
                    <button class="mode-btn" data-mode="auto">🤖</button>
                </div>
            </div>
            
            <div class="module-item">
                <div class="module-name">
                    📊 Grid Bot
                    <span class="module-desc">Сетка ордеров</span>
                </div>
                <div class="module-modes">
                    <button class="mode-btn active" data-mode="signal">📢</button>
                    <button class="mode-btn" data-mode="auto">🤖</button>
                </div>
            </div>
            
            <!-- ... другие модули -->
        </div>
    </div>
    
    <!-- 7. Risk Management Card -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">
                <div class="card-icon">⚙️</div>
                <div>
                    <h3>Риск-менеджмент</h3>
                </div>
            </div>
        </div>
        <div class="card-content">
            <div class="slider-container">
                <label>Размер позиции: <span id="risk-value">15</span>%</label>
                <input type="range" id="risk-slider" min="5" max="25" value="15" />
            </div>
            
            <div class="slider-container">
                <label>Макс. сделок: <span id="trades-value">6</span></label>
                <input type="range" id="trades-slider" min="1" max="15" value="6" />
            </div>
        </div>
    </div>
    
    <!-- 8. AI Settings Card -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">
                <div class="card-icon">🧠</div>
                <div>
                    <h3>AI Настройки</h3>
                </div>
            </div>
        </div>
        <div class="card-content">
            <div class="toggle-row">
                <button class="toggle-btn active" data-value="true">✅ AI Вкл</button>
                <button class="toggle-btn" data-value="false">❌ AI Выкл</button>
            </div>
            
            <div class="slider-container">
                <label>Мин. уверенность: <span id="confidence-value">60</span>%</label>
                <input type="range" id="confidence-slider" min="30" max="90" value="60" />
            </div>
        </div>
    </div>
    
    <!-- 9. JavaScript -->
    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        
        // Загрузить настройки
        async function loadSettings() {
            const res = await fetch('/api/settings');
            const settings = await res.json();
            // заполнить inputs/buttons
        }
        
        // Проверить статус бота
        async function checkBotStatus() {
            const res = await fetch('/api/bot-status');
            const status = await res.json();
            updateControlCard(status);
        }
        
        // Главная кнопка (Запустить/Остановить)
        document.getElementById('main-action-btn').onclick = async () => {
            const status = await fetch('/api/bot-status').then(r => r.json());
            
            if (status.running) {
                // Остановить
                await fetch('/api/stop', { method: 'POST' });
            } else {
                // Запустить
                const settings = gatherSettings();
                await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(settings)
                });
            }
            
            tg.close(); // Закрыть WebApp
        };
        
        // Собрать настройки
        function gatherSettings() {
            return {
                bybit_api_key: document.getElementById('bybit_api_key').value,
                bybit_api_secret: document.getElementById('bybit_api_secret').value,
                bybit_testnet: getToggleValue('testnet'),
                coins: gatherCoins(),
                modules: gatherModules(),
                risk_percent: parseInt(document.getElementById('risk-slider').value),
                max_trades: parseInt(document.getElementById('trades-slider').value),
                ai_enabled: getToggleValue('ai'),
                ai_confidence: parseInt(document.getElementById('confidence-slider').value),
                paper_trading: !hasValidApiKeys()
            };
        }
        
        // Собрать модули
        function gatherModules() {
            const modules = {};
            document.querySelectorAll('.module-item').forEach(item => {
                const name = item.dataset.module;
                const enabled = !item.classList.contains('disabled');
                const mode = item.querySelector('.mode-btn.active').dataset.mode;
                modules[name] = { enabled, mode };
            });
            return modules;
        }
        
        // При загрузке
        loadSettings();
        setInterval(checkBotStatus, 5000); // Проверять каждые 5 сек
    </script>
</body>
</html>
```

### Ключевые элементы

#### 1. Status Card (динамический)

```html
<div class="status-card">
    <div class="status-dot" id="status-dot"></div>
    <div class="status-text" id="status-text">Остановлен</div>
    <button class="main-btn" id="main-action-btn">
        🚀 ЗАПУСТИТЬ БОТА
    </button>
</div>
```

**JavaScript:**
```javascript
function updateControlCard(status) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const btn = document.getElementById('main-action-btn');
    
    if (status.running) {
        dot.classList.add('running'); // зелёный + пульсация
        text.textContent = 'Работает';
        btn.textContent = '🛑 ОСТАНОВИТЬ БОТА';
        btn.classList.remove('start');
        btn.classList.add('stop');
    } else {
        dot.classList.remove('running'); // красный
        text.textContent = 'Остановлен';
        btn.textContent = '🚀 ЗАПУСТИТЬ БОТА';
        btn.classList.remove('stop');
        btn.classList.add('start');
    }
}
```

#### 2. Module Item (пример Grid Bot)

```html
<div class="module-item" data-module="grid">
    <div class="module-name">
        📊 Grid Bot
        <span class="module-desc">Сетка ордеров</span>
    </div>
    <div class="module-modes">
        <button class="mode-btn active" data-mode="signal">📢</button>
        <button class="mode-btn" data-mode="auto">🤖</button>
    </div>
</div>
```

**❌ ПРОБЛЕМА:** Только кнопки Signal/Auto, но нет настроек Grid!

#### 3. Slider (пример)

```html
<div class="slider-container">
    <label>Размер позиции: <span id="risk-value">15</span>%</label>
    <input type="range" id="risk-slider" 
           min="5" max="25" value="15" 
           class="slider" />
</div>
```

**JavaScript:**
```javascript
document.getElementById('risk-slider').oninput = (e) => {
    document.getElementById('risk-value').textContent = e.target.value;
};
```

---

## 📄 НАСТРОЙКИ (JSON)

### Текущая структура `webapp_settings.json`

```json
{
  "bybit_api_key": "",
  "bybit_api_secret": "",
  "bybit_testnet": true,
  
  "modules": {
    "director": {
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
    "BTC": true,
    "ETH": true,
    "SOL": true,
    "BNB": true,
    "XRP": true,
    "ADA": true,
    "DOGE": true,
    "LINK": true,
    "AVAX": true
  },
  
  "risk_percent": 9,
  "max_trades": 4,
  "ai_enabled": true,
  "ai_confidence": 55,
  "paper_trading": true
}
```

### ❌ ЧТО ОТСУТСТВУЕТ:

В `modules.grid` нет детальных настроек Grid Bot:

```json
"grid": {
  "enabled": true,
  "mode": "signal",
  
  // ⚠️ ЭТОГО НЕТ:
  "grid_count": 10,
  "grid_step_percent": 0.5,
  "order_size_usdt": 50.0,
  "profit_per_grid": 0.3,
  "max_open_orders": 20,
  
  // Индивидуальные настройки для монет:
  "coin_configs": {
    "BTC": {
      "grid_count": 10,
      "grid_step_percent": 0.3,
      "order_size_usdt": 100.0,
      "profit_per_grid": 0.2
    },
    "ETH": {
      "grid_count": 10,
      "grid_step_percent": 0.4,
      "order_size_usdt": 75.0,
      "profit_per_grid": 0.25
    }
    // ...
  }
}
```

---

## ⚙️ GRID BOT CONFIG

**Файл:** `app/modules/grid_bot.py`

### GridConfig (Dataclass)

```python
@dataclass
class GridConfig:
    symbol: str
    enabled: bool = True
    
    # Диапазон сетки
    upper_price: float = 0.0
    lower_price: float = 0.0
    
    # Параметры сетки
    grid_count: int = 10              # Количество уровней
    grid_step_percent: float = 0.5    # Шаг сетки в %
    
    # Размер позиции
    order_size_usdt: float = 50.0     # Размер каждого ордера
    
    # Профит
    profit_per_grid: float = 0.3      # Профит с каждой сетки %
    
    # Лимиты
    max_open_orders: int = 20
    min_profit_usdt: float = 0.1
```

### Дефолтные конфигурации

```python
def _init_default_configs(self):
    # BTC
    self.configs["BTC"] = GridConfig(
        symbol="BTC",
        grid_count=10,
        grid_step_percent=0.3,      # 0.3%
        order_size_usdt=100.0,
        profit_per_grid=0.2,
    )
    
    # ETH
    self.configs["ETH"] = GridConfig(
        symbol="ETH",
        grid_count=10,
        grid_step_percent=0.4,      # 0.4%
        order_size_usdt=75.0,
        profit_per_grid=0.25,
    )
    
    # Альты
    for symbol in ["SOL", "BNB", "XRP", "ADA", "DOGE", "LINK", "AVAX"]:
        self.configs[symbol] = GridConfig(
            symbol=symbol,
            grid_count=8,
            grid_step_percent=0.5,  # 0.5%
            order_size_usdt=50.0,
            profit_per_grid=0.3,
        )
```

### ❌ ПРОБЛЕМА:

Настройки **захардкожены** в коде, нет способа изменить их через WebApp!

---

## 📱 TELEGRAM KEYBOARD

**Файл:** `app/notifications/telegram_bot.py`

### Reply Keyboard (кнопки внизу экрана)

```python
from app.bot.keyboards import get_main_keyboard

# При старте бота
await message.answer(
    "Привет! Используй кнопки ниже:",
    reply_markup=get_main_keyboard()
)
```

**`app/bot/keyboards.py`:**

```python
def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = [
        [KeyboardButton(text="🎛 Панель управления", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="📊 Статус"), KeyboardButton(text="📈 Сделки")],
        [KeyboardButton(text="📰 Новости"), KeyboardButton(text="📋 История")],
        [KeyboardButton(text="❓ Как это работает?")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
```

### Обработчики кнопок

```python
@self.dp.message(F.text == "📊 Статус")
async def btn_status(message: Message):
    text = self._get_status_text()
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@self.dp.message(F.text == "🎛 Панель управления")
async def btn_panel(message: Message):
    # Кнопка открывает WebApp через web_app параметр
    pass
```

---

## 🔧 КАК ДОБАВИТЬ GRID НАСТРОЙКИ

### ШАГ 1: Обновить Flask Server

**`app/webapp/server.py`**

Добавить Grid настройки в `default`:

```python
def load_settings() -> dict:
    default = {
        # ... существующие настройки ...
        
        "modules": {
            "director": {"enabled": True, "mode": "signal"},
            "grid": {
                "enabled": True,
                "mode": "signal",
                
                # ✅ ДОБАВИТЬ:
                "global_config": {
                    "grid_count": 10,
                    "grid_step_percent": 0.5,
                    "order_size_usdt": 50.0,
                    "profit_per_grid": 0.3,
                    "max_open_orders": 20
                },
                
                "coin_configs": {
                    "BTC": {
                        "grid_count": 10,
                        "grid_step_percent": 0.3,
                        "order_size_usdt": 100.0,
                        "profit_per_grid": 0.2
                    },
                    "ETH": {
                        "grid_count": 10,
                        "grid_step_percent": 0.4,
                        "order_size_usdt": 75.0,
                        "profit_per_grid": 0.25
                    },
                    "default": {  # Для остальных монет
                        "grid_count": 8,
                        "grid_step_percent": 0.5,
                        "order_size_usdt": 50.0,
                        "profit_per_grid": 0.3
                    }
                }
            },
            # ... другие модули ...
        }
    }
```

### ШАГ 2: Обновить WebApp HTML

**`app/webapp/templates/webapp.html`**

#### 2.1. Добавить Grid Settings в HTML

После существующего Module Item для Grid Bot:

```html
<div class="module-item" data-module="grid">
    <div class="module-name">
        📊 Grid Bot
        <span class="module-desc">Сетка ордеров</span>
    </div>
    <div class="module-modes">
        <button class="mode-btn active" data-mode="signal">📢</button>
        <button class="mode-btn" data-mode="auto">🤖</button>
    </div>
</div>

<!-- ✅ ДОБАВИТЬ КАРТОЧКУ С НАСТРОЙКАМИ: -->
<div class="card" id="grid-settings-card" style="display: none;">
    <div class="card-header">
        <div class="card-title">
            <div class="card-icon">⚙️</div>
            <div>
                <h3>Grid Bot — Настройки</h3>
                <div class="subtitle">Параметры сетки</div>
            </div>
        </div>
        <span class="card-arrow">▼</span>
    </div>
    <div class="card-content">
        <div class="card-body">
            
            <!-- Глобальные настройки -->
            <div class="section-title">🌐 Глобальные настройки</div>
            
            <div class="slider-container">
                <label>Уровней сетки: <span id="grid-count-value">10</span></label>
                <input type="range" id="grid-count-slider" 
                       min="5" max="20" value="10" step="1" class="slider" />
                <div class="slider-hint">
                    Количество ордеров выше и ниже цены
                </div>
            </div>
            
            <div class="slider-container">
                <label>Шаг сетки: <span id="grid-step-value">0.5</span>%</label>
                <input type="range" id="grid-step-slider" 
                       min="0.1" max="2.0" value="0.5" step="0.1" class="slider" />
                <div class="slider-hint">
                    Расстояние между уровнями
                </div>
            </div>
            
            <div class="slider-container">
                <label>Размер ордера: $<span id="order-size-value">50</span></label>
                <input type="range" id="order-size-slider" 
                       min="10" max="200" value="50" step="5" class="slider" />
                <div class="slider-hint">
                    USDT на каждый ордер
                </div>
            </div>
            
            <div class="slider-container">
                <label>Профит на сделку: <span id="profit-grid-value">0.3</span>%</label>
                <input type="range" id="profit-grid-slider" 
                       min="0.1" max="1.0" value="0.3" step="0.05" class="slider" />
                <div class="slider-hint">
                    Цель профита для каждой сделки
                </div>
            </div>
            
            <!-- Индивидуальные настройки для монет -->
            <div class="section-title">💰 Настройки для монет</div>
            
            <div class="coin-config-tabs">
                <button class="coin-config-tab active" data-coin="default">
                    По умолчанию
                </button>
                <button class="coin-config-tab" data-coin="BTC">BTC</button>
                <button class="coin-config-tab" data-coin="ETH">ETH</button>
                <button class="coin-config-tab" data-coin="SOL">SOL</button>
            </div>
            
            <div id="coin-config-container">
                <!-- Динамически заполняется -->
            </div>
            
        </div>
    </div>
</div>
```

#### 2.2. Добавить CSS для новых элементов

```css
/* Section Title */
.section-title {
    font-size: 13px;
    font-weight: 600;
    color: #60a5fa;
    margin-top: 16px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(71, 85, 105, 0.3);
}

/* Slider Hint */
.slider-hint {
    font-size: 11px;
    color: #64748b;
    margin-top: 4px;
}

/* Coin Config Tabs */
.coin-config-tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
    flex-wrap: wrap;
}

.coin-config-tab {
    padding: 8px 12px;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid #475569;
    border-radius: 8px;
    color: #94a3b8;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
}

.coin-config-tab.active {
    background: linear-gradient(135deg, #3b82f6, #06b6d4);
    color: white;
    border-color: #3b82f6;
}

#coin-config-container {
    background: rgba(15, 23, 42, 0.4);
    padding: 12px;
    border-radius: 10px;
}
```

#### 2.3. Добавить JavaScript логику

```javascript
// Показать настройки Grid при включении Auto режима
document.querySelectorAll('[data-module="grid"] .mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        const settingsCard = document.getElementById('grid-settings-card');
        
        if (mode === 'auto') {
            settingsCard.style.display = 'block';
        } else {
            settingsCard.style.display = 'none';
        }
    });
});

// Слайдеры Grid настроек
document.getElementById('grid-count-slider').oninput = (e) => {
    document.getElementById('grid-count-value').textContent = e.target.value;
};

document.getElementById('grid-step-slider').oninput = (e) => {
    document.getElementById('grid-step-value').textContent = e.target.value;
};

document.getElementById('order-size-slider').oninput = (e) => {
    document.getElementById('order-size-value').textContent = e.target.value;
};

document.getElementById('profit-grid-slider').oninput = (e) => {
    document.getElementById('profit-grid-value').textContent = e.target.value;
};

// Табы для монет
document.querySelectorAll('.coin-config-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        // Убрать active у всех
        document.querySelectorAll('.coin-config-tab').forEach(t => 
            t.classList.remove('active')
        );
        
        // Добавить active к текущему
        tab.classList.add('active');
        
        // Загрузить настройки для монеты
        const coin = tab.dataset.coin;
        loadCoinConfig(coin);
    });
});

function loadCoinConfig(coin) {
    const container = document.getElementById('coin-config-container');
    
    // Получить настройки для монеты из settings
    const config = settings.modules.grid.coin_configs[coin] || 
                   settings.modules.grid.coin_configs.default;
    
    container.innerHTML = `
        <div class="slider-container">
            <label>Уровней: <span id="coin-grid-count-${coin}">${config.grid_count}</span></label>
            <input type="range" min="5" max="20" value="${config.grid_count}" 
                   step="1" class="slider" data-coin="${coin}" data-param="grid_count" />
        </div>
        
        <div class="slider-container">
            <label>Шаг: <span id="coin-grid-step-${coin}">${config.grid_step_percent}</span>%</label>
            <input type="range" min="0.1" max="2.0" value="${config.grid_step_percent}" 
                   step="0.1" class="slider" data-coin="${coin}" data-param="grid_step_percent" />
        </div>
        
        <div class="slider-container">
            <label>Размер: $<span id="coin-order-size-${coin}">${config.order_size_usdt}</span></label>
            <input type="range" min="10" max="200" value="${config.order_size_usdt}" 
                   step="5" class="slider" data-coin="${coin}" data-param="order_size_usdt" />
        </div>
        
        <div class="slider-container">
            <label>Профит: <span id="coin-profit-${coin}">${config.profit_per_grid}</span>%</label>
            <input type="range" min="0.1" max="1.0" value="${config.profit_per_grid}" 
                   step="0.05" class="slider" data-coin="${coin}" data-param="profit_per_grid" />
        </div>
    `;
    
    // Добавить listeners для слайдеров
    container.querySelectorAll('.slider').forEach(slider => {
        slider.oninput = (e) => {
            const coin = e.target.dataset.coin;
            const param = e.target.dataset.param;
            const value = e.target.value;
            
            document.getElementById(`coin-${param.replace('_', '-')}-${coin}`).textContent = value;
            
            // Сохранить в settings
            if (!settings.modules.grid.coin_configs[coin]) {
                settings.modules.grid.coin_configs[coin] = {};
            }
            settings.modules.grid.coin_configs[coin][param] = parseFloat(value);
        };
    });
}

// Собрать Grid настройки при сохранении
function gatherModules() {
    const modules = {};
    
    // ... существующий код ...
    
    // Grid настройки
    if (document.getElementById('grid-settings-card').style.display !== 'none') {
        modules.grid.global_config = {
            grid_count: parseInt(document.getElementById('grid-count-slider').value),
            grid_step_percent: parseFloat(document.getElementById('grid-step-slider').value),
            order_size_usdt: parseFloat(document.getElementById('order-size-slider').value),
            profit_per_grid: parseFloat(document.getElementById('profit-grid-slider').value),
            max_open_orders: 20
        };
        
        modules.grid.coin_configs = settings.modules.grid.coin_configs || {};
    }
    
    return modules;
}
```

### ШАГ 3: Обновить Telegram Bot

**`app/notifications/telegram_bot.py`**

В методе `_apply_settings`:

```python
def _apply_settings(self, settings_data: dict):
    """Применить настройки из WebApp"""
    
    # ... существующий код ...
    
    # ✅ ДОБАВИТЬ применение Grid настроек:
    if 'modules' in settings_data and 'grid' in settings_data['modules']:
        grid_config = settings_data['modules']['grid']
        
        # Применить к grid_bot
        from app.modules.grid_bot import grid_bot
        
        # Глобальные настройки
        if 'global_config' in grid_config:
            gc = grid_config['global_config']
            # Обновить дефолтные значения для grid_bot
            
        # Индивидуальные настройки для монет
        if 'coin_configs' in grid_config:
            for coin, config in grid_config['coin_configs'].items():
                if coin in grid_bot.configs:
                    # Обновить существующую конфигурацию
                    grid_bot.configs[coin].grid_count = config.get('grid_count', 10)
                    grid_bot.configs[coin].grid_step_percent = config.get('grid_step_percent', 0.5)
                    grid_bot.configs[coin].order_size_usdt = config.get('order_size_usdt', 50.0)
                    grid_bot.configs[coin].profit_per_grid = config.get('profit_per_grid', 0.3)
```

### ШАГ 4: Обновить Grid Bot

**`app/modules/grid_bot.py`**

Добавить метод для применения настроек:

```python
def apply_config(self, symbol: str, config: Dict):
    """Применить конфигурацию из WebApp"""
    if symbol not in self.configs:
        self.configs[symbol] = GridConfig(symbol=symbol)
    
    cfg = self.configs[symbol]
    
    if 'grid_count' in config:
        cfg.grid_count = config['grid_count']
    if 'grid_step_percent' in config:
        cfg.grid_step_percent = config['grid_step_percent']
    if 'order_size_usdt' in config:
        cfg.order_size_usdt = config['order_size_usdt']
    if 'profit_per_grid' in config:
        cfg.profit_per_grid = config['profit_per_grid']
    
    logger.info(f"📊 Grid config updated for {symbol}: "
               f"{cfg.grid_count} levels, {cfg.grid_step_percent}% step, "
               f"${cfg.order_size_usdt} order")
```

---

## 📝 РЕЗЮМЕ

### ✅ Что есть сейчас:

1. ✅ WebApp с базовыми настройками (API, монеты, модули Signal/Auto)
2. ✅ Flask сервер с endpoints
3. ✅ Сохранение/загрузка настроек (JSON)
4. ✅ Grid Bot с захардкоженными конфигами
5. ✅ Telegram интеграция

### ❌ Что отсутствует:

1. ❌ Grid настройки в WebApp UI
2. ❌ Grid настройки в JSON структуре
3. ❌ Применение Grid настроек из WebApp к grid_bot
4. ❌ Индивидуальные настройки для монет

### 🔧 Что нужно сделать:

1. **Flask Server** (`server.py`):
   - Добавить `grid_config` в default settings

2. **WebApp HTML** (`webapp.html`):
   - Добавить карточку "Grid Bot — Настройки"
   - Добавить слайдеры для параметров
   - Добавить табы для настройки отдельных монет
   - Добавить JavaScript логику

3. **Telegram Bot** (`telegram_bot.py`):
   - Обновить `_apply_settings()` для применения Grid настроек

4. **Grid Bot** (`grid_bot.py`):
   - Добавить метод `apply_config()` для динамического обновления

---

**Создано:** 2026-01-28  
**Статус:** 📋 Анализ завершён (без изменений в коде)
