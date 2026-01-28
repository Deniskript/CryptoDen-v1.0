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
from app.ai.master_strategist import master_strategist
from app.modules.grid_bot import grid_bot
from app.modules.funding_scalper import funding_scalper
from app.modules.arbitrage import arbitrage_scanner
from app.modules.listing_hunter import listing_hunter
from app.core.live_updates import live_updates, UpdateType
from app.core.smart_notifications import smart_notifications, ModuleType


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
        
        # Режимы модулей (signal/auto)
        self.module_settings: Dict[str, dict] = {
            'director': {'enabled': True, 'mode': 'signal'},
            'grid': {'enabled': True, 'mode': 'signal'},
            'funding': {'enabled': True, 'mode': 'signal'},
            'arbitrage': {'enabled': False, 'mode': 'signal'},
            'listing': {'enabled': True, 'mode': 'signal'},
            'worker': {'enabled': True, 'mode': 'signal'},
        }
        
        # API статус
        self.has_api_keys: bool = False
        self.bybit_testnet: bool = True
        
        # Клиенты
        self.bybit = BybitClient(testnet=False)
        self.data_loader = BybitDataLoader()
        
        logger.info("MarketMonitor initialized with AI")
        
        # Обновляем статус при инициализации
        self._update_status_file()
    
    def get_module_mode(self, module_name: str) -> str:
        """Получить режим модуля: 'signal' или 'auto'"""
        config = self.module_settings.get(module_name, {})
        if not config.get('enabled', False):
            return 'disabled'
        return config.get('mode', 'signal')
    
    def is_module_enabled(self, module_name: str) -> bool:
        """Проверить включён ли модуль"""
        config = self.module_settings.get(module_name, {})
        return config.get('enabled', False)
    
    def can_auto_trade(self, module_name: str) -> bool:
        """Может ли модуль торговать автоматически"""
        if not self.has_api_keys:
            return False
        return self.get_module_mode(module_name) == 'auto'
    
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
        
        # Включаем live updates
        live_updates.enabled = True
        
        # Отправляем сообщение о запуске
        mode = "Сигналы" if not self.has_api_keys else "Авто"
        startup_msg = await live_updates.generate_startup_message(
            coins_count=len(self.symbols),
            mode=mode
        )
        await live_updates.send_update(startup_msg)
        
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
        
        # Выключаем live updates
        live_updates.enabled = False
        
        # НЕ отправляем сообщение здесь - telegram_bot сам отправит статус
        logger.info("🛑 Monitor stopped")
    
    async def _main_cycle(self):
        """Главный цикл"""
        
        self.last_check = datetime.now(timezone.utc)
        self.check_count += 1
        
        # Увеличиваем счётчик циклов для live updates
        live_updates.stats['cycles'] += 1
        
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
        
        # 7. Отправляем живые обновления
        try:
            indicators = {
                "BTC_rsi": await self._get_rsi("BTC"),
                "ETH_rsi": await self._get_rsi("ETH"),
                "SOL_rsi": await self._get_rsi("SOL"),
                "fear_greed": whale_ai.last_metrics.fear_greed_index if whale_ai.last_metrics else 50,
                "funding_rates": await self._get_funding_rates(),
                "minutes_to_funding": self._get_minutes_to_funding(),
                "price_changes_1h": await self._get_price_changes(),
            }
            await self._send_live_updates(prices, indicators)
            
            # Обрабатываем новости с объяснениями
            news_list = self.market_context.get("news", [])
            await self._process_news_with_explanation(news_list)
        except Exception as e:
            logger.error(f"Live updates cycle error: {e}")
        
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
        
        ЛОГИКА:
        1. Master Strategist анализирует рынок (каждые 30 мин)
        2. Director проверяет нужен ли TAKE_CONTROL (события)
        3. Если да - Director торгует, Worker отдыхает
        4. Если нет - Worker ищет сигналы по стратегиям
        """
        
        # ========================================
        # 🐋 ШАГ 0.1: Собираем данные для AI
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
        
        # ========================================
        # 👑 ШАГ 0.2: Master Strategist (каждые 30 мин)
        # ========================================
        master_grid_settings = {"enabled": True, "mode": "balanced"}
        master_funding_settings = {"enabled": True}
        master_technical_settings = {"enabled": True}
        
        if master_strategist.should_analyze():
            try:
                market_data = {
                    "prices": prices,
                    "whale_metrics": whale_metrics,
                    "news": self.market_context.get("news", []),
                }
                
                strategy = await master_strategist.analyze_market(market_data)
                
                # Уведомить в Telegram
                notification = master_strategist.format_notification()
                if notification:
                    await smart_notifications.queue_message(
                        module=ModuleType.DIRECTOR,
                        text=notification,
                        priority=2,
                        need_ai=False  # Уже AI анализ
                    )
                
                logger.info(f"👑 Master: {strategy.market_condition}, Grid: {strategy.grid.mode}, confidence: {strategy.confidence}%")
                
            except Exception as e:
                logger.error(f"👑 Master Strategist error: {e}")
        
        # Получаем настройки от Master
        master_grid_settings = master_strategist.get_module_settings("grid")
        master_funding_settings = master_strategist.get_module_settings("funding")
        master_technical_settings = master_strategist.get_module_settings("technical")
        
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
        # 🎩 ШАГ 1: Director AI
        # ========================================
        director_took_control = False
        
        if self.is_module_enabled('director') and not director_trader.is_controlling:
            try:
                should_take, direction, reason = await director_trader.should_take_control(
                    whale_metrics=whale_metrics,
                    news_context=news_context,
                    market_data={"prices": prices}
                )
                
                if should_take:
                    director_took_control = True
                    
                    if self.can_auto_trade('director'):
                        # AUTO режим — Director торгует сам
                        logger.warning(f"🎩 Director AUTO: {direction} - {reason}")
                        
                        # Выбираем лучший символ
                        best_symbol = "BTC"
                        
                        # Рассчитываем размер (20% для Director)
                        trade_size = self.current_balance * 0.20
                        
                        trade = await director_trader.execute_trade(
                            symbol=best_symbol,
                            direction=direction,
                            reason=reason,
                            size_usd=trade_size
                        )
                        
                        if trade:
                            logger.info(f"🎩 Director opened {best_symbol} {direction} ${trade_size:.0f}")
                            await self._notify_director_executed(trade, reason)
                            return  # Director управляет
                    else:
                        # SIGNAL режим — только уведомление
                        logger.info(f"🎩 Director SIGNAL: {direction} - {reason}")
                        await self._notify_director_signal(direction, reason)
                    
            except Exception as e:
                logger.error(f"Director AI error: {e}")
        
        # ========================================
        # 🎩 ШАГ 2: Если Director управляет - ждём
        # ========================================
        if director_trader.is_controlling:
            active = len(director_trader.active_trades)
            logger.debug(f"🎩 Director controlling ({active} trades), Worker waiting...")
            return
        
        # ========================================
        # 📊 ШАГ 3: Grid Bot (с учётом Master Strategist)
        # ========================================
        grid_enabled_by_master = master_grid_settings.get("enabled", True)
        grid_mode_by_master = master_grid_settings.get("mode", "balanced")
        
        if self.is_module_enabled('grid') and grid_enabled_by_master:
            try:
                # Применяем режим от Master
                grid_config = master_strategist.get_grid_config()
                
                # Устанавливаем режим торговли Grid Bot
                # Real trading только если:
                # - Модуль в AUTO режиме
                # - Есть API ключи
                # - Paper trading выключен
                can_real_trade = (
                    self.can_auto_trade('grid') 
                    and self.has_api_keys 
                    and not self.paper_trading
                )
                
                grid_bot.set_trading_mode(
                    paper_trading=not can_real_trade,
                    bybit_client=self.bybit if can_real_trade else None
                )
                
                if grid_config.get("enabled", True):
                    grid_signals = await grid_bot.get_signals({"prices": prices})
                    
                    for signal in grid_signals:
                        if self.can_auto_trade('grid'):
                            # AUTO режим — исполняем сделку
                            mode_str = "REAL" if can_real_trade else "PAPER"
                            logger.info(f"📊 Grid {mode_str} ({grid_mode_by_master}): {signal.direction} {signal.symbol}")
                            await self._execute_grid_trade(signal)
                            await self._notify_grid_executed(signal)
                        else:
                            # SIGNAL режим — только уведомление
                            logger.info(f"📊 Grid SIGNAL ({grid_mode_by_master}): {signal.direction} {signal.symbol}")
                            await self._notify_grid_signal(signal)
                else:
                    logger.debug(f"📊 Grid OFF by Master Strategist")
            except Exception as e:
                logger.error(f"Grid Bot error: {e}")
        elif not grid_enabled_by_master:
            logger.debug(f"📊 Grid disabled by Master Strategist")
        
        # ========================================
        # 💰 ШАГ 3.5: Funding Scalper (с учётом Master Strategist)
        # ========================================
        funding_enabled_by_master = master_funding_settings.get("enabled", True)
        
        if self.is_module_enabled('funding') and funding_enabled_by_master:
            try:
                funding_signals = await funding_scalper.get_signals({"prices": prices})
                
                for signal in funding_signals:
                    if self.can_auto_trade('funding'):
                        # AUTO режим — исполняем сделку
                        logger.info(f"💰 Funding AUTO: {signal.direction} {signal.symbol}")
                        await self._execute_funding_trade(signal)
                        await self._notify_funding_executed(signal)
                    else:
                        # SIGNAL режим — только уведомление
                        logger.info(f"💰 Funding SIGNAL: {signal.direction} {signal.symbol}")
                        await self._notify_funding_signal(signal)
            except Exception as e:
                logger.error(f"Funding Scalper error: {e}")
        elif not funding_enabled_by_master:
            logger.debug(f"💰 Funding disabled by Master Strategist")
        
        # ========================================
        # 🔄 ШАГ 3.7: Arbitrage Scanner
        # ========================================
        if self.is_module_enabled('arbitrage'):
            try:
                arb_signals = await arbitrage_scanner.get_signals({"prices": prices})
                
                for signal in arb_signals:
                    if self.can_auto_trade('arbitrage'):
                        # AUTO режим — исполняем арбитраж
                        logger.info(f"🔄 Arbitrage AUTO: {signal.reason}")
                        await self._execute_arbitrage(signal)
                        await self._notify_arbitrage_executed(signal)
                    else:
                        # SIGNAL режим — только уведомление
                        logger.info(f"🔄 Arbitrage SIGNAL: {signal.reason}")
                        await self._notify_arbitrage_signal(signal)
                    
            except Exception as e:
                logger.error(f"Arbitrage error: {e}")
        
        # ========================================
        # 🆕 ШАГ 3.8: Listing Hunter
        # ========================================
        if self.is_module_enabled('listing'):
            try:
                from app.modules.listing_hunter import ListingType
                
                listing_signals = await listing_hunter.get_signals({"prices": prices})
                
                for signal in listing_signals:
                    # Находим листинг
                    listing = None
                    for l in listing_hunter.history[-10:]:
                        if l.symbol == signal.symbol:
                            listing = l
                            break
                    
                    if not listing:
                        continue
                    
                    # Listing Scalp можно автоматизировать
                    if listing.listing_type == ListingType.LISTING_SCALP:
                        if self.can_auto_trade('listing'):
                            logger.info(f"🆕 Listing AUTO: BUY {signal.symbol}")
                            await self._execute_listing_trade(signal, listing)
                            await self._notify_listing_executed(signal, listing)
                        else:
                            await self._notify_listing_signal(signal, listing)
                    else:
                        # Pre-listing и Launchpad — только сигналы
                        await self._notify_listing_signal(signal, listing)
                    
            except Exception as e:
                logger.error(f"Listing Hunter error: {e}")
        
        # ========================================
        # 👷 ШАГ 4: Worker ищет сигналы по стратегиям
        # ========================================
        if not self.is_module_enabled('worker') or director_took_control:
            return
        
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
                
                # Уведомляем о сигнале через smart_notifications
                await smart_notifications.queue_signal(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    entry=signal.entry_price,
                    tp=signal.take_profit,
                    sl=signal.stop_loss,
                    rsi=signal.indicators.get('rsi', 50),
                    strategy=signal.strategy_name,
                    win_rate=signal.win_rate
                )
                
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
    
    async def _notify_listing(self, signal):
        """🆕 Уведомление о новом листинге"""
        try:
            # Получаем детали листинга
            listing = None
            for l in listing_hunter.history[-10:]:
                if l.symbol == signal.symbol:
                    listing = l
                    break
            
            if not listing:
                return
            
            # Эмодзи и текст по типу
            type_info = {
                "pre_listing": ("📋", "PRE-LISTING", "Листинг анонсирован"),
                "listing_scalp": ("⚡", "SCALP", "Торговля началась!"),
                "launchpad": ("🚀", "LAUNCHPAD", "Новый Launchpad"),
                "perpetual": ("📊", "PERPETUAL", "Фьючерсы добавлены"),
            }
            
            emoji, title, desc = type_info.get(
                listing.listing_type.value, 
                ("🆕", "LISTING", "Новый листинг")
            )
            
            # Формируем текст в зависимости от типа
            if listing.listing_type.value == "pre_listing":
                bybit_status = "✅ Есть на Bybit" if listing.is_on_bybit else "❌ Нет на Bybit"
                
                if listing.is_on_bybit:
                    action_text = "💡 *Действие:* Можно купить на Bybit!"
                else:
                    action_text = """💡 *Действие:* 
