"""
WebApp Server — Flask сервер для Telegram WebApp
"""
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os
import json
import asyncio
import threading

app = Flask(__name__, 
    template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
    static_folder=os.path.join(os.path.dirname(__file__), 'static')
)
CORS(app)

# Путь к файлу настроек
SETTINGS_FILE = "/root/crypto-bot/data/webapp_settings.json"

# Флаг для запуска бота
START_REQUESTED_FILE = "/root/crypto-bot/data/start_requested.json"


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


def request_start(settings: dict):
    """Создать запрос на запуск бота"""
    os.makedirs(os.path.dirname(START_REQUESTED_FILE), exist_ok=True)
    with open(START_REQUESTED_FILE, 'w') as f:
        json.dump({
            "requested": True,
            "settings": settings
        }, f, indent=2)


@app.route('/')
def index():
    """Главная страница WebApp"""
    settings = load_settings()
    return render_template('webapp.html', settings=settings)


@app.route('/market')
def market():
    """Страница Рынок"""
    return render_template('market.html')


@app.route('/news')
def news():
    """Страница Новости"""
    return render_template('news.html')


@app.route('/stats')
def stats_page():
    """Страница статистики"""
    return render_template('stats.html')


@app.route('/analyze')
def analyze_page():
    """Страница анализа"""
    return render_template('analyze.html')


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
        request_start(data)
    
    return jsonify({
        "status": "ok",
        "action": "start_bot",
        "message": "Settings saved. Bot will start."
    })


BOT_STATUS_FILE = "/root/crypto-bot/data/bot_status.json"

@app.route('/api/bot-status')
def get_bot_status():
    """Получить статус бота из файла (бот обновляет его)"""
    default = {
        "running": False,
        "balance": 1000,
        "active_trades": 0,
        "paper_trading": True,
        "ai_enabled": True
    }
    
    try:
        if os.path.exists(BOT_STATUS_FILE):
            with open(BOT_STATUS_FILE, 'r') as f:
                status = json.load(f)
                return jsonify(status)
    except Exception as e:
        print(f"Status read error: {e}")
    
    return jsonify(default)


