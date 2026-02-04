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
from app.brain import trading_ai
from app.brain.trading_ai import AIAction
from app.notifications import telegram_bot
from app.backtesting.data_loader import BybitDataLoader
from app.ai.trading_coordinator import trading_coordinator, get_director_guidance
from app.ai.director_ai import director_trader
from app.ai.whale_ai import whale_ai
from app.ai.master_strategist import master_strategist
from app.ai.director_brain import director_brain
from app.modules.grid_bot import grid_bot
from app.modules.funding_scalper import funding_scalper
from app.modules.arbitrage import arbitrage_scanner
from app.modules.listing_hunter import listing_hunter
from app.core.live_updates import live_updates, UpdateType
from app.core.smart_notifications import smart_notifications
from app.core.trade_tracker import trade_tracker
from app.core.session_tracker import session_tracker


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
        
        # Отслеживание отправленных уведомлений (чтобы не спамить)
        self.notified_listings: set = set()  # {symbol_exchange}
        self.notified_grid_signals: set = set()  # {symbol_direction_price}
        
        # Антиспам для DirectorBrain сигналов
        # {"BTC_LONG": {"time": datetime, "price": 81200, "confidence": 73}}
        self._brain_signals_cache: Dict[str, dict] = {}
        
        # Периодические статусы трекера
        self._last_tracker_status: Optional[datetime] = None
        self._tracker_status_interval: int = 3600  # каждый час
        
        # Антиспам для Director AI
        self._last_director_decision: Optional[str] = None
        self._last_director_time: Optional[datetime] = None
        self._director_spam_interval: int = 1800  # 30 минут
        
        # Антиспам для листингов
        self._listing_cooldowns: Dict[str, datetime] = {}  # {symbol: last_sent_time}
        self._listings_sent_this_batch: int = 0
        self._max_listings_per_batch: int = 2
        self._listing_cooldown_minutes: int = 60  # 1 час между одинаковыми листингами
        
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
    
    def should_send_brain_signal(self, symbol: str, direction: str, entry_price: float, confidence: int) -> bool:
        """
        Антиспам для DirectorBrain сигналов
        Не отправлять если:
        1. Такой же сигнал был за последние 30 минут
        2. Цена изменилась менее чем на 1%
        """
        cache_key = f"{symbol}_{direction}"
        now = datetime.now()
        
        if cache_key in self._brain_signals_cache:
            cached = self._brain_signals_cache[cache_key]
            cached_time = cached["time"]
            cached_price = cached["price"]
            
            # Не прошло 30 минут
            if now - cached_time < timedelta(minutes=30):
                # Цена изменилась менее чем на 1%
                if cached_price > 0:
                    price_change = abs(entry_price - cached_price) / cached_price * 100
                    if price_change < 1.0:
                        logger.debug(f"⏭️ Brain signal skipped (duplicate): {direction} {symbol} "
                                   f"(price change {price_change:.2f}% < 1%)")
                        return False
        
        # Сохранить в кэш
        self._brain_signals_cache[cache_key] = {
            "time": now,
            "price": entry_price,
            "confidence": confidence
        }
        
        # Очистка старых записей
        self._cleanup_brain_signals_cache()
        
        return True
    
    def _cleanup_brain_signals_cache(self):
        """Удалить записи старше 1 часа"""
        now = datetime.now()
        expired = []
        for key, data in self._brain_signals_cache.items():
            if now - data["time"] > timedelta(hours=1):
                expired.append(key)
        for key in expired:
            del self._brain_signals_cache[key]
    
    def _check_director_allows(self, direction: str) -> bool:
        """
        Проверить разрешает ли Director AI открывать позицию в этом направлении
        ПРОБЛЕМА 2 FIX: DirectorBrain НЕ должен открывать если Director AI запретил
        """
        try:
            from app.ai.director_ai import get_director_state
            state = get_director_state()
            
            if direction == "LONG" and not state.get("allow_long", True):
                reason = state.get("reason", "Director AI блокирует LONG")
                logger.warning(f"⛔ DirectorBrain LONG blocked by Director AI: {reason}")
                return False
            
            if direction == "SHORT" and not state.get("allow_short", True):
                reason = state.get("reason", "Director AI блокирует SHORT")
                logger.warning(f"⛔ DirectorBrain SHORT blocked by Director AI: {reason}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Director state check error: {e}")
            return True  # При ошибке разрешаем
    
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
        
        # Начинаем новый сеанс
        session_tracker.start_session()
        
        # Включаем live updates
        live_updates.enabled = True
        
        # НЕ отправляем сообщение здесь - smart_notifications.send_startup_sequence отправит ОДНО сообщение
        
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
        
        # Запуск Momentum Detector
        try:
            from app.brain.momentum_detector import momentum_detector
            all_coins = list(set(self.symbols + ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']))
            asyncio.create_task(momentum_detector.start(all_coins))
            logger.info(f"⚡ Momentum Detector started for {len(all_coins)} coins")
        except Exception as e:
            logger.error(f"Failed to start Momentum Detector: {e}")
        
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
        
        # Завершаем текущий сеанс
        closed_session = session_tracker.end_session()
        if closed_session:
            logger.info(f"📊 Session ended: {closed_session.signals_count} signals, "
                       f"PnL: {closed_session.total_pnl_percent:+.2f}%")
        
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
        
        # 3.5. Обновляем TradeTracker (сигнальные сделки)
        tracker_actions = trade_tracker.update_all_trades(prices)
        for action in tracker_actions:
            await self._handle_tracker_action(action)
        
        # 3.6. Периодический статус трекера (каждый час)
        await self._send_tracker_status_if_needed()
        
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
            # УБРАНО: Спам каждую минуту
            # await self._send_live_updates(prices, indicators)
            
            # УБРАНО: Спам новостей
            # news_list = self.market_context.get("news", [])
            # await self._process_news_with_explanation(news_list)
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
        🧠 Adaptive Brain v3.0 — Unified Trading Logic
        
        НОВАЯ ЛОГИКА:
        1. Listing Hunter — проверка новых листингов
        2. Adaptive Brain — единый мозг принимает решения
        3. Momentum Detector — работает параллельно (запускается в start())
        
        Заменяет: Master Strategist, Director AI, Director Brain, Worker
        """
        
        # ═══════════════════════════════════════════════════════════
        # 🆕 ШАГ 1: Listing Hunter — проверка новых листингов
        # ═══════════════════════════════════════════════════════════
        if self.is_module_enabled('listing'):
            try:
                from app.modules.listing_hunter import listing_hunter
                from app.brain import adaptive_brain
                
                listing_signals = await listing_hunter.get_signals({"prices": prices})
                
                for signal in listing_signals[:2]:  # Макс 2 за раз
                    # ═══════════════════════════════════════════════════════════
                    # НОВОЕ: Проверка что монета торгуется на Bybit
                    # ═══════════════════════════════════════════════════════════
                    try:
                        pair = f"{signal.symbol}USDT"
                        price = await self.bybit.get_price(pair)
                        
                        if price and price > 0:
                            # Монета существует на Bybit — добавляем в Brain
                            adaptive_brain.add_dynamic_coin(signal.symbol)
                            logger.info(f"🆕 {signal.symbol} verified on Bybit and added to Brain")
                            
                            # Уведомить
                            await self._notify_listing(signal)
                        else:
                            logger.warning(f"⚠️ {signal.symbol} not found on Bybit, skipping")
                    except Exception as e:
                        logger.warning(f"⚠️ {signal.symbol} not supported on Bybit: {e}")
                    
            except Exception as e:
                logger.error(f"Listing Hunter error: {e}")
        
        # ═══════════════════════════════════════════════════════════
        # 🧠 ШАГ 2: Adaptive Brain — главный анализ
        # ═══════════════════════════════════════════════════════════
        if self.ai_enabled:
            try:
                from app.brain import adaptive_brain, TradeAction
                from app.core.trade_tracker import trade_tracker
                
                # Получить лучшую возможность
                best = await adaptive_brain.get_best_opportunity()
                
                if best and best.action in [TradeAction.LONG, TradeAction.SHORT]:
                    
                    # Проверить антиспам
                    if not self.should_send_brain_signal(
                        best.symbol, 
                        best.action.value, 
                        best.entry_price or 0, 
                        best.confidence
                    ):
                        logger.debug(f"Brain signal skipped (antispam): {best.symbol}")
                        return
                    
                    # Отправить сигнал
                    await self._send_brain_signal(best)
                    
                    # ✅ ИСПРАВЛЕНИЕ #3: Правильный вызов trade_tracker с параметром source
                    trade_id = trade_tracker.open_trade(
                        symbol=best.symbol,
                        direction=best.action.value,
                        entry_price=best.entry_price or 0,
                        stop_loss=best.stop_loss or 0,
                        take_profit=best.take_profit or 0,
                        confidence=best.confidence,
                        size_usd=self.get_trade_size(),
                        reasoning=best.reasoning[:200],
                        source=best.source  # brain или momentum
                    )
                    
                    logger.info(f"🧠 Adaptive Brain: {best.action.value} {best.symbol} tracked (ID: {trade_id})")
                    
            except Exception as e:
                logger.error(f"Adaptive Brain error: {e}")
    
    async def _send_brain_signal(self, decision):
        """Отправить сигнал от Adaptive Brain"""
        from app.brain import TradeAction
        from app.notifications.telegram_bot import telegram_bot
        
        emoji = "🟢" if decision.action == TradeAction.LONG else "🔴"
        action = decision.action.value
        
        # Рассчитать проценты
        if decision.entry_price and decision.stop_loss:
            sl_percent = abs((decision.stop_loss - decision.entry_price) / decision.entry_price * 100)
        else:
            sl_percent = 0
        
        if decision.entry_price and decision.take_profit:
            tp_percent = abs((decision.take_profit - decision.entry_price) / decision.entry_price * 100)
        else:
            tp_percent = 0
        
        # Форматировать факторы
        factors_text = "\n".join([f"• {f}" for f in decision.key_factors[:5]]) if decision.key_factors else "• N/A"
        
        # Ограничения
        if decision.restrictions:
            restrictions_text = "\n".join([f"⚠️ {r}" for r in decision.restrictions])
        else:
            restrictions_text = "✅ Нет ограничений"
        
        text = f"""
{emoji} *{action} {decision.symbol}USDT*

━━━━━━━━━━━━━━━━━━

📍 *Вход:* ${decision.entry_price:,.2f}
🛑 *Стоп:* ${decision.stop_loss:,.2f} (-{sl_percent:.1f}%)
🎯 *Цель:* ${decision.take_profit:,.2f} (+{tp_percent:.1f}%)

━━━━━━━━━━━━━━━━━━

📊 *Режим рынка:* {decision.regime.value.upper()}

━━━━━━━━━━━━━━━━━━

🧠 *Анализ:*
{decision.reasoning}

━━━━━━━━━━━━━━━━━━

📈 *Ключевые факторы:*
{factors_text}

━━━━━━━━━━━━━━━━━━

{restrictions_text}

━━━━━━━━━━━━━━━━━━

⚠️ *Уверенность:* {decision.confidence}%
🧠 *v3.0 Adaptive Brain*
⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""
        
        await telegram_bot.send_message(text.strip())
    
    async def _notify_listing(self, signal):
        """Уведомление о листинге"""
        from app.notifications.telegram_bot import telegram_bot
        
        text = f"""
🆕 *NEW LISTING DETECTED!*

💎 *{signal.symbol}*
📊 Exchange: Bybit
⏰ {datetime.utcnow().strftime('%H:%M UTC')}

{signal.reason}
"""
        
        await telegram_bot.send_message(text.strip())


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
            is_buy = signal.direction == "BUY"
            emoji = "🟢" if is_buy else "🔴"
            action = "ПОКУПКА" if is_buy else "ПРОДАЖА"
            
            # Получаем статистику
            status = await grid_bot.get_status()
            
            # Рассчитываем профит на сетке
            grid_profit_pct = status.get('profit_per_grid', 0.5)
            
            text = f"""
📊 *СЕТКА*

{emoji} *{action}* {signal.symbol}
💰 *Цена:* ${signal.entry_price:,.2f}

📈 *Статистика сегодня:*
• Сделок: {status['today_trades']}
• Профит: ${status['today_profit_usdt']:.2f}

💡 *Что дальше:*
{'Жду рост для продажи +' + str(grid_profit_pct) + '%' if is_buy else 'Жду падение для покупки -' + str(grid_profit_pct) + '%'}

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
                is_profit = "+" in signal.reason
                emoji = "✅" if is_profit else "❌"
                result = "Прибыль" if is_profit else "Убыток"
                
                text = f"""
💰 *ФАНДИНГ ЗАКРЫТ*

{emoji} *{signal.symbol}* — {result}
📊 {signal.reason}

⏰ {signal.timestamp.strftime('%H:%M:%S')}
"""
            else:
                is_long = signal.direction == "LONG"
                emoji = "🟢" if is_long else "🔴"
                direction = "ЛОНГ" if is_long else "ШОРТ"
                
                # Получаем статус
                status = await funding_scalper.get_status()
                minutes_to = status.get("minutes_to_funding", 0)
                hours = minutes_to // 60
                mins = minutes_to % 60
                time_str = f"{hours}ч {mins}мин" if hours > 0 else f"{mins} мин"
                
                # Рассчитываем потенциал
                tp_pct = abs((signal.take_profit - signal.entry_price) / signal.entry_price * 100)
                sl_pct = abs((signal.stop_loss - signal.entry_price) / signal.entry_price * 100)
                
                text = f"""
💰 *ФАНДИНГ СКАЛЬП*

{emoji} *{direction} {signal.symbol}*

📊 *Детали сделки:*
• Вход: ${signal.entry_price:,.2f}
• Цель: ${signal.take_profit:,.2f} (+{tp_pct:.1f}%)
• Стоп: ${signal.stop_loss:,.2f} (-{sl_pct:.1f}%)

⏰ *До начисления:* {time_str}

💡 *Логика:* {signal.reason}

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
        """📊 Grid Bot — НОВЫЙ формат с буферизацией"""
        try:
            # Добавляем в буфер (не отправляем сразу!)
            smart_notifications.add_grid_signal(
                symbol=signal.symbol,
                direction=signal.direction,
                price=signal.entry_price,
                profit=0  # Профит будет при закрытии цикла
            )
            logger.debug(f"Grid signal buffered: {signal.direction} {signal.symbol}")
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
📊 *СЕТКА*

{emoji} *{action} {signal.symbol}*
💰 Цена: ${signal.entry_price:,.2f}

📈 *Сегодня:*
• Сделок: {status.get('today_trades', 0)}
• Профит: ${status.get('today_profit_usdt', 0):.2f}

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Grid executed notification error: {e}")
    
    async def _notify_funding_signal(self, signal):
        """💰 Funding Scalper — рекомендация (signal mode)"""
        try:
            is_long = signal.direction == "LONG"
            dir_emoji = "🟢" if is_long else "🔴"
            direction = "ЛОНГ" if is_long else "ШОРТ"
            
            status = await funding_scalper.get_status()
            minutes_to = status.get("minutes_to_funding", 0)
            hours = minutes_to // 60
            mins = minutes_to % 60
            time_str = f"{hours}ч {mins}мин" if hours > 0 else f"{mins} мин"
            
            # Funding rate
            funding_rate = 0
            for rate_info in status.get("top_funding_rates", []):
                if signal.symbol in rate_info.get("symbol", ""):
                    funding_rate = rate_info.get("rate", 0)
                    break
            
            if is_long:
                logic = f"Funding {funding_rate:+.3f}% — шорты платят лонгам"
            else:
                logic = f"Funding {funding_rate:+.3f}% — лонги платят шортам"
            
            tp_pct = abs((signal.take_profit - signal.entry_price) / signal.entry_price * 100)
            sl_pct = abs((signal.stop_loss - signal.entry_price) / signal.entry_price * 100)
            
            text = f"""
💰 *ФАНДИНГ — СИГНАЛ*

{dir_emoji} *{direction} {signal.symbol}*

📊 *Параметры:*
• Вход: ${signal.entry_price:,.2f}
• Цель: ${signal.take_profit:,.2f} (+{tp_pct:.1f}%)
• Стоп: ${signal.stop_loss:,.2f} (-{sl_pct:.1f}%)

⏰ *До начисления:* {time_str}

💡 *Логика:* {logic}

Откройте позицию вручную

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Funding signal notification error: {e}")
    
    async def _notify_funding_executed(self, signal):
        """💰 Funding Scalper — выполнено (auto mode)"""
        try:
            is_long = signal.direction == "LONG"
            dir_emoji = "🟢" if is_long else "🔴"
            direction = "ЛОНГ" if is_long else "ШОРТ"
            
            tp_pct = abs((signal.take_profit - signal.entry_price) / signal.entry_price * 100)
            sl_pct = abs((signal.stop_loss - signal.entry_price) / signal.entry_price * 100)
            
            text = f"""
💰 *ФАНДИНГ ОТКРЫТ*

{dir_emoji} *{direction} {signal.symbol}*

📊 *Параметры:*
• Вход: ${signal.entry_price:,.2f}
• Цель: ${signal.take_profit:,.2f} (+{tp_pct:.1f}%)
• Стоп: ${signal.stop_loss:,.2f} (-{sl_pct:.1f}%)

✅ Позиция открыта автоматически
Ожидаем начисление Funding

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Funding executed notification error: {e}")
    
    async def _notify_arbitrage_signal(self, signal):
        """🔄 Arbitrage — возможность (signal mode)"""
        try:
            text = f"""
🔄 *АРБИТРАЖ*

✨ Найден прибыльный цикл!

📊 *Детали:*
{signal.reason}

⚠️ Требуется быстрое исполнение!
Для авто-режима включите Auto

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
        """🆕 Листинг — НОВЫЙ формат, только SPOT (не perpetual!)"""
        try:
            from app.modules.listing_hunter import ListingType
            
            # ФИЛЬТР: пропускаем perpetual!
            if listing.listing_type == ListingType.PERPETUAL:
                logger.debug(f"Skip perpetual listing: {listing.symbol}")
                return
            
            # ФИЛЬТР: пропускаем если в title есть perpetual
            if "perpetual" in listing.title.lower():
                logger.debug(f"Skip perpetual listing (title): {listing.symbol}")
                return
            
            if "futures" in listing.title.lower():
                logger.debug(f"Skip futures listing: {listing.symbol}")
                return
            
            # Форматируем дату листинга
            listing_date = None
            if listing.listing_date:
                listing_date = listing.listing_date.strftime('%Y-%m-%d %H:%M UTC')
            
            # Отправляем через новую систему
            await smart_notifications.send_listing_signal(
                symbol=listing.symbol,
                name=listing.name,
                exchange=listing.exchange,
                listing_type=listing.listing_type.value,
                price=listing.current_price,
                volume=None,
                ai_description=None,
                ai_analysis=None,
                url=listing.url if listing.url else None,
                listing_date=listing_date
            )
            
            logger.info(f"🆕 Listing notification sent: {listing.symbol} on {listing.exchange}")
            
        except Exception as e:
            logger.error(f"Listing notification error: {e}")
    
    async def _notify_listing_executed(self, signal, listing):
        """🆕 Listing — куплено (auto mode)"""
        try:
            tp_price = signal.entry_price * 1.20  # +20%
            sl_price = signal.entry_price * 0.95  # -5%
            
            text = f"""
🆕 *ЛИСТИНГ КУПЛЕН*

✅ *{listing.name}* ({listing.symbol})
🏦 Биржа: {listing.exchange}

📊 *Параметры сделки:*
• Вход: ${signal.entry_price:,.4f}
• Цель: ${tp_price:,.4f} (+20%)
• Стоп: ${sl_price:,.4f} (-5%)

💡 *Стратегия:*
Скальпинг на листинге. Ожидаем быстрый рост в первые часы.

⏰ {self._get_time()}
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Listing executed notification error: {e}")
    
    async def _notify_worker_signal(self, signal):
        """👷 Worker — НОВЫЙ формат с объяснением"""
        try:
            # Получаем индикаторы (если есть)
            rsi = 50
            if hasattr(signal, 'indicators') and signal.indicators:
                rsi = signal.indicators.get('rsi', 50)
            
            # EMA тренд
            ema_trend = "вверх ✅" if signal.direction == "LONG" else "вниз ✅"
            
            # MACD
            macd_signal = "покупка" if signal.direction == "LONG" else "продажа"
            
            await smart_notifications.send_worker_signal(
                symbol=signal.symbol,
                direction=signal.direction,
                entry=signal.entry_price,
                tp=signal.take_profit,
                sl=signal.stop_loss,
                rsi=rsi,
                ema_trend=ema_trend,
                macd_signal=macd_signal,
                win_rate=signal.win_rate,
                ai_analysis=None  # Можно добавить AI позже
            )
        except Exception as e:
            logger.error(f"Worker signal notification error: {e}")
    
    async def _notify_director_signal(self, direction: str, reason: str):
        """🎩 Director — НОВЫЙ формат TAKE_CONTROL"""
        try:
            from app.ai.whale_ai import whale_ai
            
            # Получаем цену BTC
            prices = await self.bybit.get_prices(["BTC"])
            btc_price = prices.get("BTC", 0)
            
            if btc_price == 0:
                logger.warning("Director signal: BTC price is 0")
                return
            
            # Рассчитываем TP/SL
            if direction == "LONG":
                tp = btc_price * 1.04  # +4%
                sl = btc_price * 0.98  # -2%
            else:
                tp = btc_price * 0.96  # -4%
                sl = btc_price * 1.02  # +2%
            
            # Получаем метрики
            fear_greed = 50
            long_ratio = 50
            liquidations = 0
            risk_score = 50
            
            if whale_ai.last_metrics:
                m = whale_ai.last_metrics
                fear_greed = m.fear_greed_index
                long_ratio = m.long_ratio
                liquidations = m.liq_long + m.liq_short
            
            await smart_notifications.send_director_signal(
                symbol="BTC",
                direction=direction,
                entry=btc_price,
                tp=tp,
                sl=sl,
                size_percent=20,
                fear_greed=fear_greed,
                long_ratio=long_ratio,
                liquidations=liquidations,
                news_summary=reason[:50],
                risk_score=risk_score,
                scenario=reason,
                ai_analysis=None
            )
        except Exception as e:
            logger.error(f"Director signal notification error: {e}")
    
    async def _notify_director_executed(self, trade, reason: str):
        """🎩 Director — выполнено (auto mode)"""
        try:
            is_long = trade.direction == "LONG"
            dir_emoji = "🟢" if is_long else "🔴"
            dir_text = "ЛОНГ" if is_long else "ШОРТ"
            
            tp_pct = abs((trade.take_profit - trade.entry_price) / trade.entry_price * 100)
            sl_pct = abs((trade.stop_loss - trade.entry_price) / trade.entry_price * 100)
            
            text = f"""
🎩 *ДИРЕКТОР — СДЕЛКА*

{dir_emoji} *{dir_text} {trade.symbol}*

📊 *Параметры:*
• Вход: ${trade.entry_price:,.2f}
• Цель: ${trade.take_profit:,.2f} (+{tp_pct:.1f}%)
• Стоп: ${trade.stop_loss:,.2f} (-{sl_pct:.1f}%)

📋 *Анализ:*
{reason[:200]}

✅ Director взял управление

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
    # 🎯 TRADE TRACKER ACTIONS
    # ==========================================
    
    async def _send_tracker_status_if_needed(self):
        """
        Отправить статус трекера каждый час (если есть активные сделки)
        """
        try:
            active_trades = trade_tracker.get_active_trades()
            
            # Нет сделок — не отправляем
            if not active_trades:
                return
            
            now = datetime.now()
            
            # Проверяем прошёл ли час
            if self._last_tracker_status:
                elapsed = (now - self._last_tracker_status).total_seconds()
                if elapsed < self._tracker_status_interval:
                    return
            
            self._last_tracker_status = now
            
            # Формируем статус
            lines = [
                "📊 *Hourly Trade Update*",
                ""
            ]
            
            total_pnl = 0.0
            total_pnl_usd = 0.0
            
            for trade in active_trades:
                dir_emoji = "🟢" if trade.direction == "LONG" else "🔴"
                pnl_emoji = "📈" if trade.pnl_percent >= 0 else "📉"
                
                # Время в сделке
                opened_at = datetime.fromisoformat(trade.opened_at)
                hours_in_trade = (now - opened_at).total_seconds() / 3600
                
                lines.append(
                    f"{dir_emoji} *{trade.symbol}* {trade.direction}\n"
                    f"   Entry: ${trade.entry_price:,.2f} → ${trade.current_price:,.2f}\n"
                    f"   {pnl_emoji} PnL: *{trade.pnl_percent:+.2f}%* (${trade.pnl_usd:+.2f})\n"
                    f"   🕐 {hours_in_trade:.1f}h | SL двигали: {trade.sl_moves}x"
                )
                
                total_pnl += trade.pnl_percent
                total_pnl_usd += trade.pnl_usd
            
            # Итого
            total_emoji = "✅" if total_pnl >= 0 else "⚠️"
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━",
                f"{total_emoji} *Итого:* {total_pnl:+.2f}% (${total_pnl_usd:+.2f})",
                f"⏰ {now.strftime('%H:%M')}"
            ])
            
            text = "\n".join(lines)
            await telegram_bot.send_message(text)
            
            logger.info(f"🎯 Tracker hourly status sent ({len(active_trades)} trades, {total_pnl:+.2f}%)")
            
        except Exception as e:
            logger.error(f"Tracker status error: {e}")
    
    async def _handle_tracker_action(self, action: dict):
        """
        Обработать действие от TradeTracker
        
        Actions:
        - UPDATE_SL: SL передвинут
        - CLOSE_TP: Take Profit достигнут
        - CLOSE_SL: Stop Loss сработал
        """
        try:
            action_type = action.get("action")
            trade = action.get("trade")
            
            if not trade:
                return
            
            if action_type == "UPDATE_SL":
                # SL передвинут — уведомляем
                text = f"""📊 *SL Update*

{trade.direction} *{trade.symbol}*
Entry: ${trade.entry_price:,.2f}

🛡 SL: ${action['old_sl']:,.2f} → *${action['new_sl']:,.2f}*
{action['reason']}

💰 PnL: *{trade.pnl_percent:+.2f}%*
⏰ {datetime.now().strftime('%H:%M')}"""
                
                await telegram_bot.send_message(text)
                logger.info(f"🎯 Tracker: SL moved for {trade.symbol}")
            
            elif action_type == "CLOSE_TP":
                # Take Profit — поздравляем!
                text = f"""🎯 *TAKE PROFIT!*

{trade.direction} *{trade.symbol}*
Entry: ${trade.entry_price:,.2f}
Exit: ${trade.current_price:,.2f}

✅ Прибыль: *+{trade.pnl_percent:.2f}%*
💵 *+${action['pnl_usd']:.2f}*

{action['reason']}

📊 SL двигали: {trade.sl_moves} раз
⏰ {datetime.now().strftime('%H:%M')}"""
                
                await telegram_bot.send_message(text)
                logger.info(f"🎯 Tracker: TP hit for {trade.symbol} +{trade.pnl_percent:.2f}%")
            
            elif action_type == "CLOSE_SL":
                # Stop Loss — анализируем
                text = f"""🛑 *STOP LOSS*

{trade.direction} *{trade.symbol}*
Entry: ${trade.entry_price:,.2f}
Exit: ${trade.current_price:,.2f}

❌ Убыток: *{trade.pnl_percent:.2f}%*
💸 *${action['pnl_usd']:.2f}*

{action['reason']}

📊 SL двигали: {trade.sl_moves} раз
⏰ {datetime.now().strftime('%H:%M')}"""
                
                await telegram_bot.send_message(text)
                logger.info(f"🎯 Tracker: SL hit for {trade.symbol} {trade.pnl_percent:.2f}%")
            
            elif action_type == "CLOSE_MANUAL":
                # Ручное закрытие
                emoji = "✅" if action['pnl_percent'] >= 0 else "❌"
                text = f"""🔧 *Manual Close*

{trade.direction} *{trade.symbol}*
Entry: ${trade.entry_price:,.2f}
Exit: ${trade.current_price:,.2f}

{emoji} PnL: *{trade.pnl_percent:+.2f}%*
💵 *${action['pnl_usd']:+.2f}*

📝 {action.get('reason', 'Manual')}
⏰ {datetime.now().strftime('%H:%M')}"""
                
                await telegram_bot.send_message(text)
            
            elif action_type == "PNL_UPDATE":
                # Периодическое обновление PnL
                pnl_emoji = "🟢" if trade.pnl_percent >= 0 else "🔴"
                dir_emoji = "📈" if trade.direction == "LONG" else "📉"
                
                # Время в сделке
                try:
                    opened_at = datetime.fromisoformat(trade.opened_at)
                    hours_in_trade = (datetime.now() - opened_at).total_seconds() / 3600
                    time_str = f"{hours_in_trade:.1f}h"
                except:
                    time_str = "N/A"
                
                # Дистанция до TP/SL
                if trade.direction == "LONG":
                    dist_to_tp = (trade.take_profit - trade.current_price) / trade.current_price * 100
                    dist_to_sl = (trade.current_price - trade.stop_loss) / trade.current_price * 100
                else:
                    dist_to_tp = (trade.current_price - trade.take_profit) / trade.current_price * 100
                    dist_to_sl = (trade.stop_loss - trade.current_price) / trade.current_price * 100
                
                text = f"""📊 *Trade Update*

{dir_emoji} *{trade.symbol}* {trade.direction}

💰 Entry: ${trade.entry_price:,.2f}
📍 Now: *${trade.current_price:,.2f}*

{pnl_emoji} PnL: *{trade.pnl_percent:+.2f}%* (${trade.pnl_usd:+.2f})

🎯 TP: ${trade.take_profit:,.2f} ({dist_to_tp:+.1f}%)
🛡 SL: ${trade.stop_loss:,.2f} ({dist_to_sl:.1f}% away)

{action['reason']}

🕐 В сделке: {time_str}
⏰ {datetime.now().strftime('%H:%M')}"""
                
                await telegram_bot.send_message(text)
                logger.info(f"🎯 Tracker: PnL update for {trade.symbol} {trade.pnl_percent:+.2f}%")
        
        except Exception as e:
            logger.error(f"Tracker action error: {e}")
    
    # ==========================================
    # 📢 LIVE UPDATES
    # ==========================================
    
    async def _send_live_updates(self, prices: Dict, indicators: Dict):
        """
        УБРАНО: Спам каждую минуту!
        Этот метод больше не используется.
        """
        # ЗАКОММЕНТИРОВАНО: вызовы queue_director_status, queue_grid_status и т.д.
        # Теперь уведомления отправляются только при реальных сигналах
        pass
    
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
        """Выполнить сигнал - открыть сделку"""
        
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