├── Купить на другой бирже ДО листинга
├── Или ждать появления на Bybit
└── Ожидаемый рост: +50-200%"""
                
                price_text = f"${listing.current_price:.4f}" if listing.current_price else "N/A"
                date_text = listing.listing_date.strftime('%Y-%m-%d %H:%M UTC') if listing.listing_date else "Скоро"
                
                text = f"""
{emoji} *{title} — НОВЫЙ ЛИСТИНГ!*

🔥 *Монета:* {listing.name} ({listing.symbol})
🏦 *Биржа:* {listing.exchange}
📅 *Дата:* {date_text}

📊 *Статус:* {bybit_status}
💰 *Цена:* {price_text}

{action_text}

🔗 [Подробнее]({listing.url})

⏰ {listing.announced_at.strftime('%H:%M:%S')}
"""
            
            elif listing.listing_type.value == "listing_scalp":
                if listing_hunter.config.mode == "auto":
                    mode_text = "🤖 *Режим:* Авто-торговля активна"
                else:
                    mode_text = """💡 *Стратегия скальпинга:*
├── Купить СЕЙЧАС
├── TP: +20%
├── SL: -5%
└── Время: 5-30 минут"""
                
                text = f"""
{emoji} *{title} — ТОРГОВЛЯ НАЧАЛАСЬ!*

