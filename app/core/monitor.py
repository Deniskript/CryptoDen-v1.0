"""
Market Monitor — Главный цикл с AI
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.logger import logger
from app.strategies import strategy_checker, get_enabled_strategies, Signal
from app.trading import trade_manager, CloseReason
from app.trading.bybit.client import BybitClient
from app.intelligence.news_parser import news_parser
from app.brain import trading_ai, AIAction
from app.notifications import telegram_bot
from app.backtesting.data_loader import BybitDataLoader


class MarketMonitor:
    """
    24/7 мониторинг с AI
    
    Цикл (каждые 60 сек):
    1. Получить цены с Bybit
    2. Обновить контекст новостей (каждые 5 мин)
    3. Проверить стратегии
    4. AI анализирует: новости + стратегия + позиции
    5. Выполнить решение AI
    6. Обновить SL/TP активных позиций через AI
    """
    
    def __init__(self):
        self.running: bool = False
        self.check_interval: int = 60  # секунд
        self.news_interval: int = 300  # 5 минут
        self.position_check_interval: int = 30  # 30 сек для активных позиций
        
        self.symbols: List[str] = []
        self.last_check: Optional[datetime] = None
        self.last_news_update: Optional[datetime] = None
        self.market_context: dict = {}
        self.check_count: int = 0
        
        # Режим
        self.paper_trading: bool = True
        self.trade_value_usdt: float = 50.0
        
        # AI контроль
        self.ai_enabled: bool = True
        self.min_confidence: int = 60  # Минимальная уверенность AI для сделки
        
        # Клиенты
        self.bybit = BybitClient(testnet=False)
        self.data_loader = BybitDataLoader()
        
        logger.info("MarketMonitor initialized with AI")
    
    async def start(self):
        """Запустить мониторинг"""
        
        self.running = True
        self.symbols = list(get_enabled_strategies().keys())
        
        logger.info("=" * 60)
        logger.info("🚀 MARKET MONITOR STARTED (AI ENABLED)")
        logger.info(f"📊 Symbols: {', '.join(self.symbols)}")
        logger.info(f"🧠 AI: {'ON' if self.ai_enabled else 'OFF'}")
        logger.info(f"📝 Mode: {'PAPER' if self.paper_trading else 'LIVE'}")
        logger.info(f"⏱️ Check interval: {self.check_interval}s")
        logger.info("=" * 60)
        
        # Первоначальная загрузка новостей
        await self._update_news_context()
        
        # Отправляем в Telegram
        await telegram_bot.send_message(
            "🚀 *CryptoDen Bot Started*\n\n"
            f"📊 Symbols: {len(self.symbols)}\n"
            f"🧠 AI: {'Enabled' if self.ai_enabled else 'Disabled'}\n"
            f"📝 Mode: {'Paper' if self.paper_trading else 'Live'}"
        )
        
        # Основной цикл
        async with self.bybit:
            while self.running:
                try:
                    await self._main_cycle()
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                    await telegram_bot.notify_error(str(e))
                
                if self.running:
                    await asyncio.sleep(self.check_interval)
    
    async def stop(self):
        """Остановить"""
        self.running = False
        await telegram_bot.send_message("🛑 *Bot Stopped*")
        logger.info("🛑 Monitor stopped")
    
    async def _main_cycle(self):
        """Главный цикл"""
        
        self.last_check = datetime.now(timezone.utc)
        self.check_count += 1
        
        logger.info(f"\n⏰ Cycle #{self.check_count} at {self.last_check.strftime('%H:%M:%S')}")
        
        # 1. Получаем цены
        prices = await self.bybit.get_prices(self.symbols)
        
        if not prices:
            logger.warning("Failed to get prices")
            return
        
        # Показываем цены
        price_str = " | ".join([f"{s}: ${p:,.2f}" for s, p in list(prices.items())[:3]])
        logger.info(f"💹 {price_str}...")
        
        # 2. Обновляем новости (каждые 5 мин)
        await self._update_news_context_if_needed()
        
        # 3. Обновляем активные позиции
        await trade_manager.update_prices(prices)
        
        # 4. Проверяем активные позиции через AI (двигаем SL/TP)
        if self.ai_enabled:
            await self._check_active_positions_with_ai(prices)
        
        # 5. Ищем новые сигналы
        await self._check_for_signals(prices)
        
        # Логируем статус
        active = trade_manager.get_active_trades()
        mode = self.market_context.get('market_mode', 'NORMAL')
        
        logger.info(f"📊 Mode: {mode} | Active trades: {len(active)}")
        
        if active:
            for t in active:
                logger.info(f"   {t.symbol} {t.direction}: {t.unrealized_pnl_percent:+.2f}%")
    
    async def _update_news_context(self):
        """Обновить контекст новостей"""
        
        try:
            async with news_parser:
                self.market_context = await news_parser.get_market_context()
            
            self.last_news_update = datetime.now(timezone.utc)
            
            mode = self.market_context.get('market_mode', 'NORMAL')
            news_count = len(self.market_context.get('news', []))
            events = len(self.market_context.get('calendar', []))
            
            logger.info(f"📰 News updated | Mode: {mode} | News: {news_count} | Events: {events}")
            
        except Exception as e:
            logger.error(f"News update error: {e}")
            self.market_context = {"market_mode": "NORMAL", "news": [], "calendar": []}
    
    async def _update_news_context_if_needed(self):
        """Обновить новости если прошло 5 минут"""
        
        if self.last_news_update is None:
            await self._update_news_context()
            return
        
        elapsed = (datetime.now(timezone.utc) - self.last_news_update).total_seconds()
        if elapsed >= self.news_interval:
            await self._update_news_context()
    
    async def _check_active_positions_with_ai(self, prices: Dict[str, float]):
        """Проверить активные позиции — нужно ли двигать SL/TP"""
        
        trades = trade_manager.get_active_trades()
        
        if not trades:
            return
        
        for trade in trades:
            if trade.symbol not in prices:
                continue
            
            current_price = prices[trade.symbol]
            
            try:
                # Спрашиваем AI нужно ли корректировать
                async with trading_ai:
                    decision = await trading_ai.should_adjust_position(
                        symbol=trade.symbol,
                        position={
                            'direction': trade.direction,
                            'entry_price': trade.entry_price,
                            'pnl_percent': trade.unrealized_pnl_percent,
                            'stop_loss': trade.stop_loss,
                            'take_profit': trade.take_profit,
                        },
                        market_context=self.market_context,
                        current_price=current_price
                    )
                
                # Применяем решение
                if decision.action == AIAction.ADJUST_SL and decision.new_sl:
                    old_sl = trade.stop_loss
                    trade.stop_loss = decision.new_sl
                    logger.info(f"🧠 AI moved SL for {trade.symbol}: ${old_sl:.2f} → ${decision.new_sl:.2f}")
                    await telegram_bot.send_message(
                        f"🧠 *AI Adjusted SL*\n\n"
                        f"📍 {trade.symbol}\n"
                        f"SL: ${old_sl:.2f} → ${decision.new_sl:.2f}\n"
                        f"📝 {decision.reason}"
                    )
                
                elif decision.action == AIAction.ADJUST_TP and decision.new_tp:
                    old_tp = trade.take_profit
                    trade.take_profit = decision.new_tp
                    logger.info(f"🧠 AI moved TP for {trade.symbol}: ${old_tp:.2f} → ${decision.new_tp:.2f}")
                
                elif decision.action == AIAction.CLOSE:
                    logger.info(f"🧠 AI closing {trade.symbol}: {decision.reason}")
                    await trade_manager.close_trade(trade.id, CloseReason.MANUAL)
                    
            except Exception as e:
                logger.error(f"AI position check error for {trade.symbol}: {e}")
    
    async def _check_for_signals(self, prices: Dict[str, float]):
        """Проверить стратегии и открыть сделки"""
        
        for symbol, price in prices.items():
            try:
                # Загружаем данные из кэша
                df = self.data_loader.load_from_cache(symbol, '5m')
                
                if df is None or len(df) < 50:
                    continue
                
                # Берём последние 100 свечей
                df = df.tail(100).copy()
                
                # Проверяем стратегию
                signal = await strategy_checker.check_symbol(symbol, df, price)
                
                if not signal:
                    continue
                
                logger.info(f"🎯 Signal: {symbol} {signal.direction}")
                
                # Если AI выключен — торгуем по стратегии напрямую
                if not self.ai_enabled:
                    await telegram_bot.notify_signal(signal)
                    await self._execute_signal(signal)
                    continue
                
                # AI анализирует
                async with trading_ai:
                    decision = await trading_ai.analyze(
                        symbol=symbol,
                        market_context=self.market_context,
                        strategy_signal={
                            'direction': signal.direction,
                            'strategy_name': signal.strategy_name,
                            'win_rate': signal.win_rate,
                            'entry_price': signal.entry_price,
                            'stop_loss': signal.stop_loss,
                            'take_profit': signal.take_profit,
                        },
                        current_position=None,
                        price_data={'recent_candles': []},
                        current_price=price
                    )
                
                # Уведомляем о сигнале
                await telegram_bot.notify_signal(signal)
                
                # Выполняем решение AI
                if decision.action in [AIAction.OPEN_LONG, AIAction.OPEN_SHORT]:
                    if decision.confidence >= self.min_confidence:
                        # Корректируем SL/TP от AI
                        if decision.stop_loss:
                            signal.stop_loss = decision.stop_loss
                        if decision.take_profit:
                            signal.take_profit = decision.take_profit
                        
                        # Размер сделки
                        trade_value = self.trade_value_usdt * decision.size_multiplier
                        
                        await self._execute_signal(signal, trade_value)
                        
                        await telegram_bot.send_message(
                            f"🧠 *AI Approved Trade*\n\n"
                            f"📍 {symbol} {decision.direction}\n"
                            f"📊 Confidence: {decision.confidence}%\n"
                            f"📦 Size: {decision.size_multiplier}x (${trade_value:.0f})\n"
                            f"📝 {decision.reason}\n"
                            f"📰 News: {decision.news_influence}"
                        )
                    else:
                        logger.info(f"🧠 AI rejected {symbol}: confidence {decision.confidence}% < {self.min_confidence}%")
                
                elif decision.action == AIAction.WAIT:
                    logger.info(f"🧠 AI says WAIT for {symbol}: {decision.reason}")
                    
            except Exception as e:
                logger.error(f"Signal check error for {symbol}: {e}")
    
    async def _execute_signal(self, signal: Signal, value: float = None):
        """Выполнить сигнал — открыть сделку"""
        
        value = value or self.trade_value_usdt
        
        can_open, reason = trade_manager.can_open_trade(signal.symbol)
        if not can_open:
            logger.info(f"⏭️ Skip {signal.symbol}: {reason}")
            return
        
        if self.paper_trading:
            trade = await trade_manager.open_trade(signal, value)
            if trade:
                await telegram_bot.notify_trade_opened(trade)
                logger.info(f"📝 Paper trade opened: {trade.id}")
        else:
            # LIVE торговля
            if signal.direction == "LONG":
                resp = await self.bybit.market_buy(signal.symbol, quote_qty=value)
                if resp.get('retCode') == 0:
                    trade = await trade_manager.open_trade(signal, value)
                    if trade:
                        await telegram_bot.notify_trade_opened(trade)
                        logger.info(f"✅ Live trade opened: {trade.id}")
                else:
                    logger.error(f"❌ Order failed: {resp}")
                    await telegram_bot.notify_error(f"Order failed: {resp.get('retMsg')}")
            else:
                logger.warning(f"⚠️ SHORT on spot not supported for {signal.symbol}")
    
    def get_status(self) -> dict:
        """Статус"""
        return {
            'running': self.running,
            'check_count': self.check_count,
            'ai_enabled': self.ai_enabled,
            'market_mode': self.market_context.get('market_mode', 'UNKNOWN'),
            'active_trades': len(trade_manager.get_active_trades()),
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'paper_trading': self.paper_trading,
            'symbols': self.symbols,
        }


# Глобальный экземпляр
market_monitor = MarketMonitor()
