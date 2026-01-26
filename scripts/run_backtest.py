#!/usr/bin/env python3
"""
Run Backtest — Бэктестинг с валидацией на разных периодах
"""
import asyncio
import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.backtesting.data_loader import BybitDataLoader
from app.backtesting.strategies import strategy_library
from app.backtesting.backtest_engine import BacktestEngine
from app.core.logger import logger


async def run_backtest_period(
    symbols: list,
    timeframe: str,
    start_date: str,
    end_date: str,
    tp: float,
    sl: float,
    period_name: str,
    download: bool = False
) -> dict:
    """Запуск бэктеста за период"""
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📅 БЭКТЕСТ: {period_name}")
    logger.info(f"📆 Период: {start_date} — {end_date}")
    logger.info(f"{'='*60}")
    
    results = {}
    engine = BacktestEngine(tp_percent=tp, sl_percent=sl, min_trades=20)
    loader = BybitDataLoader()
    
    for symbol in symbols:
        logger.info(f"\n🔍 {symbol}...")
        
        # Загружаем данные
        if download:
            async with BybitDataLoader() as dl:
                df = await dl.download_symbol(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date
                )
        else:
            df = loader.load_from_cache(symbol, timeframe)
        
        if df is None or len(df) < 100:
            logger.warning(f"⚠️ Недостаточно данных для {symbol}")
            continue
        
        # Фильтруем по датам
        df['timestamp'] = df['timestamp'].dt.tz_localize(None) if df['timestamp'].dt.tz else df['timestamp']
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        df = df[(df['timestamp'] >= start_dt) & (df['timestamp'] <= end_dt)]
        
        if len(df) < 100:
            logger.warning(f"⚠️ Недостаточно данных после фильтрации: {len(df)}")
            continue
        
        logger.info(f"📊 {len(df):,} свечей ({df['timestamp'].min()} — {df['timestamp'].max()})")
        
        # Тестируем все стратегии
        symbol_results = await engine.test_all_strategies(df, symbol)
        
        # Сортируем по win rate
        symbol_results = sorted(symbol_results, key=lambda x: x.get('win_rate', 0), reverse=True)
        
        results[symbol] = symbol_results
        
        # Показываем топ-3
        if symbol_results:
            logger.info(f"🏆 TOP-3:")
            for i, top in enumerate(symbol_results[:3], 1):
                logger.info(f"   {i}. {top['strategy'][:40]} — WR: {top['win_rate']:.1f}%")
    
    return results


async def compare_periods(results_2024: dict, results_2025: dict) -> dict:
    """Сравнение результатов между периодами"""
    
    logger.info(f"\n{'='*70}")
    logger.info("📊 СРАВНЕНИЕ 2024 vs 2025")
    logger.info(f"{'='*70}")
    
    comparison = {}
    
    for symbol in results_2024.keys():
        if symbol not in results_2025:
            continue
        
        # Лучшие стратегии 2024
        top_2024 = {r['strategy']: r for r in results_2024[symbol][:30]}
        
        # Проверяем как они работают в 2025
        comparison[symbol] = []
        
        for strategy_name, data_2024 in top_2024.items():
            # Ищем эту стратегию в результатах 2025
            data_2025 = None
            for r in results_2025[symbol]:
                if r['strategy'] == strategy_name:
                    data_2025 = r
                    break
            
            if data_2025:
                wr_2024 = data_2024.get('win_rate', 0)
                wr_2025 = data_2025.get('win_rate', 0)
                
                # Стабильная если разница < 10%
                stable = abs(wr_2024 - wr_2025) < 10
                
                comparison[symbol].append({
                    'strategy': strategy_name,
                    'wr_2024': wr_2024,
                    'wr_2025': wr_2025,
                    'diff': wr_2025 - wr_2024,
                    'stable': stable,
                    'avg_wr': (wr_2024 + wr_2025) / 2,
                    'trades_2024': data_2024.get('total_trades', 0),
                    'trades_2025': data_2025.get('total_trades', 0),
                    'pnl_2024': data_2024.get('total_pnl', 0),
                    'pnl_2025': data_2025.get('total_pnl', 0),
                })
        
        # Сортируем по среднему WR
        comparison[symbol] = sorted(
            comparison[symbol], 
            key=lambda x: x['avg_wr'], 
            reverse=True
        )
        
        # Показываем результаты
        logger.info(f"\n📈 {symbol}:")
        logger.info(f"{'Стратегия':<45} {'2024':>8} {'2025':>8} {'Avg':>8} {'Stable':>8}")
        logger.info("-" * 80)
        
        for s in comparison[symbol][:7]:
            stable_icon = "✅" if s['stable'] else "⚠️"
            logger.info(
                f"{s['strategy'][:44]:<45} {s['wr_2024']:>7.1f}% {s['wr_2025']:>7.1f}% "
                f"{s['avg_wr']:>7.1f}% {stable_icon:>8}"
            )
    
    return comparison