🔥 *Монета:* {listing.name} ({listing.symbol})
🏦 *Биржа:* {listing.exchange}

⚡ *Статус:* МОЖНО ТОРГОВАТЬ!

{mode_text}

⚠️ *Риск:* HIGH
🎯 *Потенциал:* +10-50%

🔗 [Торговать]({listing.url})

⏰ {listing.announced_at.strftime('%H:%M:%S')}
"""
            
            elif listing.listing_type.value == "launchpad":
                text = f"""
{emoji} *{title} — НОВЫЙ LAUNCHPAD!*

🔥 *Проект:* {listing.name} ({listing.symbol})
🏦 *Платформа:* {listing.exchange}

📋 *Как участвовать:*
├── 1. Зайдите на {listing.exchange}
├── 2. Найдите раздел Launchpad/Launchpool
├── 3. Застейкайте требуемые токены
└── 4. Получите {listing.symbol} бесплатно!

⚠️ *Важно:* Действуйте быстро, места ограничены!

🔗 [Участвовать]({listing.url})

⏰ {listing.announced_at.strftime('%H:%M:%S')}
"""
            
            else:
                text = f"""
{emoji} *{title}*

🔥 *Монета:* {listing.name} ({listing.symbol})
🏦 *Биржа:* {listing.exchange}

