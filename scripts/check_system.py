#!/usr/bin/env python3
"""
Check System - Проверка системы
===============================

Использование:
    python scripts/check_system.py
"""

import asyncio
import sys
sys.path.insert(0, "/root/crypto-bot")


async def check_all():
    """Проверить все компоненты"""
    print("🔍 Проверка системы CryptoDen\n")
    
    errors = []
    
    # 1. Config
    print("1️⃣ Проверка конфигурации...")
    try:
        from app.core.config import settings
        print(f"   ✅ Config loaded")
        print(f"   📱 Telegram token: {'✅ Set' if settings.telegram_bot_token else '❌ Missing'}")
        print(f"   🔑 Bybit API: {'✅ Set' if settings.bybit_api_key else '⚠️ Not set'}")
        print(f"   🤖 OpenRouter: {'✅ Set' if settings.openrouter_api_key else '⚠️ Not set'}")
    except Exception as e:
        print(f"   ❌ Config error: {e}")
        errors.append(("Config", str(e)))
    
    # 2. Database
    print("\n2️⃣ Проверка Redis...")
    try:
        from app.core.database import redis_client
        await redis_client.connect()
        await redis_client.set("test", "ok", ex=10)
        result = await redis_client.get("test")
        if result == "ok":
            print(f"   ✅ Redis connected")
        else:
            print(f"   ⚠️ Redis connected but test failed")
        await redis_client.close()
    except Exception as e:
        print(f"   ⚠️ Redis not available: {e}")
    
    # 3. Bybit API
    print("\n3️⃣ Проверка Bybit API...")
    try:
        from app.trading.bybit.client import bybit_client
        ticker = await bybit_client.get_ticker("BTC")
        if ticker:
            print(f"   ✅ Bybit API working")
            print(f"   📊 BTC price: ${ticker['price']:,.2f}")
        else:
            print(f"   ⚠️ Bybit API returned no data")
        await bybit_client.close()
    except Exception as e:
        print(f"   ❌ Bybit API error: {e}")
        errors.append(("Bybit", str(e)))
    
    # 4. Strategies
    print("\n4️⃣ Проверка стратегий...")
    try:
        from app.strategies.config import strategy_config
        strategies = strategy_config.get_all()
        print(f"   ✅ {len(strategies)} стратегий загружено")
        for coin, strategy in list(strategies.items())[:3]:
            print(f"   📊 {coin}: {strategy.get('strategy', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Strategies error: {e}")
        errors.append(("Strategies", str(e)))
    
    # 5. Indicators
    print("\n5️⃣ Проверка индикаторов...")
    try:
        from app.strategies.indicators import calc_rsi, calc_ema, calc_macd
        test_prices = [100 + i for i in range(50)]
        rsi = calc_rsi(test_prices)
        ema = calc_ema(test_prices, 14)
        print(f"   ✅ Индикаторы работают (RSI={rsi:.1f}, EMA={ema:.1f})")
    except Exception as e:
        print(f"   ❌ Indicators error: {e}")
        errors.append(("Indicators", str(e)))
    
    # 6. Bot handlers
    print("\n6️⃣ Проверка handlers...")
    try:
        from app.bot.handlers import all_routers
        print(f"   ✅ {len(all_routers)} routers loaded")
    except Exception as e:
        print(f"   ❌ Handlers error: {e}")
        errors.append(("Handlers", str(e)))
    
    # Summary
    print("\n" + "="*50)
    if errors:
        print(f"⚠️ Найдено {len(errors)} ошибок:")
        for name, error in errors:
            print(f"   ❌ {name}: {error}")
    else:
        print("✅ Все компоненты работают!")
    print("="*50)


def main():
    asyncio.run(check_all())


if __name__ == "__main__":
    main()
