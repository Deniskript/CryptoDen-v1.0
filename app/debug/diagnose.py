"""
Диагностика работы бота
Запуск: python -m app.debug.diagnose
"""
import asyncio
import sys
import os

sys.path.insert(0, '/root/crypto-bot')
os.chdir('/root/crypto-bot')


async def diagnose_all():
    """Полная диагностика всех компонентов"""
    
    print("\n" + "="*60)
    print("🔍 ДИАГНОСТИКА CRYPTODEN BOT")
    print("="*60 + "\n")
    
    results = {
        'config': False,
        'strategies': False,
        'bybit': False,
        'data_cache': False,
        'news': False,
        'ai': False,
        'monitor': False
    }
    
    # 1. Проверка конфигурации
    print("⚙️  1. КОНФИГУРАЦИЯ")
    print("-"*40)
    try:
        from app.core.config import settings
        
        print(f"   ✅ Settings loaded")
        print(f"   • Telegram: {'✅' if settings.telegram_bot_token else '❌'}")
        print(f"   • Bybit API: {'✅' if settings.bybit_api_key else '❌'}")
        print(f"   • OpenRouter: {'✅' if settings.openrouter_api_key else '❌'}")
        print(f"   • CryptoCompare: {'✅' if settings.cryptocompare_api_key else '❌'}")
        
        results['config'] = True
        
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    print()
    
    # 2. Проверка стратегий
    print("📊 2. СТРАТЕГИИ")
    print("-"*40)
    try:
        from app.strategies import get_enabled_strategies, strategy_checker
        
        strategies = get_enabled_strategies()
        print(f"   ✅ Загружено стратегий: {len(strategies)}")
        
        for symbol, strat in strategies.items():
            status = '✅' if strat.enabled else '❌'
            print(f"   {status} {symbol}: {strat.name}")
            print(f"      Условия: {len(strat.conditions)}")
            for c in strat.conditions:
                print(f"      • {c.get('indicator')} {c.get('operator')} {c.get('value')}")
        
        print(f"\n   📈 Checker status: {strategy_checker.get_status()}")
        results['strategies'] = True
        
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 3. Проверка Bybit API
    print("📈 3. BYBIT API")
    print("-"*40)
    try:
        from app.trading.bybit.client import BybitClient
        
        async with BybitClient(testnet=False) as client:
            # Проверяем цену BTC
            price = await client.get_price('BTC')
            if price:
                print(f"   ✅ BTC цена: ${price:,.2f}")
                results['bybit'] = True
            else:
                print("   ❌ Не удалось получить цену")
            
            # Получаем все цены
            symbols = ['BTC', 'ETH', 'SOL', 'XRP']
            prices = await client.get_prices(symbols)
            print(f"   ✅ Цены получены: {len(prices)}")
            for s, p in prices.items():
                print(f"   • {s}: ${p:,.2f}")
                
    except Exception as e:
        print(f"   ❌ Ошибка Bybit: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 4. Проверка кэша данных
    print("💾 4. КЭШ ДАННЫХ")
    print("-"*40)
    try:
        from app.backtesting.data_loader import BybitDataLoader
        import os
        
        loader = BybitDataLoader()
        
        cache_dir = '/root/crypto-bot/data/cache'
        if os.path.exists(cache_dir):
            files = os.listdir(cache_dir)
            print(f"   ✅ Файлов в кэше: {len(files)}")
            
            for f in files[:5]:
                size = os.path.getsize(os.path.join(cache_dir, f)) / 1024
                print(f"   • {f}: {size:.1f} KB")
        else:
            print(f"   ⚠️ Директория кэша не существует")
        
        # Пробуем загрузить данные
        print("\n   📊 Проверяю загрузку данных для BTC...")
        df = loader.load_from_cache('BTC', '5m')
        
        if df is not None and len(df) > 0:
            print(f"   ✅ Загружено {len(df)} свечей")
            print(f"   • Последняя цена: ${df['close'].iloc[-1]:,.2f}")
            print(f"   • Диапазон дат: {df['timestamp'].iloc[0]} - {df['timestamp'].iloc[-1]}")
            results['data_cache'] = True
        else:
            print("   ⚠️ Нет данных в кэше!")
            print("   💡 Нужно скачать: python scripts/run_backtest.py --download")
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 5. Проверка индикаторов и сигналов
    print("🎯 5. ПРОВЕРКА ИНДИКАТОРОВ")
    print("-"*40)
    try:
        from app.strategies.indicators import TechnicalIndicators
        from app.backtesting.data_loader import BybitDataLoader
        
        loader = BybitDataLoader()
        df = loader.load_from_cache('BTC', '5m')
        
        if df is not None and len(df) >= 50:
            df = df.tail(100).copy()
            ind = TechnicalIndicators()
            
            rsi = ind.rsi(df['close'], 14)
            ema_21 = ind.ema(df['close'], 21)
            ema_50 = ind.ema(df['close'], 50)
            stoch = ind.stochastic_k(df, 14)
            macd_dir = ind.macd_cross_direction(df['close'])
            
            current_price = df['close'].iloc[-1]
            
            print(f"   📈 BTC Индикаторы:")
            print(f"   • Цена: ${current_price:,.2f}")
            print(f"   • RSI(14): {rsi:.1f}")
            print(f"   • EMA(21): ${ema_21:,.2f}")
            print(f"   • EMA(50): ${ema_50:,.2f}")
            print(f"   • Stoch(14): {stoch:.1f}")
            print(f"   • MACD Cross: {macd_dir}")
            print(f"   • Price vs EMA(21): {current_price - ema_21:+.2f}")
            
            # Анализ сигнала
            print("\n   🔍 Анализ условий BTC стратегии:")
            print(f"      RSI < 30: {'✅' if rsi < 30 else '❌'} (RSI={rsi:.1f})")
            print(f"      Price > EMA21: {'✅' if current_price > ema_21 else '❌'}")
            
            if rsi < 30 and current_price > ema_21:
                print("   🎯 СИГНАЛ ЕСТЬ! Условия выполнены!")
            else:
                print("   😴 Сигнала нет - условия не выполнены")
                print("   💡 Это НОРМАЛЬНО! Бот ждёт подходящий момент.")
        else:
            print("   ⚠️ Недостаточно данных для анализа")
            
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 6. Проверка парсера новостей
    print("📰 6. ПАРСЕР НОВОСТЕЙ")
    print("-"*40)
    try:
        from app.intelligence.news_parser import news_parser
        
        print("   📡 Загружаю новости...")
        context = await news_parser.get_market_context()
        
        news = context.get('news', [])
        mode = context.get('market_mode', 'UNKNOWN')
        
        print(f"   ✅ Режим рынка: {mode}")
        print(f"   ✅ Новостей: {len(news)}")
        
        if news:
            print("\n   📋 Последние новости:")
            for n in news[:3]:
                title = n.get('title', '')[:50]
                sentiment = n.get('sentiment', 'neutral')
                emoji = '🟢' if 'positive' in str(sentiment).lower() else '🔴' if 'negative' in str(sentiment).lower() else '⚪'
                print(f"   {emoji} {title}...")
        
        results['news'] = True
        
    except Exception as e:
        print(f"   ❌ Ошибка новостей: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 7. Проверка AI
    print("🧠 7. TRADING AI")
    print("-"*40)
    try:
        from app.core.config import settings
        
        if settings.openrouter_api_key:
            print(f"   ✅ OpenRouter API: ...{settings.openrouter_api_key[-8:]}")
            
            from app.brain import trading_ai
            print(f"   ✅ Trading AI инициализирован")
            print(f"   • Model: {trading_ai.MODEL}")
            results['ai'] = True
        else:
            print("   ⚠️ OPENROUTER_API_KEY не задан")
            
    except Exception as e:
        print(f"   ❌ Ошибка AI: {e}")
    
    print()
    
    # 8. Проверка монитора
    print("🔄 8. МОНИТОР")
    print("-"*40)
    try:
        from app.core.monitor import market_monitor
        
        print(f"   • Running: {'✅' if market_monitor.running else '❌ Остановлен'}")
        print(f"   • Symbols: {market_monitor.symbols}")
        print(f"   • AI Enabled: {'✅' if market_monitor.ai_enabled else '❌'}")
        print(f"   • Paper Trading: {'✅' if market_monitor.paper_trading else '❌ LIVE!'}")
        print(f"   • Balance: ${market_monitor.current_balance:,.2f}")
        print(f"   • Trade Size: ${market_monitor.get_trade_size():,.2f} (15%)")
        print(f"   • Max Trades: {market_monitor.max_open_trades}")
        print(f"   • Check Count: {market_monitor.check_count}")
        
        if market_monitor.last_check:
            print(f"   • Last Check: {market_monitor.last_check}")
        
        results['monitor'] = True
        
    except Exception as e:
        print(f"   ❌ Ошибка монитора: {e}")
    
    print()
    
    # Итоги
    print("="*60)
    print("📋 ИТОГИ ДИАГНОСТИКИ")
    print("="*60)
    
    for component, status in results.items():
        emoji = '✅' if status else '❌'
        print(f"   {emoji} {component.upper()}")
    
    all_ok = all(results.values())
    
    print()
    if all_ok:
        print("🎉 Все компоненты работают!")
        print()
        print("💡 Если нет сигналов — рынок не даёт условий.")
        print("   Стратегии требуют RSI < 30 (перепроданность).")
        print("   Обычно RSI > 40 в нормальном рынке.")
        print("   Бот ждёт подходящий момент — это НОРМАЛЬНО!")
    else:
        print("⚠️ Есть проблемы! Исправьте ошибки выше.")
    
    print()
    print("="*60)


if __name__ == "__main__":
    asyncio.run(diagnose_all())
