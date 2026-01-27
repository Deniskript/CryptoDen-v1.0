"""
Market Monitor — Главный цикл с AI

Правила:
- Размер сделки = 15% от баланса
- Максимум 6 открытых сделок
- Баланс кончился → ждём закрытия → снова торгуем
"""
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.logger import logger

# Файл статуса для WebApp
BOT_STATUS_FILE = "/root/crypto-bot/data/bot_status.json"
from app.strategies import strategy_checker, get_enabled_strategies, Signal
from app.trading import trade_manager, CloseReason
from app.trading.bybit.client import BybitClient
from app.intelligence.news_parser import news_parser
from app.brain import trading_ai, AIAction
from app.notifications import telegram_bot
from app.backtesting.data_loader import BybitDataLoader
from app.ai.trading_coordinator import trading_coordinator, get_director_guidance
from app.ai.director_ai import director_trader
from app.ai.whale_ai import whale_ai
from app.modules.grid_bot import grid_bot
from app.modules.funding_scalper import funding_scalper
from app.modules.arbitrage import arbitrage_scanner


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
        
        # Баланс
        self.current_balance: float = 1000.0  # Начальный для Paper
        self.initial_balance: float = 1000.0
        self.balance_percent_per_trade: float = 0.15  # 15%
        self.max_open_trades: int = 6
        self.min_trade_size: float = 10.0  # Минимум $10
        
        # AI контроль
        self.ai_enabled: bool = True
        self.min_confidence: int = 60  # Минимальная уверенность AI для сделки
        
        # Клиенты
        self.bybit = BybitClient(testnet=False)
        self.data_loader = BybitDataLoader()
        
        logger.info("MarketMonitor initialized with AI")
        
        # Обновляем статус при инициализации
        self._update_status_file()
    
    def _update_status_file(self):
        """Обновить файл статуса для WebApp"""
        try:
            os.makedirs(os.path.dirname(BOT_STATUS_FILE), exist_ok=True)
            
            status = {
                "running": self.running,
                "balance": self.current_balance,
                "active_trades": len(trade_manager.get_active_trades()) if self.running else 0,
                "paper_trading": self.paper_trading,
                "ai_enabled": self.ai_enabled,
                "symbols": self.symbols,
                "last_update": datetime.utcnow().isoformat()
            }
            
            with open(BOT_STATUS_FILE, 'w') as f:
                json.dump(status, f, indent=2)
                
        except Exception as e:
            logger.error(f"Status file update error: {e}")
    
    def get_trade_size(self) -> float:
        """Размер сделки = 15% от баланса"""
        size = self.current_balance * self.balance_percent_per_trade
        return max(0, round(size, 2))
    
    def can_open_new_trade(self) -> tuple[bool, str]:
        """Можно ли открыть новую сделку"""
        active = len(trade_manager.get_active_trades())
        
        if active >= self.max_open_trades:
            return False, f"Лимит сделок ({active}/{self.max_open_trades})"
        
        trade_size = self.get_trade_size()
        if trade_size < self.min_trade_size:
            return False, f"Недостаточно баланса (${self.current_balance:.2f})"
        
        return True, "OK"
    
    async def update_balance_after_close(self, pnl: float):
        """Обновить баланс после закрытия сделки"""
        old_balance = self.current_balance
        self.current_balance += pnl
        
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        logger.info(f"💰 Balance: ${old_balance:.2f} → ${self.current_balance:.2f} ({pnl_emoji} ${pnl:+.2f})")
    
    async def sync_balance_from_exchange(self):
        """Синхронизировать баланс с биржи (для LIVE)"""
        if not self.paper_trading:
            try:
                balance = await self.bybit.get_balance("USDT")
                if balance is not None:
                    self.current_balance = balance
                    logger.info(f"💰 Synced balance from Bybit: ${balance:.2f}")
            except Exception as e:
                logger.error(f"Balance sync error: {e}")
    
    async def start(self):
        """Запустить мониторинг"""
        
        self.running = True
        self._update_status_file()
        
        # Если symbols пустой, берём из стратегий
        if not self.symbols:
            self.symbols = list(get_enabled_strategies().keys())
        
        logger.info("=" * 60)
        logger.info("🚀 MARKET MONITOR STARTED (AI ENABLED)")
        logger.info(f"📊 Symbols: {', '.join(self.symbols)}")
        logger.info(f"🧠 AI: {'ON' if self.ai_enabled else 'OFF'}")
        logger.info(f"📝 Mode: {'PAPER' if self.paper_trading else 'LIVE'}")
        logger.info(f"💰 Balance: ${self.current_balance:.2f}")
        logger.info(f"📦 Trade size: ${self.get_trade_size():.2f} (15%)")
        logger.info(f"📊 Max trades: {self.max_open_trades}")
        logger.info(f"⏱️ Check interval: {self.check_interval}s")
        logger.info("=" * 60)
        
        # Синхронизируем баланс для LIVE
        if not self.paper_trading:
            await self.sync_balance_from_exchange()
        
        # Первоначальная загрузка новостей
        await self._update_news_context()
        
        # НЕ отправляем сообщение здесь - telegram_bot сам отправит статус
        
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
        self._update_status_file()
        
        # НЕ отправляем сообщение здесь - telegram_bot сам отправит статус
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
        closed_trades = await trade_manager.update_prices(prices)
        
        # Обрабатываем закрытые сделки
        if closed_trades:
            for trade in closed_trades:
                await self.update_balance_after_close(trade.unrealized_pnl)
                await telegram_bot.notify_trade_closed(trade)
        
        # 4. Проверяем активные позиции через AI (двигаем SL/TP)
        if self.ai_enabled:
            await self._check_active_positions_with_ai(prices)
        
        # 5. Обновляем Whale AI метрики (каждые 5 циклов = 5 мин)
        if self.check_count % 5 == 0:
            try:
                await whale_ai.get_market_metrics("BTC")
                logger.debug("🐋 Whale AI metrics updated")
            except Exception as e:
                logger.error(f"Whale AI update error: {e}")
        
        # 6. Ищем новые сигналы (Director TAKE_CONTROL)
        await self._check_for_signals(prices)
        
        # Логируем статус
        active = trade_manager.get_active_trades()
        mode = self.market_context.get('market_mode', 'NORMAL')
        
        logger.info(f"📊 Mode: {mode} | Active: {len(active)}/{self.max_open_trades} | Balance: ${self.current_balance:.2f}")
        
        # Обновляем файл статуса для WebApp
        self._update_status_file()
        
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
                    closed = await trade_manager.close_trade(trade.id, CloseReason.MANUAL)
                    if closed:
                        await self.update_balance_after_close(closed.unrealized_pnl)
                        await telegram_bot.notify_trade_closed(closed)
                    
            except Exception as e:
                logger.error(f"AI position check error for {trade.symbol}: {e}")
    
    async def _check_for_signals(self, prices: Dict[str, float]):
        """
        🔍 Поиск торговых сигналов
        
        НОВАЯ ЛОГИКА:
        1. Director проверяет нужен ли TAKE_CONTROL (события)
        2. Если да - Director торгует, Worker отдыхает
        3. Если нет - Worker ищет сигналы по стратегиям
        """
        
        # ========================================
        # 🐋 ШАГ 0: Собираем данные для Director
        # ========================================
        whale_metrics = {}
        if whale_ai.last_metrics:
            m = whale_ai.last_metrics
            whale_metrics = {
                "fear_greed": m.fear_greed_index,
                "long_ratio": m.long_ratio,
                "short_ratio": m.short_ratio,
                "funding_rate": m.funding_rate,
                "oi_change_1h": m.oi_change_1h,
                "oi_change_24h": m.oi_change_24h,
                "liq_long": m.liq_long,
                "liq_short": m.liq_short,
            }
            logger.debug(f"🐋 Whale: F&G={m.fear_greed_index}, L/S={m.long_ratio:.0f}%, Funding={m.funding_rate:+.4f}%")
        
        # Собираем контекст новостей
        news_context = {"sentiment": "neutral", "critical_count": 0}
        news = self.market_context.get("news", [])
        if news:
            bearish = sum(1 for n in news if n.get("sentiment", 0) < -0.2)
            bullish = sum(1 for n in news if n.get("sentiment", 0) > 0.2)
            critical = sum(1 for n in news if n.get("importance") == "HIGH")
            
            if bearish > bullish:
                news_context["sentiment"] = "bearish"
            elif bullish > bearish:
                news_context["sentiment"] = "bullish"
            news_context["critical_count"] = critical
        
        # ========================================
        # 🎩 ШАГ 1: Director проверяет TAKE_CONTROL
        # ========================================
        if not director_trader.is_controlling:
            try:
                should_take, direction, reason = await director_trader.should_take_control(
                    whale_metrics=whale_metrics,
                    news_context=news_context,
                    market_data={"prices": prices}
                )
                
                if should_take:
                    logger.warning(f"🎩 TAKE_CONTROL: {direction} - {reason}")
                    
                    # Выбираем лучший символ для торговли
                    best_symbol = "BTC"
                    if "BTCUSDT" in prices:
                        best_symbol = "BTC"
                    elif "BTC" in prices:
                        best_symbol = "BTC"
                    
                    # Рассчитываем размер позиции (20% для Director - агрессивно!)
                    trade_size = self.current_balance * 0.20
                    
                    # Director открывает сделку!
                    trade = await director_trader.execute_trade(
                        symbol=best_symbol,
                        direction=direction,
                        reason=reason,
                        size_usd=trade_size
                    )
                    
                    if trade:
                        logger.info(f"🎩 Director opened {best_symbol} {direction} ${trade_size:.0f}")
                        await self._notify_director_trade(trade, reason)
                        return  # Director управляет, дальше не идём
                    
            except Exception as e:
                logger.error(f"Director TAKE_CONTROL error: {e}")
        
        # ========================================
        # 🎩 ШАГ 2: Если Director управляет - ждём
        # ========================================
        if director_trader.is_controlling:
            active = len(director_trader.active_trades)
            logger.debug(f"🎩 Director controlling ({active} trades), Worker waiting...")
            return
        
        # ========================================
        # 📊 ШАГ 3: Grid Bot
        # ========================================
        if grid_bot.enabled:
            try:
                grid_signals = await grid_bot.get_signals({"prices": prices})
                
                for signal in grid_signals:
                    logger.info(f"📊 Grid: {signal.direction} {signal.symbol} @ {signal.entry_price:.2f}")
                    
                    # Уведомление в Telegram
                    await self._notify_grid_trade(signal)
                    
            except Exception as e:
                logger.error(f"Grid Bot error: {e}")
        
        # ========================================
        # 💰 ШАГ 3.5: Funding Scalper
        # ========================================
        if funding_scalper.enabled:
            try:
                funding_signals = await funding_scalper.get_signals({"prices": prices})
                
                for signal in funding_signals:
                    logger.info(f"💰 Funding: {signal.direction} {signal.symbol} - {signal.reason}")
                    
                    # Уведомление в Telegram
                    await self._notify_funding_trade(signal)
                    
            except Exception as e:
                logger.error(f"Funding Scalper error: {e}")
        
        # ========================================
        # 🔄 ШАГ 3.7: Arbitrage Scanner
        # ========================================
        if arbitrage_scanner.enabled:
            try:
                arb_signals = await arbitrage_scanner.get_signals({"prices": prices})
                
                for signal in arb_signals:
                    logger.info(f"🔄 Arbitrage: {signal.reason}")
                    
                    # Уведомление в Telegram
                    await self._notify_arbitrage_trade(signal)
                    
            except Exception as e:
                logger.error(f"Arbitrage Scanner error: {e}")
        
        # ========================================
        # 👷 ШАГ 4: Worker ищет сигналы по стратегиям
        # ========================================
        guidance = await get_director_guidance()
        
        decision = guidance.get("decision", "continue")
        risk_level = guidance.get("risk_level", "normal")
        director_size_mult = guidance.get("size_multiplier", 1.0)
        
        # Логируем решение Директора (только если не кэшированное)
        if not guidance.get("cached", True):
            logger.info(f"🎩 Director: {decision} | Risk: {risk_level} | Size: x{director_size_mult}")
            
            # Уведомляем о важных решениях
            if decision not in ["continue"] or risk_level in ["high", "extreme"]:
                await telegram_bot.send_message(
                    f"🎩 *Director Decision*\n\n"
                    f"📊 Risk: {risk_level.upper()}\n"
                    f"🎯 Decision: {decision}\n"
                    f"📦 Size: x{director_size_mult}\n"
                    f"🟢 LONG: {'✅' if guidance.get('allow_longs') else '🚫'}\n"
                    f"🔴 SHORT: {'✅' if guidance.get('allow_shorts') else '🚫'}"
                )
        
        # Проверяем закрытия по команде Director
        if decision in ["close_all", "close_longs", "close_shorts"]:
            close_actions = await trading_coordinator.check_for_close_orders(guidance)
            
            for action in close_actions:
                success = await trading_coordinator.execute_close_action(action)
                if success:
                    await telegram_bot.send_message(
                        f"🎩 *Director Closed Position*\n\n"
                        f"📍 {action.symbol} {action.direction}\n"
                        f"📝 {action.reason}"
                    )
            
            if decision == "close_all":
                return
        
        # Проверяем можно ли открывать новые
        if decision in ["pause_new", "take_control"]:
            logger.debug(f"⏸️ Director: {decision} — Worker paused")
            return
        
        # Базовая проверка лимитов
        can_open, reason = self.can_open_new_trade()
        if not can_open:
            logger.debug(f"⏭️ Skip signals: {reason}")
            return
        
        # ========================================
        # 👷 ШАГ 4: Worker проверяет стратегии
        # ========================================
        for symbol, price in prices.items():
            can_open, reason = self.can_open_new_trade()
            if not can_open:
                break
            
            try:
                # Загружаем данные из кэша
                df = self.data_loader.load_from_cache(symbol, '5m')
                
                if df is None or len(df) < 50:
                    continue
                
                df = df.tail(100).copy()
                
                # Проверяем стратегию
                signal = await strategy_checker.check_symbol(symbol, df, price)
                
                if not signal:
                    continue
                
                logger.info(f"🎯 Worker Signal: {symbol} {signal.direction}")
                trading_coordinator.signals_generated += 1
                
                # Фильтрация через Director
                allowed, filter_reason = await trading_coordinator.filter_signal(signal, guidance)
                
                if not allowed:
                    logger.info(f"⛔ Signal blocked: {filter_reason}")
                    continue
                
                # Уведомляем о сигнале
                await telegram_bot.notify_signal(signal)
                
                # Если AI выключен — торгуем напрямую
                if not self.ai_enabled:
                    trade_size = self.get_trade_size() * director_size_mult
                    await self._execute_signal(signal, trade_size)
                    continue
                
                # AI анализирует
                async with trading_ai:
                    ai_decision = await trading_ai.analyze(
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
                
                # Выполняем решение AI
                if ai_decision.action in [AIAction.OPEN_LONG, AIAction.OPEN_SHORT]:
                    if ai_decision.confidence >= self.min_confidence:
                        if ai_decision.stop_loss:
                            signal.stop_loss = ai_decision.stop_loss
                        if ai_decision.take_profit:
                            signal.take_profit = ai_decision.take_profit
                        
                        trade_size = self.get_trade_size() * ai_decision.size_multiplier * director_size_mult
                        
                        await self._execute_signal(signal, trade_size)
                        trading_coordinator.actions_executed += 1
                        
                        await telegram_bot.send_message(
                            f"🧠 *Worker Trade*\n\n"
                            f"📍 {symbol} {ai_decision.direction}\n"
                            f"📊 Confidence: {ai_decision.confidence}%\n"
                            f"📦 Size: ${trade_size:.0f}\n"
                            f"📝 {ai_decision.reason}"
                        )
                    else:
                        logger.info(f"🧠 AI rejected: {ai_decision.confidence}% < {self.min_confidence}%")
                
                elif ai_decision.action == AIAction.WAIT:
                    logger.debug(f"🧠 AI says WAIT: {ai_decision.reason}")
                    
            except Exception as e:
                logger.error(f"Signal check error for {symbol}: {e}")
    
    async def _notify_director_trade(self, trade, reason: str):
        """🎩 Уведомление о сделке Director"""
        try:
            emoji = "🟢" if trade.direction == "LONG" else "🔴"
            
            text = f"""
🎩 *DIRECTOR TAKE_CONTROL*

{emoji} *{trade.direction}* {trade.symbol}

💰 *Вход:* ${trade.entry_price:,.2f}
🎯 *TP:* ${trade.take_profit:,.2f} (+{((trade.take_profit/trade.entry_price)-1)*100:.1f}%)
🛑 *SL:* ${trade.stop_loss:,.2f} ({((trade.stop_loss/trade.entry_price)-1)*100:.1f}%)

📊 *Причина:* {reason}

⏰ {trade.opened_at.strftime('%H:%M:%S')}
"""
            await telegram_bot.send_message(text)
            
        except Exception as e:
            logger.error(f"Director notification error: {e}")
    
    async def _notify_grid_trade(self, signal):
        """📊 Уведомление о сделке Grid Bot"""
        try:
            emoji = "🟢" if signal.direction == "BUY" else "🔴"
            
            # Получаем статистику
            status = await grid_bot.get_status()
            
            text = f"""
📊 *GRID BOT*

{emoji} *{signal.direction}* {signal.symbol} @ ${signal.entry_price:,.2f}

📈 *Сегодня:* {status['today_trades']} сделок | ${status['today_profit_usdt']:.2f}
📊 *Всего:* {status['total_trades']} сделок | ${status['total_profit_usdt']:.2f}

⏰ {signal.timestamp.strftime('%H:%M:%S')}
"""
            await telegram_bot.send_message(text)
            
        except Exception as e:
            logger.error(f"Grid notification error: {e}")
    
    async def _notify_funding_trade(self, signal):
        """💰 Уведомление о сделке Funding Scalper"""
        try:
            is_close = signal.direction.startswith("CLOSE")
            
            if is_close:
                emoji = "✅" if "+" in signal.reason else "❌"
                text = f"""
💰 *FUNDING SCALPER — ЗАКРЫТИЕ*

{emoji} {signal.symbol}
📊 {signal.reason}

⏰ {signal.timestamp.strftime('%H:%M:%S')}
"""
            else:
                emoji = "🟢" if signal.direction == "LONG" else "🔴"
                
                # Получаем статус
                status = await funding_scalper.get_status()
                minutes_to = status.get("minutes_to_funding", 0)
                
                text = f"""
💰 *FUNDING SCALPER — ВХОД*

{emoji} *{signal.direction}* {signal.symbol}

💵 *Вход:* ${signal.entry_price:,.2f}
🎯 *TP:* ${signal.take_profit:,.2f}
🛑 *SL:* ${signal.stop_loss:,.2f}

📊 *Причина:* {signal.reason}
⏰ *До Funding:* {minutes_to} мин

⏰ {signal.timestamp.strftime('%H:%M:%S')}
"""
            await telegram_bot.send_message(text)
            
        except Exception as e:
            logger.error(f"Funding notification error: {e}")
    
    async def _notify_arbitrage_trade(self, signal):
        """🔄 Уведомление об арбитраже"""
        try:
            # Получаем статус
            status = await arbitrage_scanner.get_status()
            
            text = f"""
🔄 *ARBITRAGE EXECUTED*

💰 {signal.reason}

📊 *Статистика:*
├── Сделок сегодня: {status['stats']['today_trades']}
└── Профит сегодня: ${status['stats']['today_profit_usdt']:.2f}

⏰ {signal.timestamp.strftime('%H:%M:%S')}
"""
            await telegram_bot.send_message(text)
            
        except Exception as e:
            logger.error(f"Arbitrage notification error: {e}")
    
    async def _execute_signal(self, signal: Signal, value: float = None):
        """Выполнить сигнал — открыть сделку"""
        
        # Размер = 15% от баланса если не указан
        value = value or self.get_trade_size()
        
        # Финальная проверка
        can_open, reason = self.can_open_new_trade()
        if not can_open:
            logger.info(f"⏭️ Skip {signal.symbol}: {reason}")
            return
        
        # Проверяем есть ли уже позиция по этому символу
        existing = [t for t in trade_manager.get_active_trades() if t.symbol == signal.symbol]
        if existing:
            logger.info(f"⏭️ Skip {signal.symbol}: уже есть позиция")
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
            'max_trades': self.max_open_trades,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'paper_trading': self.paper_trading,
            'symbols': self.symbols,
            'balance': self.current_balance,
            'trade_size': self.get_trade_size(),
        }


# Глобальный экземпляр
market_monitor = MarketMonitor()