async def run_validation(args):
    """Запуск валидации 2024 vs 2025"""
    
    symbols = BybitDataLoader.SYMBOLS
    if args.symbol:
        symbols = [args.symbol.upper()]
    
    # Бэктест 2024
    results_2024 = await run_backtest_period(
        symbols=symbols,
        timeframe=args.timeframe,
        start_date="2024-01-01",
        end_date="2024-12-31",
        tp=args.tp,
        sl=args.sl,
        period_name="2024",
        download=args.download
    )
    
    # Бэктест 2025 (используем данные до текущей даты)
    results_2025 = await run_backtest_period(
        symbols=symbols,
        timeframe=args.timeframe,
        start_date="2025-01-01",
        end_date="2025-12-31",
        tp=args.tp,
        sl=args.sl,
        period_name="2025",
        download=args.download
    )
    
    # Сравнение
    comparison = await compare_periods(results_2024, results_2025)
    
    # Сохраняем результаты
    report = {
        'generated_at': datetime.now().isoformat(),
        'parameters': {
            'tp_percent': args.tp,
            'sl_percent': args.sl,
            'timeframe': args.timeframe,
        },
        'comparison': comparison,
        'stable_strategies': {}
    }
    
    # Выбираем стабильные стратегии
    for symbol, strategies in comparison.items():
        # WR >= 60% в оба года и стабильная
        stable = [
            s for s in strategies 
            if s['stable'] and s['wr_2024'] >= 60 and s['wr_2025'] >= 55
        ]
        if stable:
            report['stable_strategies'][symbol] = stable[0]
    
    # Сохраняем
    report_path = Path('/root/crypto-bot/reports') / f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    logger.info(f"\n💾 Отчёт сохранён: {report_path}")
    
    # Итоговая таблица стабильных стратегий
    logger.info(f"\n{'='*70}")
    logger.info("🏆 СТАБИЛЬНЫЕ СТРАТЕГИИ (WR >= 60% в 2024 И >= 55% в 2025)")
    logger.info(f"{'='*70}")
    
    if report['stable_strategies']:
        for symbol, data in report['stable_strategies'].items():
            logger.info(f"\n✅ {symbol}: {data['strategy']}")
            logger.info(f"   2024: {data['wr_2024']:.1f}% | 2025: {data['wr_2025']:.1f}% | Avg: {data['avg_wr']:.1f}%")
            logger.info(f"   Trades: {data['trades_2024']} (2024) / {data['trades_2025']} (2025)")
    else:
        logger.warning("⚠️ Стабильных стратегий не найдено")
    
    return report


async def run_single_period(args):
    """Бэктест за один период"""
    
    symbols = BybitDataLoader.SYMBOLS if args.all else [args.symbol.upper() if args.symbol else 'BTC']
    
    results = await run_backtest_period(
        symbols=symbols,
        timeframe=args.timeframe,
        start_date=f"{args.year}-01-01",
        end_date=f"{args.year}-12-31",
        tp=args.tp,
        sl=args.sl,
        period_name=args.year,
        download=args.download
    )
    
    # Сохраняем отчёт
    if not args.no_save and results:
        report = {
            'generated_at': datetime.now().isoformat(),
            'year': args.year,
            'parameters': {'tp': args.tp, 'sl': args.sl, 'timeframe': args.timeframe},
            'best_per_symbol': {
                symbol: data[0] if data else None
                for symbol, data in results.items()
            }
        }
        
        report_path = Path('/root/crypto-bot/reports') / f"backtest_{args.year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"\n💾 Отчёт: {report_path}")
    
    # Итог
    if results:
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 ЛУЧШИЕ СТРАТЕГИИ {args.year}")
        logger.info(f"{'='*60}")
        
        for symbol, data in results.items():
            if data:
                best = data[0]
                logger.info(f"  {symbol}: {best['strategy'][:40]} | WR={best['win_rate']:.1f}%")


async def main():
    parser = argparse.ArgumentParser(description='CryptoDen Backtester')
    parser.add_argument('--validate', action='store_true', help='Run 2024 vs 2025 validation')
    parser.add_argument('--year', type=str, default='2024', help='Year to test')
    parser.add_argument('--symbol', type=str, help='Single symbol')
    parser.add_argument('--all', action='store_true', help='All symbols')
    parser.add_argument('--download', action='store_true', help='Download fresh data')
    parser.add_argument('--timeframe', type=str, default='5m')
    parser.add_argument('--tp', type=float, default=0.3, help='Take profit %%')
    parser.add_argument('--sl', type=float, default=0.5, help='Stop loss %%')
    parser.add_argument('--no-save', action='store_true', help='Do not save report')
    
    args = parser.parse_args()
    
    print()
    print("=" * 70)
    print("🚀 CRYPTODEN BACKTESTER")
    print("=" * 70)
    print(f"📊 Стратегий: {strategy_library.count()}")
    print(f"⚙️ TP: {args.tp}% | SL: {args.sl}%")
    print("=" * 70)
    
    # Категории
    categories = strategy_library.list_categories()
    print("\n📋 Категории стратегий:")
    for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"   • {cat}: {cnt}")
    print()
    
    if args.validate:
        await run_validation(args)
    else:
        await run_single_period(args)
    
    logger.info("\n✅ Готово!")


if __name__ == "__main__":
    asyncio.run(main())
