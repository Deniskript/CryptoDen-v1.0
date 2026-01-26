"""
WebApp Server — Flask сервер для Telegram WebApp
"""
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
import json

app = Flask(__name__, 
    template_folder='templates',
    static_folder='static'
)
CORS(app)

# Путь к файлу настроек
SETTINGS_FILE = "/root/crypto-bot/data/webapp_settings.json"


def load_settings() -> dict:
    """Загрузить настройки"""
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
    
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                default.update(saved)
    except Exception as e:
        print(f"Error loading settings: {e}")
    
    return default


def save_settings(settings: dict):
    """Сохранить настройки"""
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)


@app.route('/')
def index():
    """Главная страница WebApp"""
    settings = load_settings()
    return render_template('webapp.html', settings=settings)


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Получить настройки"""
    return jsonify(load_settings())


@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Сохранить настройки"""
    data = request.json
    save_settings(data)
    return jsonify({"status": "ok"})


@app.route('/api/start', methods=['POST'])
def start_bot():
    """Запустить бота"""
    data = request.json
    if data:
        save_settings(data)
    
    return jsonify({
        "status": "ok",
        "action": "start_bot"
    })


@app.route('/health')
def health():
    """Health check"""
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