📊 {desc}

🔗 [Подробнее]({listing.url})

⏰ {listing.announced_at.strftime('%H:%M:%S')}
"""
            
            await telegram_bot.send_message(text)
            
        except Exception as e:
            logger.error(f"Listing notification error: {e}")
    
    # ==========================================
    # 📢 УВЕДОМЛЕНИЯ SIGNAL MODE
    # ==========================================
    
    async def _notify_grid_signal(self, signal):
        """📊 Grid Bot — рекомендация (signal mode)"""
        try:
            is_buy = signal.direction == "BUY"
            emoji = "🟢" if is_buy else "🔴"
            action = "КУПИТЬ" if is_buy else "ПРОДАТЬ"
            
            # Расчёт цели
            target_pct = 0.3  # Grid step
            if is_buy:
                target = signal.entry_price * (1 + target_pct / 100)
            else:
                target = signal.entry_price * (1 - target_pct / 100)
            
            text = f"""
📊 *GRID BOT — СИГНАЛ*

{emoji} Рекомендация: *{action} {signal.symbol}*

━━━━━━━━━━━━━━━━━━━━
💰 Цена: ${signal.entry_price:,.2f}
🎯 Цель: ${target:,.2f} ({'+' if is_buy else '-'}{target_pct}%)
━━━━━━━━━━━━━━━━━━━━

