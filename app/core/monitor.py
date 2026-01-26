"""
Market Monitor — Главный цикл мониторинга 24/7
Проверяет сигналы, открывает/закрывает сделки
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.logger import logger
from app.strategies import strategy_checker, get_enabled_strategies, Signal
from app.trading import trade_manager
from app.trading.bybit.client import BybitClient
from app.backtesting.data_loader import BybitDataLoader
from app.notifications import telegram_bot


class MarketMonitor:
    """
    24/7 мониторинг рынка
    
    Цикл:
    1. Получить цены с Bybit
    2. Загрузить свечи для анализа
    3. Проверить стратегии
    4. Открыть сделки по сигналам
    5. Обновить активные сделки
    6. Закрыть по SL/TP/Trailing
    """
    
    def __init__(self):
        self.running: bool = False
        self.check_interval: int = 60  # секунд
        self.symbols: List[str] = []
        self.last_check: Optional[datetime] = None
        self.check_count: int = 0
        
        # Режим работы
        self.paper_trading: bool = True  # True = не торгуем реально
        self.trade_value_usdt: float = 50.0  # Размер сделки
        
        # Bybit клиент
        self.bybit = BybitClient(testnet=False)
        
        logger.info("MarketMonitor initialized")
    
    async def start(self):
        """Запустить мониторинг"""
        
        self.running = True
        self.symbols = list(get_enabled_strategies().keys())
        
        logger.info("=" * 50)
        logger.info("🚀 MARKET MONITOR STARTED")
        logger.info(f"📊 Symbols: {', '.join(self.symbols)}")
        logger.info(f"⏱️ Check interval: {self.check_interval}s")
        logger.info(f"💰 Trade size: ${self.trade_value_usdt}")
        logger.info(f"📝 Mode: {'PAPER' if self.paper_trading else 'LIVE'}")
        logger.info("=" * 50)
        
        async with self.bybit:
            while self.running:
                try:
                    await self._check_cycle()
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                
                if self.running:
                    await asyncio.sleep(self.check_interval)
    
    async def stop(self):
        """Остановить мониторинг"""
        self.running = False
        logger.info("🛑 Market Monitor stopped")
    
    async def _check_cycle(self):
        """Один цикл проверки"""
        
        self.last_check = datetime.now(timezone.utc)
        self.check_count += 1
        
        logger.info(f"\n⏰ Check #{self.check_count} at {self.last_check.strftime('%H:%M:%S')}")
        
        # 1. Получаем цены
        prices = await self.bybit.get_prices(self.symbols)
        
        if not prices:
            logger.warning("Failed to get prices")
            return
        
        # Показываем цены
        price_str = " | ".join([f"{s}: ${p:,.2f}" for s, p in list(prices.items())[:4]])
        logger.info(f"💹 {price_str}...")
        
        # 2. Обновляем активные сделки
        await trade_manager.update_prices(prices)
        
        # 3. Загружаем свечи и проверяем стратегии
        signals = await self._check_strategies(prices)
        
        # 4. Обрабатываем сигналы
        for signal in signals:
            await self._process_signal(signal)
        
        # 5. Логируем статус
        active = trade_manager.get_active_trades()
        stats = trade_manager.get_statistics()
        
        if active:
            logger.info(f"📊 Active trades: {len(active)}")
            for t in active:
                logger.info(f"   {t.symbol} {t.direction}: {t.unrealized_pnl_percent:+.2f}%")
        
        if stats.get('total_trades', 0) > 0:
            logger.info(f"📈 Stats: {stats['wins']}W/{stats['losses']}L | PnL: ${stats['total_pnl']:.2f}")
    
    async def _check_strategies(self, prices: Dict[str, float]) -> List[Signal]:
        """Проверить стратегии для всех символов"""
        
        signals = []
        loader = BybitDataLoader()
        
        for symbol, price in prices.items():
            # Загружаем из кэша
            df = loader.load_from_cache(symbol, '5m')
            
            if df is None or len(df) < 50:
                logger.debug(f"{symbol}: No cached data")
                continue
            
            # Берём последние 100 свечей
            df = df.tail(100).copy()
            
            # Проверяем стратегию
            signal = await strategy_checker.check_symbol(symbol, df, price)
            
            if signal:
                signals.append(signal)
                logger.info(f"🎯 SIGNAL: {symbol} {signal.direction}")
                logger.info(f"   Strategy: {signal.strategy_name}")
                logger.info(f"   Entry: ${price:.4f}")
                logger.info(f"   SL: ${signal.stop_loss:.4f} | TP: ${signal.take_profit:.4f}")
        
        return signals
    
    async def _process_signal(self, signal: Signal):
        """Обработать сигнал — открыть сделку"""
        
        # Уведомляем о сигнале
        await telegram_bot.notify_signal(signal)
        
        # Проверяем можно ли открыть
        can_open, reason = trade_manager.can_open_trade(signal.symbol)
        
        if not can_open:
            logger.info(f"⏭️ Skip signal: {reason}")
            return
        
        trade = None
        
        if self.paper_trading:
            # Paper trading — только симуляция
            trade = await trade_manager.open_trade(signal, self.trade_value_usdt)
            logger.info(f"📝 PAPER TRADE opened: {trade.id}")
        
        else:
            # LIVE trading — реальный ордер!
            logger.info(f"🔴 LIVE ORDER: {signal.symbol} {signal.direction}")
            
            if signal.direction == "LONG":
                resp = await self.bybit.market_buy(
                    signal.symbol, 
                    quote_qty=self.trade_value_usdt
                )
            else:
                # Для SHORT на споте нужно сначала иметь монету
                logger.warning("SHORT on spot requires holding the coin")
                return
            
            if resp.get('retCode') == 0:
                trade = await trade_manager.open_trade(signal, self.trade_value_usdt)
                logger.info(f"✅ LIVE TRADE opened: {trade.id}")
            else:
                logger.error(f"❌ Order failed: {resp}")
                await telegram_bot.notify_error(f"Order failed: {resp.get('retMsg')}")
        
        # Уведомляем об открытии сделки
        if trade:
            await telegram_bot.notify_trade_opened(trade)
    
    def get_status(self) -> dict:
        """Статус монитора"""
        return {
            'running': self.running,
            'check_count': self.check_count,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'symbols': self.symbols,
            'paper_trading': self.paper_trading,
            'active_trades': len(trade_manager.get_active_trades()),
            'strategy_status': strategy_checker.get_status(),
            'trade_stats': trade_manager.get_statistics(),
        }


# Глобальный экземпляр
market_monitor = MarketMonitor()
