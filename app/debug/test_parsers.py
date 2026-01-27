"""
🔍 ЧЕСТНЫЙ ТЕСТ ПАРСЕРОВ
Показывает РЕАЛЬНЫЕ данные из всех источников
"""
import asyncio
from datetime import datetime


async def test_all_parsers():
    """Полный тест всех парсеров"""
    
    print("=" * 70)
    print("🔍 ЧЕСТНЫЙ ТЕСТ ВСЕХ ПАРСЕРОВ")
    print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    results = {
        "twitter": {"status": "❌", "data": None, "error": None},
        "rss": {"status": "❌", "data": None, "error": None},
        "coinglass": {"status": "❌", "data": None, "error": None},
        "whale_ai": {"status": "❌", "data": None, "error": None},
        "news_parser": {"status": "❌", "data": None, "error": None},
    }
    
    # ============================================
    # 1. TWITTER PARSER
    # ============================================
    print("\n" + "=" * 70)
    print("🐦 TWITTER PARSER TEST")
    print("=" * 70)
    
    try:
        from app.parsers.twitter_parser import twitter_parser, get_whale_data, get_twitter_news
        
        # Проверяем Nitter
        print("\n📡 Поиск рабочего Nitter...")
        instance = await twitter_parser._find_working_instance()
        print(f"   Nitter Instance: {instance or '❌ НЕ НАЙДЕН!'}")
        
        if instance:
            # Whale данные
            print("\n🐋 Whale Transactions:")
            whale_data = await get_whale_data()
            
            if whale_data and whale_data.get("total_volume_usd", 0) > 0:
                print(f"   ✅ Total Volume: ${whale_data['total_volume_usd']:,.0f}")
                print(f"   📥 Exchange Inflow: ${whale_data['exchange_inflow']:,.0f}")
                print(f"   📤 Exchange Outflow: ${whale_data['exchange_outflow']:,.0f}")
                print(f"   💰 Net Flow: ${whale_data['net_flow']:+,.0f}")
                print(f"   🎯 Sentiment: {whale_data['sentiment']}")
                
                # Показываем топ транзакции
                if whale_data.get("top_transactions"):
                    print(f"\n   📋 Топ транзакции ({len(whale_data['top_transactions'])}):")
                    for tx in whale_data["top_transactions"][:3]:
                        print(f"      • {tx.coin}: ${tx.amount_usd:,.0f} | {tx.tx_type}")
                        print(f"        {tx.raw_text[:80]}...")
                
                results["twitter"]["status"] = "✅"
                results["twitter"]["data"] = whale_data
            else:
                print("   ⚠️ Нет данных о транзакциях китов")
            
            # Twitter новости
            print("\n📰 Twitter News:")
            news = await get_twitter_news()
            
            if news:
                print(f"   ✅ Найдено новостей: {len(news)}")
                for n in news[:3]:
                    print(f"   [{n.importance}] @{n.author}: {n.text[:60]}...")
                results["twitter"]["status"] = "✅"
            else:
                print("   ⚠️ Новости не получены")
        else:
            print("\n   ❌ Nitter недоступен — Twitter данные не будут получены")
            print("   Причина: Twitter заблокировал все Nitter инстансы в 2023-2024")
            results["twitter"]["error"] = "Nitter blocked"
    
    except ImportError as e:
        print(f"   ❌ Модуль не найден: {e}")
        results["twitter"]["error"] = str(e)
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["twitter"]["error"] = str(e)
    
    # ============================================
    # 2. RSS PARSER
    # ============================================
    print("\n" + "=" * 70)
    print("📰 RSS PARSER TEST")
    print("=" * 70)
    
    try:
        from app.parsers.rss_parser import rss_parser, get_latest_news, get_news_summary
        
        print(f"\n📋 Источников: {len(rss_parser.feeds)}")
        for feed_id, config in rss_parser.feeds.items():
            print(f"   • {config['name']}")
        
        # Получаем новости
        print("\n🔄 Загружаю новости...")
        summary = await get_news_summary()
        
        if summary and summary.get("total", 0) > 0:
            print(f"\n   ✅ Всего новостей: {summary['total']}")
            print(f"   🔴 Critical: {summary['critical']}")
            print(f"   📈 Bullish: {summary.get('bullish', 0)}")
            print(f"   📉 Bearish: {summary.get('bearish', 0)}")
            print(f"   🎯 Overall Sentiment: {summary['sentiment']}")
            
            # Показываем реальные новости
            if summary.get("top_news"):
                print(f"\n   📋 Топ новости:")
                for i, n in enumerate(summary["top_news"][:5], 1):
                    coins = ", ".join(n.coins) if n.coins else "-"
                    importance_emoji = {"critical": "🔴", "high": "🟡", "medium": "⚪", "low": "⚫"}.get(n.importance, "⚪")
                    sentiment_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(n.sentiment, "⚪")
                    print(f"\n   {i}. {importance_emoji}{sentiment_emoji} [{n.source}]")
                    print(f"      {n.title[:70]}...")
                    if n.description:
                        print(f"      {n.description[:100]}...")
                    print(f"      📌 Монеты: {coins}")
            
            # По монетам
            if summary.get("by_coin"):
                print(f"\n   📊 Новости по монетам:")
                for coin, stats in list(summary["by_coin"].items())[:5]:
                    print(f"      {coin}: {stats['count']} (🟢{stats['bullish']} / 🔴{stats['bearish']})")
            
            results["rss"]["status"] = "✅"
            results["rss"]["data"] = {"total": summary["total"], "sentiment": summary["sentiment"]}
        else:
            print("   ⚠️ Новости не получены")
            print("   Возможные причины:")
            print("   - RSS источники недоступны")
            print("   - Проблемы с сетью")
    
    except ImportError as e:
        print(f"   ❌ Модуль не найден: {e}")
        results["rss"]["error"] = str(e)
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["rss"]["error"] = str(e)
    
    # ============================================
    # 3. COINGLASS PARSER
    # ============================================
    print("\n" + "=" * 70)
    print("📊 COINGLASS PARSER TEST")
    print("=" * 70)
    
    try:
        from app.parsers.coinglass_parser import coinglass_parser, get_market_data
        
        print("\n🔄 Загружаю данные рынка (BTC)...")
        data = await get_market_data("BTC")
        
        if data:
            # Ликвидации
            liq = data.get("liquidations", {})
            print(f"\n🔥 Ликвидации:")
            print(f"   1h  — Long: ${liq.get('long_1h', 0)/1e6:.2f}M | Short: ${liq.get('short_1h', 0)/1e6:.2f}M | Total: ${liq.get('total_1h', 0)/1e6:.2f}M")
            print(f"   24h — Long: ${liq.get('long_24h', 0)/1e6:.2f}M | Short: ${liq.get('short_24h', 0)/1e6:.2f}M | Total: ${liq.get('total_24h', 0)/1e6:.2f}M")
            print(f"   Dominant: {liq.get('dominant', 'unknown')}")
            
            # Open Interest
            oi = data.get("open_interest", {})
            print(f"\n📈 Open Interest:")
            if oi.get("total", 0) > 0:
                print(f"   Total: ${oi['total']/1e9:.2f}B")
            print(f"   Change 1h: {oi.get('change_1h', 0):+.2f}%")
            print(f"   Change 4h: {oi.get('change_4h', 0):+.2f}%")
            print(f"   Change 24h: {oi.get('change_24h', 0):+.2f}%")
            print(f"   Trend: {oi.get('trend', 'unknown')}")
            
            if oi.get("by_exchange"):
                print(f"   By Exchange:")
                for ex, val in list(oi["by_exchange"].items())[:3]:
                    print(f"      • {ex}: ${val/1e9:.2f}B")
            
            # Funding
            funding = data.get("funding", {})
            print(f"\n💰 Funding Rate:")
            print(f"   Current: {funding.get('current', 0):+.4f}%")
            print(f"   Predicted: {funding.get('predicted', 0):+.4f}%")
            print(f"   Average: {funding.get('average', 0):+.4f}%")
            print(f"   Sentiment: {funding.get('sentiment', 'unknown')}")
            
            if funding.get("by_exchange"):
                print(f"   By Exchange:")
                for ex, rate in list(funding["by_exchange"].items())[:3]:
                    print(f"      • {ex}: {rate:+.4f}%")
            
            # Анализ
            analysis = data.get("analysis", {})
            print(f"\n🎯 Анализ:")
            print(f"   Risk Score: {analysis.get('risk_score', 0)}/100")
            print(f"   Overall Sentiment: {analysis.get('overall_sentiment', 'unknown')}")
            
            if analysis.get("signals"):
                print(f"\n   ⚠️ Сигналы ({len(analysis['signals'])}):")
                for s in analysis["signals"]:
                    print(f"      • {s}")
            else:
                print(f"\n   ✅ Нет значимых сигналов — рынок спокоен")
            
            results["coinglass"]["status"] = "✅"
            results["coinglass"]["data"] = {
                "funding": funding.get("current", 0),
                "oi_change": oi.get("change_1h", 0),
                "risk": analysis.get("risk_score", 0)
            }
        else:
            print("   ⚠️ Данные не получены")
    
    except ImportError as e:
        print(f"   ❌ Модуль не найден: {e}")
        results["coinglass"]["error"] = str(e)
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["coinglass"]["error"] = str(e)
    
    # ============================================
    # 4. NEWS PARSER (CryptoCompare + Calendar)
    # ============================================
    print("\n" + "=" * 70)
    print("📰 NEWS PARSER TEST (CryptoCompare + Calendar)")
    print("=" * 70)
    
    try:
        from app.intelligence.news_parser import news_parser
        
        print("\n🔄 Загружаю новости и календарь...")
        context = await news_parser.get_market_context()
        
        if context:
            print(f"\n📊 Market Context:")
            print(f"   News Count: {context.get('news_count', 0)}")
            print(f"   Upcoming Events: {context.get('upcoming_events', 0)}")
            print(f"   Market Mode: {context.get('market_mode', 'unknown')}")
            print(f"   Combined Sentiment: {context.get('combined_sentiment', 'unknown')}")
            print(f"   Total Sources: {context.get('total_news_sources', 0)}")
            
            # Новости
            news = context.get("news", [])
            if news:
                print(f"\n   📰 Новости из CryptoCompare ({len(news)}):")
                for n in news[:3]:
                    print(f"      • [{n.get('importance', '?')}] {n.get('title', '')[:60]}...")
                    print(f"        Source: {n.get('source', '?')} | Sentiment: {n.get('sentiment', 0):.2f}")
            
            # Календарь
            calendar = context.get("calendar", [])
            if calendar:
                print(f"\n   📅 Календарь событий ({len(calendar)}):")
                for e in calendar:
                    print(f"      • [{e.get('importance', '?')}] {e.get('event', '')}")
                    print(f"        Time: {e.get('time', '')} | Recommendation: {e.get('recommendation', '?')}")
            else:
                print(f"\n   📅 Нет ближайших важных событий")
            
            # Trending
            trending = context.get("trending", [])
            if trending:
                print(f"\n   🔥 Trending: {', '.join(trending[:5])}")
            
            results["news_parser"]["status"] = "✅"
            results["news_parser"]["data"] = {
                "news": len(news),
                "events": len(calendar),
                "mode": context.get("market_mode")
            }
        else:
            print("   ⚠️ Данные не получены")
    
    except ImportError as e:
        print(f"   ❌ Модуль не найден: {e}")
        results["news_parser"]["error"] = str(e)
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["news_parser"]["error"] = str(e)
    
    # ============================================
    # 5. WHALE AI (Интеграция всего)
    # ============================================
    print("\n" + "=" * 70)
    print("🐋 WHALE AI INTEGRATION TEST")
    print("=" * 70)
    
    try:
        from app.ai.whale_ai import whale_ai, check_whale_activity
        
        print("\n🔄 Запускаю полный анализ BTC...")
        alert = await check_whale_activity("BTC")
        metrics = whale_ai.last_metrics
        
        if metrics:
            print(f"\n📊 Метрики от Whale AI:")
            print(f"   Funding Rate: {metrics.funding_rate:+.4f}%")
            print(f"   Funding Sentiment: {metrics.funding_sentiment}")
            print(f"   OI Change 1h: {metrics.oi_change_1h:+.2f}%")
            print(f"   OI Change 24h: {metrics.oi_change_24h:+.2f}%")
            print(f"   Long/Short: {metrics.long_ratio:.1f}% / {metrics.short_ratio:.1f}%")
            print(f"   L/S Sentiment: {metrics.ls_sentiment}")
            print(f"   Fear & Greed: {metrics.fear_greed_index} ({metrics.fear_greed_label})")
            
            # Данные из парсеров
            print(f"\n   🐋 Whale Data (Twitter):")
            print(f"      Net Flow: ${metrics.whale_net_flow:+,.0f}")
            print(f"      Inflow: ${metrics.whale_inflow:,.0f}")
            print(f"      Outflow: ${metrics.whale_outflow:,.0f}")
            print(f"      Sentiment: {metrics.whale_sentiment}")
            print(f"      Transactions: {metrics.whale_transactions}")
            
            print(f"\n   🔥 Liquidations (Coinglass):")
            print(f"      Total 1h: ${metrics.liquidations_1h:,.0f}")
            print(f"      Long: ${metrics.liq_long:,.0f}")
            print(f"      Short: ${metrics.liq_short:,.0f}")
            
            print(f"\n🚨 Alert:")
            print(f"   Level: {alert.level.value.upper()}")
            print(f"   Message: {alert.message}")
            print(f"   Recommendation: {alert.recommendation}")
            
            bias = whale_ai.get_trading_bias()
            bias_emoji = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"}.get(bias, "⚪")
            print(f"\n{bias_emoji} Trading Bias: {bias}")
            
            results["whale_ai"]["status"] = "✅"
            results["whale_ai"]["data"] = {
                "alert": alert.level.value,
                "bias": bias,
                "funding": metrics.funding_rate,
                "fear_greed": metrics.fear_greed_index
            }
        else:
            print("   ⚠️ Метрики не получены")
    
    except ImportError as e:
        print(f"   ❌ Модуль не найден: {e}")
        results["whale_ai"]["error"] = str(e)
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        results["whale_ai"]["error"] = str(e)
    
    # ============================================
    # ИТОГОВЫЙ ОТЧЁТ
    # ============================================
    print("\n" + "=" * 70)
    print("📋 ИТОГОВЫЙ ОТЧЁТ")
    print("=" * 70)
    
    print("\n┌────────────────┬────────┬─────────────────────────────────┐")
    print("│ Компонент      │ Статус │ Данные                          │")
    print("├────────────────┼────────┼─────────────────────────────────┤")
    
    for name, result in results.items():
        status = result["status"]
        if result["data"]:
            data_str = str(result["data"])[:30]
        elif result["error"]:
            data_str = f"Error: {result['error'][:20]}"
        else:
            data_str = "Нет данных"
        print(f"│ {name:14} │ {status:6} │ {data_str:31} │")
    
    print("└────────────────┴────────┴─────────────────────────────────┘")
    
    # Подсчёт
    working = sum(1 for r in results.values() if r["status"] == "✅")
    total = len(results)
    
    print(f"\n🎯 Работает: {working}/{total} компонентов")
    
    if working == total:
        print("\n✅ ВСЕ ПАРСЕРЫ РАБОТАЮТ!")
    elif working >= total - 1:
        print("\n⚠️ Почти всё работает (Twitter недоступен — это нормально)")
    elif working > 0:
        print("\n⚠️ Часть парсеров работает")
    else:
        print("\n❌ Ни один парсер не работает!")
    
    return results


if __name__ == "__main__":
    asyncio.run(test_all_parsers())