💡 _Сетка показывает хорошую точку._
_Рекомендуем {'купить' if is_buy else 'продать'} вручную._

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Grid signal notification error: {e}")
    
    async def _notify_grid_executed(self, signal):
        """📊 Grid Bot — выполнено (auto mode)"""
        try:
            is_buy = signal.direction == "BUY"
            emoji = "🟢" if is_buy else "🔴"
            action = "КУПИЛ" if is_buy else "ПРОДАЛ"
            
            status = await grid_bot.get_status()
            
            text = f"""
📊 *GRID BOT — СДЕЛКА*

{emoji} *{action}* {signal.symbol}

━━━━━━━━━━━━━━━━━━━━
💰 Цена: ${signal.entry_price:,.2f}
━━━━━━━━━━━━━━━━━━━━

📈 Сегодня: {status.get('today_trades', 0)} сделок
💰 Профит: ${status.get('today_profit_usdt', 0):.2f}

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Grid executed notification error: {e}")
    
    async def _notify_funding_signal(self, signal):
        """💰 Funding Scalper — рекомендация (signal mode)"""
        try:
            dir_emoji = "🟢" if signal.direction == "LONG" else "🔴"
            
            status = await funding_scalper.get_status()
            minutes_to = status.get("minutes_to_funding", 0)
            
            # Funding rate
            funding_rate = 0
            for rate_info in status.get("top_funding_rates", []):
                if signal.symbol in rate_info.get("symbol", ""):
                    funding_rate = rate_info.get("rate", 0)
                    break
            
            explain = ""
            if signal.direction == "LONG":
                explain = f"📉 Funding {funding_rate:+.3f}% (отриц.)\n_Шорты платят лонгам_"
            else:
                explain = f"📈 Funding {funding_rate:+.3f}% (полож.)\n_Лонги платят шортам_"
            
            text = f"""
💰 *FUNDING — СИГНАЛ*

{dir_emoji} Рекомендация: *{signal.direction} {signal.symbol}*

━━━━━━━━━━━━━━━━━━━━
💰 Вход: ${signal.entry_price:,.2f}
🎯 TP: ${signal.take_profit:,.2f}
🛑 SL: ${signal.stop_loss:,.2f}
━━━━━━━━━━━━━━━━━━━━

{explain}

⏰ До Funding: *{minutes_to} мин*