@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Остановить бота"""
    STOP_REQUESTED_FILE = "/root/crypto-bot/data/stop_requested.json"
    os.makedirs(os.path.dirname(STOP_REQUESTED_FILE), exist_ok=True)
    with open(STOP_REQUESTED_FILE, 'w') as f:
        json.dump({"requested": True}, f)
    
    return jsonify({
        "status": "ok",
        "action": "stop_bot"
    })


@app.route('/api/market')
def get_market():
    """Получить данные рынка"""
    try:
        import asyncio
        from app.ai.whale_ai import whale_ai
        from app.trading.bybit.client import BybitClient
        
        # Создаём новый event loop для синхронного контекста
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Получаем метрики
            metrics = loop.run_until_complete(whale_ai.get_market_metrics("BTC"))
            
            # Получаем цену BTC
            btc_price = 0
            btc_change_24h = 0
            try:
                client = BybitClient(testnet=False)
                btc_price = loop.run_until_complete(client.get_price("BTC")) or 0
            except:
                pass
            
            if not metrics:
                return jsonify({"success": False, "error": "Failed to get metrics"})
            
            # Статусы
            fg_status = ""
            fg_advice = ""
            if metrics.fear_greed_index < 25:
                fg_status = "Экстремальный страх"
                fg_advice = "Хорошо для покупок"
            elif metrics.fear_greed_index < 45:
                fg_status = "Страх"
                fg_advice = "Можно покупать осторожно"
            elif metrics.fear_greed_index < 55:
                fg_status = "Нейтрально"
                fg_advice = "Ждите сигнал"
            elif metrics.fear_greed_index < 75:
                fg_status = "Жадность"
                fg_advice = "Осторожно с покупками"
            else:
                fg_status = "Экстремальная жадность"
                fg_advice = "Опасно покупать"
            
            ls_status = ""
            if metrics.long_ratio > 65:
                ls_status = "Много лонгов ⚠️ Риск ликвидаций"
            elif metrics.long_ratio < 35:
                ls_status = "Много шортов ⚠️ Возможен шорт-сквиз"
            else:
                ls_status = "Баланс"
            
            funding_status = ""
            if metrics.funding_rate > 0.05:
                funding_status = "Лонги переплачивают ⚠️"
            elif metrics.funding_rate < -0.05:
                funding_status = "Шорты переплачивают ⚠️"
            else:
                funding_status = "Нейтрально"
            
            oi_status = ""
            if metrics.oi_change_24h < -5:
                oi_status = "Сильное падение — закрытие позиций"
            elif metrics.oi_change_24h < -2:
                oi_status = "Падает — осторожность"
            elif metrics.oi_change_24h > 5:
                oi_status = "Сильный рост — новые позиции"
            elif metrics.oi_change_24h > 2:
                oi_status = "Растёт — интерес к рынку"
            else:
                oi_status = "Стабильно"
            
            liq_status = ""
            total_liq = metrics.liq_long + metrics.liq_short
            if total_liq > 100_000_000:
                liq_status = "Массовые ликвидации! ⚠️"
            elif total_liq > 50_000_000:
                liq_status = "Повышенные ликвидации"
            elif metrics.liq_long > metrics.liq_short * 2:
                liq_status = "Лонги страдают"
            elif metrics.liq_short > metrics.liq_long * 2:
                liq_status = "Шорты страдают"
            else:
                liq_status = "Умеренные"
            
            # AI выводы
            ai_conclusions = []
            if metrics.fear_greed_index < 30:
                ai_conclusions.append("Рынок в страхе — исторически хорошо для покупок")
            if metrics.fear_greed_index > 70:
                ai_conclusions.append("Рынок перегрет — осторожно с покупками")
            if metrics.long_ratio > 65:
                ai_conclusions.append("Много лонгов — риск каскадных ликвидаций")
            if metrics.long_ratio < 35:
                ai_conclusions.append("Мало лонгов — возможен рост")
            if metrics.oi_change_24h < -5:
                ai_conclusions.append("OI падает — трейдеры закрывают позиции")
            if metrics.funding_rate > 0.05:
                ai_conclusions.append("Funding высокий — лонги переплачивают")
            if total_liq > 50_000_000:
                ai_conclusions.append("Крупные ликвидации — возможен разворот")
            
            # Рекомендация
            if metrics.fear_greed_index < 30 and metrics.long_ratio < 50:
                ai_conclusions.append("✅ Хорошие условия для покупки")
            elif metrics.fear_greed_index > 70 and metrics.long_ratio > 60:
                ai_conclusions.append("⚠️ Опасно покупать, ждите коррекцию")
            else:
                ai_conclusions.append("⏳ Ждите чёткий сигнал от бота")
            
            if not ai_conclusions:
                ai_conclusions.append("Рынок спокойный, ждите сигнал")
            
            return jsonify({
                "success": True,
                "data": {
                    "btc": {
                        "price": btc_price,
                        "change_24h": btc_change_24h
                    },
                    "fear_greed": {
                        "value": metrics.fear_greed_index,
                        "status": fg_status,
                        "advice": fg_advice
                    },
                    "long_short": {
                        "long_ratio": metrics.long_ratio,
                        "short_ratio": metrics.short_ratio,
                        "status": ls_status
                    },
                    "funding": {
                        "rate": metrics.funding_rate,
                        "status": funding_status
                    },
                    "open_interest": {
                        "change_1h": metrics.oi_change_1h,
                        "change_24h": metrics.oi_change_24h,
                        "status": oi_status
                    },
                    "liquidations": {
                        "long": metrics.liq_long,
                        "short": metrics.liq_short,
                        "total": total_liq,
                        "status": liq_status
                    },
                    "ai_conclusions": ai_conclusions,
                    "updated_at": metrics.timestamp.isoformat() if metrics.timestamp else None
                }
            })
        finally:
            loop.close()
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/news')
def get_news():
    """Получить новости для WebApp"""
    try:
        import asyncio
        from app.intelligence.news_parser import news_parser
        from datetime import datetime, timezone
        
        # Создаём event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Получаем контекст
            context = loop.run_until_complete(news_parser.get_market_context())
            
            news_list = context.get('news', [])
            market_mode = context.get('market_mode', 'NORMAL')
            upcoming_events = context.get('upcoming_events', [])
            overall_sentiment = context.get('overall_sentiment', 0)
            
            # Режим рынка
            mode_info = {
                'NORMAL': {'emoji': '🟢', 'name': 'Нормальный', 'desc': 'Можно торговать'},
                'NEWS_ALERT': {'emoji': '🟡', 'name': 'Осторожность', 'desc': 'Важные новости'},
                'WAIT_EVENT': {'emoji': '🔴', 'name': 'Ожидание', 'desc': 'Важное событие скоро'},
            }
            
            mode = mode_info.get(market_mode, mode_info['NORMAL'])
            
            # Форматируем новости
            formatted_news = []
            for news in news_list[:10]:
                # Пропустить если это строка или None
                if news is None:
                    continue
                if isinstance(news, str):
                    # Попробуем распарсить как dict
                    try:
                        import ast
                        news = ast.literal_eval(news)
                    except:
                        continue
                
                # Если это dict — извлекаем данные
                if isinstance(news, dict):
                    title = news.get('title', '')
                    published = news.get('published_at') or news.get('published')
                    sentiment = float(news.get('sentiment', 0))
                    importance = news.get('importance', 'LOW')
                    coins = news.get('coins_affected', news.get('coins', []))
                    summary = news.get('summary', '')
                    source = news.get('source', 'Unknown')
                    url = news.get('url', '')
                else:
                    # Объект с атрибутами
                    title = getattr(news, 'title', str(news)[:100])
                    published = getattr(news, 'published_at', None)
                    sentiment = float(getattr(news, 'sentiment', 0))
                    importance = getattr(news, 'importance', 'LOW')
                    coins = getattr(news, 'coins_affected', [])
                    summary = getattr(news, 'summary', '')
                    source = getattr(news, 'source', 'Unknown')
                    url = getattr(news, 'url', '')
                
                if not title:
                    continue
                
                # Время
                time_ago = ""
                if published:
                    try:
                        # Убедимся что published это datetime
                        pub = published
                        if isinstance(pub, str):
                            from dateutil import parser as dt_parser
                            pub = dt_parser.parse(pub)
                        
                        delta = datetime.now(timezone.utc) - pub.replace(tzinfo=timezone.utc)
                        if delta.days > 0:
                            time_ago = f"{delta.days}д назад"
                        elif delta.seconds >= 3600:
                            time_ago = f"{delta.seconds // 3600}ч назад"
                        else:
                            time_ago = f"{max(1, delta.seconds // 60)}мин назад"
                    except:
                        time_ago = "недавно"
                
                # Sentiment emoji
                if sentiment > 0.3:
                    sentiment_emoji = "🟢"
                    sentiment_text = "Позитивная"
                elif sentiment < -0.3:
                    sentiment_emoji = "🔴"
                    sentiment_text = "Негативная"
                else:
                    sentiment_emoji = "⚪"
                    sentiment_text = "Нейтральная"
                
                # Importance emoji
                importance_emoji = {
                    'LOW': '⬜',
                    'MEDIUM': '🟨',
                    'HIGH': '🟧',
                    'CRITICAL': '🟥'
                }.get(importance, '⬜')
                
                # Impact на рынок
                impact = ""
                if sentiment > 0.5:
                    impact = "Ожидается рост цены"
                elif sentiment > 0.2:
                    impact = "Умеренно позитивно"
                elif sentiment < -0.5:
                    impact = "Возможно падение"
                elif sentiment < -0.2:
                    impact = "Умеренно негативно"
                else:
                    impact = "Незначительное влияние"
                
                formatted_news.append({
                    'title': title,
                    'source': source,
                    'url': url,
                    'time_ago': time_ago,
                    'published_at': published if isinstance(published, str) else (published.isoformat() if published else None),
                    'sentiment': sentiment,
                    'sentiment_emoji': sentiment_emoji,
                    'sentiment_text': sentiment_text,
                    'importance': importance,
                    'importance_emoji': importance_emoji,
                    'coins': (coins[:3] if isinstance(coins, list) else []) if coins else [],
                    'summary': summary,
                    'impact': impact,
                })
            
            # Форматируем события
            formatted_events = []
            if isinstance(upcoming_events, list):
                for event in upcoming_events[:5]:
                    if isinstance(event, dict):
                        formatted_events.append({
                            'name': event.get('event', ''),
                            'date': event.get('date', event.get('time', 'Скоро')),
                            'importance': event.get('importance', 'MEDIUM'),
                        })
                    else:
                        formatted_events.append({
                            'name': getattr(event, 'event', str(event)),
                            'date': getattr(event, 'time', 'Скоро'),
                            'importance': getattr(event, 'importance', 'MEDIUM'),
                        })
            
            return jsonify({
                "success": True,
                "data": {
                    "mode": {
                        "code": market_mode,
                        "emoji": mode['emoji'],
                        "name": mode['name'],
                        "desc": mode['desc'],
                    },
                    "overall_sentiment": overall_sentiment,
                    "news": formatted_news,
                    "events": formatted_events,
                    "updated_at": datetime.now().isoformat(),
                }
            })
        finally:
            loop.close()
            
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        })


@app.route('/api/news/settings', methods=['GET'])
def get_news_settings():
    """Получить настройки уведомлений новостей"""
    settings_file = "/root/crypto-bot/data/news_notifications.json"
    
    default_settings = {
        "enabled": False,
        "critical_only": True,
        "high_importance": True,
        "medium_importance": False,
        "before_events": True,
        "events_hours": 1,
        "daily_digest": False,
        "digest_time": "09:00",
    }
    
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r') as f:
                return jsonify({"success": True, "settings": json.load(f)})
        except:
            pass
    
    return jsonify({"success": True, "settings": default_settings})


@app.route('/api/news/settings', methods=['POST'])
def save_news_settings():
    """Сохранить настройки уведомлений новостей"""
    settings_file = "/root/crypto-bot/data/news_notifications.json"
    
    try:
        data = request.json
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        with open(settings_file, 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/stats')
def get_stats():
    """Статистика сеансов и сделок с разбивкой по источникам"""
    try:
        from app.core.session_tracker import session_tracker
        from app.core.trade_tracker import trade_tracker
        
        return jsonify({
            "success": True,
            "data": {
                "current_session": session_tracker.get_current_session(),
                "sessions": session_tracker.get_all_sessions(limit=10),
                "total": session_tracker.get_total_stats(),
                "active_trades": len(trade_tracker.get_active_trades()),
                "trade_stats": trade_tracker.get_stats().get("summary", {}),
                "source_stats": trade_tracker.get_stats_by_source()
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/analyze/<symbol>')
def api_analyze(symbol: str):
    """API для анализа монеты Adaptive Brain"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            from app.brain.adaptive_brain import adaptive_brain
            
            decision = loop.run_until_complete(adaptive_brain.analyze(symbol.upper()))
            
            return jsonify({
                "success": True,
                "data": {
                    "symbol": decision.symbol,
                    "action": decision.action.value,
                    "confidence": decision.confidence,
                    "entry_price": decision.entry_price,
                    "stop_loss": decision.stop_loss,
                    "take_profit": decision.take_profit,
                    "regime": decision.regime.value,
                    "reasoning": decision.reasoning,
                    "key_factors": decision.key_factors,
                    "restrictions": decision.restrictions,
                    "source": decision.source
                }
            })
        finally:
            loop.close()
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route('/api/brain/status')
def api_brain_status():
    """Статус Adaptive Brain"""
    try:
        from app.brain.adaptive_brain import adaptive_brain
        return jsonify({
            "success": True,
            "data": adaptive_brain.get_status()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/momentum/status')
def api_momentum_status():
    """Статус Momentum Detector"""
    try:
        from app.brain.momentum_detector import momentum_detector
        return jsonify({
            "success": True,
            "data": momentum_detector.get_status(),
            "alerts": momentum_detector.get_recent_alerts(10)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/health')
def health():
    """Health check"""
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