💡 _Откройте позицию вручную_
_и заработайте на Funding Rate_

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Funding signal notification error: {e}")
    
    async def _notify_funding_executed(self, signal):
        """💰 Funding Scalper — выполнено (auto mode)"""
        try:
            dir_emoji = "🟢" if signal.direction == "LONG" else "🔴"
            
            text = f"""
💰 *FUNDING — ПОЗИЦИЯ ОТКРЫТА*

{dir_emoji} *{signal.direction} {signal.symbol}*

━━━━━━━━━━━━━━━━━━━━
💰 Вход: ${signal.entry_price:,.2f}
🎯 TP: ${signal.take_profit:,.2f}
🛑 SL: ${signal.stop_loss:,.2f}
━━━━━━━━━━━━━━━━━━━━

✅ _Позиция открыта автоматически_
_Ожидаем Funding payment_

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Funding executed notification error: {e}")
    
    async def _notify_arbitrage_signal(self, signal):
        """🔄 Arbitrage — возможность (signal mode)"""
        try:
            text = f"""
🔄 *ARBITRAGE — ВОЗМОЖНОСТЬ*

✨ Найден прибыльный цикл!

━━━━━━━━━━━━━━━━━━━━
📊 {signal.reason}
━━━━━━━━━━━━━━━━━━━━

⚠️ _Требуется быстрое исполнение!_
_Для авто-режима включите 🤖 Auto_

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Arbitrage signal notification error: {e}")
    
    async def _notify_arbitrage_executed(self, signal):
        """🔄 Arbitrage — выполнено (auto mode)"""
        try:
            text = f"""
🔄 *ARBITRAGE — ЦИКЛ ВЫПОЛНЕН*

✅ {signal.reason}

💰 _Профит зачислен на баланс_

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Arbitrage executed notification error: {e}")
    
    async def _notify_listing_signal(self, signal, listing):
        """Отправить информацию о листинге через live_updates"""
        try:
            # Определяем риск/потенциал
            risk_score = 3  # По умолчанию средний
            potential = "+30-80%"
            
            # Анализируем листинг
            if listing.exchange == "Binance":
                risk_score = 4
                potential = "+50-150%"
            elif listing.exchange == "Bybit":
                risk_score = 3
                potential = "+30-100%"
            
            from app.modules.listing_hunter import ListingType
            is_tradeable = listing.listing_type == ListingType.LISTING_SCALP
            
            update = await live_updates.generate_listing(
                name=listing.name,
                symbol=listing.symbol,
                exchange=listing.exchange,
                is_tradeable=is_tradeable,
                risk_score=risk_score,
                potential=potential
            )
            
            if update:
                await live_updates.send_update(update)
                
        except Exception as e:
            logger.error(f"Listing notification error: {e}")
    
    async def _notify_listing_executed(self, signal, listing):
        """🆕 Listing — куплено (auto mode)"""
        try:
            text = f"""
🆕 *ЛИСТИНГ — КУПЛЕНО*

✅ *{listing.symbol}* куплен автоматически!

━━━━━━━━━━━━━━━━━━━━
💰 Цена: ${signal.entry_price:,.4f}
🎯 TP: +20%
🛑 SL: -5%
━━━━━━━━━━━━━━━━━━━━

⏳ _Ожидаем рост..._

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Listing executed notification error: {e}")
    
    async def _notify_worker_signal(self, signal):
        """👷 Worker — рекомендация (signal mode)"""
        try:
            dir_emoji = "🟢" if signal.direction == "LONG" else "🔴"
            
            tp_pct = abs((signal.take_profit - signal.entry_price) / signal.entry_price * 100)
            sl_pct = abs((signal.stop_loss - signal.entry_price) / signal.entry_price * 100)
            
            text = f"""
👷 *RSI STRATEGY — СИГНАЛ*

{dir_emoji} Рекомендация: *{signal.direction} {signal.symbol}*

━━━━━━━━━━━━━━━━━━━━
💰 Вход: ${signal.entry_price:,.2f}
🎯 TP: ${signal.take_profit:,.2f} (+{tp_pct:.1f}%)
🛑 SL: ${signal.stop_loss:,.2f} (-{sl_pct:.1f}%)
━━━━━━━━━━━━━━━━━━━━

📊 Стратегия: {signal.strategy_name if hasattr(signal, 'strategy_name') else 'RSI + EMA'}
🎯 Win Rate: {signal.win_rate:.1f}%

💡 _Откройте позицию вручную_

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Worker signal notification error: {e}")
    
    async def _notify_director_signal(self, direction: str, reason: str):
        """🎩 Director — рекомендация (signal mode)"""
        try:
            dir_emoji = "🟢" if direction == "LONG" else "🔴"
            
            text = f"""
🎩 *DIRECTOR AI — СИГНАЛ*

{dir_emoji} Рекомендация: *{direction} BTC*

━━━━━━━━━━━━━━━━━━━━
📊 *Причина:*
{reason}
━━━━━━━━━━━━━━━━━━━━

💡 _Director видит сильную возможность!_
_Рекомендуем открыть позицию вручную_

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Director signal notification error: {e}")
    
    async def _notify_director_executed(self, trade, reason: str):
        """🎩 Director — выполнено (auto mode)"""
        try:
            dir_emoji = "🟢" if trade.direction == "LONG" else "🔴"
            
            tp_pct = abs((trade.take_profit - trade.entry_price) / trade.entry_price * 100)
            sl_pct = abs((trade.stop_loss - trade.entry_price) / trade.entry_price * 100)
            
            text = f"""
🎩 *DIRECTOR — СДЕЛКА ОТКРЫТА*

{dir_emoji} *{trade.direction} {trade.symbol}*

━━━━━━━━━━━━━━━━━━━━
💰 Вход: ${trade.entry_price:,.2f}
🎯 TP: ${trade.take_profit:,.2f} (+{tp_pct:.1f}%)
🛑 SL: ${trade.stop_loss:,.2f} (-{sl_pct:.1f}%)
━━━━━━━━━━━━━━━━━━━━

📊 *Причина:*
{reason}

✅ _Director взял управление_

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Director executed notification error: {e}")
    
    def _get_time(self) -> str:
        """Текущее время"""
        return datetime.now().strftime('%H:%M:%S')
    
    # ==========================================
    # 🤖 ИСПОЛНЕНИЕ AUTO MODE
    # ==========================================
    
    async def _execute_grid_trade(self, signal):
        """Исполнить Grid сделку (auto mode)"""
        # Grid Bot уже исполняет внутри, просто логируем
        logger.info(f"📊 Grid trade executed: {signal.direction} {signal.symbol}")
    
    async def _execute_funding_trade(self, signal):
        """Исполнить Funding сделку (auto mode)"""
        # Здесь будет реальное исполнение через Bybit API
        logger.info(f"💰 Funding trade executed: {signal.direction} {signal.symbol}")
    
    async def _execute_arbitrage(self, signal):
        """Исполнить арбитраж (auto mode)"""
        # Arbitrage уже исполняет внутри
        logger.info(f"🔄 Arbitrage executed: {signal.reason}")
    
    async def _execute_listing_trade(self, signal, listing):
        """Исполнить Listing сделку (auto mode)"""
        logger.info(f"🆕 Listing trade executed: {listing.symbol}")
    
    # ==========================================
    # 📢 LIVE UPDATES
    # ==========================================
    
    async def _send_live_updates(self, prices: Dict, indicators: Dict):
        """Отправить живые обновления через smart_notifications"""
        if not smart_notifications.enabled:
            return
        
        try:
            btc_price = prices.get("BTC", 0)
            btc_rsi = indicators.get("BTC_rsi", 50)
            fear_greed = indicators.get("fear_greed", 50)
            
            # Director status - создаём snapshot с реальными данными
            from app.core.market_data_provider import MarketSnapshot
            snapshot = MarketSnapshot(
                btc_price=btc_price,
                btc_rsi=btc_rsi,
                fear_greed=fear_greed,
                eth_price=prices.get("ETH", 0),
                sol_price=prices.get("SOL", 0),
            )
            await smart_notifications.queue_director_status(
                snapshot=snapshot,
                has_signal=False
            )
            
            # Grid status
            if btc_price > 0:
                support = btc_price * 0.995
                resistance = btc_price * 1.005
                await smart_notifications.queue_grid_status(
                    symbol="BTC",
                    price=btc_price,
                    support=support,
                    resistance=resistance
                )
            
            # Funding status
            funding_rates = indicators.get("funding_rates", {})
            minutes_to = indicators.get("minutes_to_funding", 60)
            if funding_rates:
                await smart_notifications.queue_funding_status(
                    rates=funding_rates,
                    minutes_to_funding=minutes_to
                )
            
        except Exception as e:
            logger.error(f"Live updates error: {e}")
    
    def _get_no_entry_reason(self, rsi: float, fear_greed: int) -> str:
        """Сформировать причину почему не входим"""
        reasons = []
        
        if 40 <= rsi <= 60:
            reasons.append(f"• RSI в нейтральной зоне ({rsi:.0f})")
        elif rsi > 60:
            reasons.append(f"• RSI высоковат ({rsi:.0f}), жду откат")
        else:
            reasons.append(f"• RSI пока не достиг зоны покупки ({rsi:.0f})")
        
        if 40 <= fear_greed <= 60:
            reasons.append(f"• Fear & Greed нейтральный ({fear_greed})")
        elif fear_greed > 70:
            reasons.append(f"• Много жадности ({fear_greed}), опасно входить")
        
        if not reasons:
            reasons.append("• Жду более чёткий сигнал")
        
        return "\n".join(reasons)
    
    async def _get_rsi(self, symbol: str) -> float:
        """Получить RSI для символа"""
        try:
            from app.strategies.indicators import TechnicalIndicators
            
            df = self.data_loader.load_from_cache(symbol, '5m')
            
            if df is None or len(df) < 20:
                return 50
            
            ind = TechnicalIndicators()
            return ind.rsi(df['close'].tail(50), 14)
        except:
            return 50
    
    async def _get_funding_rates(self) -> Dict[str, float]:
        """Получить funding rates"""
        try:
            status = await funding_scalper.get_status()
            rates = {}
            for item in status.get("top_funding_rates", []):
                symbol = item.get("symbol", "").replace("USDT", "")
                rates[symbol] = item.get("rate", 0)
            return rates
        except:
            return {}
    
    def _get_minutes_to_funding(self) -> int:
        """Минут до следующего funding"""
        now = datetime.utcnow()
        # Funding в 00:00, 08:00, 16:00 UTC
        funding_hours = [0, 8, 16]
        
        for h in funding_hours:
            if now.hour < h:
                return (h - now.hour) * 60 - now.minute
        
        # Следующий в 00:00
        return (24 - now.hour) * 60 - now.minute
    
    async def _get_price_changes(self) -> Dict[str, float]:
        """Получить изменения цен за час"""
        try:
            changes = {}
            
            for symbol in ["BTC", "ETH", "SOL"]:
                df = self.data_loader.load_from_cache(symbol, '1h')
                if df is not None and len(df) >= 2:
                    current = df['close'].iloc[-1]
                    prev = df['close'].iloc[-2]
                    changes[symbol] = ((current - prev) / prev) * 100
            
            return changes
        except:
            return {}
    
    async def _process_news_with_explanation(self, news_list: List[Dict]):
        """Обработать новости и отправить через smart_notifications"""
        if not news_list:
            return
        
        # Отправляем через smart_notifications
        for news in news_list[:2]:  # Макс 2 новости за раз
            importance = news.get('importance', 'LOW')
            if importance not in ['HIGH', 'MEDIUM']:
                continue
            
            title = news.get('title', '')
            source = news.get('source', 'Unknown')
            sentiment = news.get('sentiment', 0)
            
            await smart_notifications.queue_news(
                title=title,
                source=source,
                sentiment=sentiment,
                importance=importance
            )
    
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
