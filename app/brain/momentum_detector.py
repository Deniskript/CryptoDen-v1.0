"""
⚡ Momentum Detector v2.0 — РАННЕЕ обнаружение движений

ФИЛОСОФИЯ:
- ±1.0% за 2 мин = НАЧАЛО движения → можно входить
- ±1.5% за 3 мин = ПОДТВЕРЖДЕНИЕ → увеличить позицию
- ±3.0% за 5 мин = ИНФОРМАЦИЯ → поздно входить

Мониторит 50+ монет каждые 20 секунд.
При раннем обнаружении — отправляет в Brain для AI анализа.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.core.logger import logger
from app.core.config import settings


class MoveType(Enum):
    """Тип движения"""
    EARLY = "early"           # Раннее обнаружение — ВХОДИТЬ
    CONFIRMED = "confirmed"   # Подтверждённое — УСИЛИТЬ
    LATE = "late"             # Позднее — НЕ ВХОДИТЬ


class MoveDirection(Enum):
    """Направление"""
    PUMP = "PUMP"
    DUMP = "DUMP"


@dataclass
class MomentumMove:
    """Обнаруженное движение"""
    symbol: str
    direction: MoveDirection
    move_type: MoveType
    change_percent: float
    timeframe_seconds: int
    price_start: float
    price_now: float
    detected_at: datetime
    volume_spike: bool = False
    
    @property
    def is_actionable(self) -> bool:
        """Можно ли действовать (входить в сделку)"""
        return self.move_type in [MoveType.EARLY, MoveType.CONFIRMED]
    
    @property
    def emoji(self) -> str:
        if self.move_type == MoveType.EARLY:
            return "🟢" if self.direction == MoveDirection.PUMP else "🔴"
        elif self.move_type == MoveType.CONFIRMED:
            return "🟡"
        else:
            return "⚠️"


@dataclass
class PricePoint:
    """Точка цены с временем"""
    time: datetime
    price: float
    volume: float = 0.0


class MomentumDetector:
    """
    Детектор раннего momentum
    
    Уровни обнаружения:
    1. EARLY:     ±1.0% за 2 мин  → Отправить в Brain, можно входить
    2. CONFIRMED: ±1.5% за 3 мин  → Движение подтверждено
    3. LATE:      ±3.0% за 5 мин  → Только информация, НЕ входить
    """
    
    # ═══════════════════════════════════════════════════════════
    # КОНФИГУРАЦИЯ
    # ═══════════════════════════════════════════════════════════
    
    # Топ-50 ликвидных монет для мониторинга
    COINS_TO_MONITOR: List[str] = [
        # Топ-10 по капитализации
        "BTC", "ETH", "SOL", "BNB", "XRP", 
        "ADA", "DOGE", "LINK", "AVAX", "MATIC",
        # Топ 11-20
        "DOT", "UNI", "SHIB", "LTC", "ATOM",
        "APT", "ARB", "OP", "SUI", "NEAR",
        # Топ 21-30
        "FTM", "SAND", "MANA", "AXS", "GALA",
        "ENJ", "CHZ", "FLOW", "IMX", "LRC",
        # DeFi
        "CRV", "AAVE", "MKR", "SNX", "COMP",
        "SUSHI", "1INCH", "BAL", "RUNE", "KAVA",
        # AI & Data
        "INJ", "FET", "AGIX", "OCEAN", "RNDR",
        "GRT", "FIL", "AR", "TIA", "SEI"
    ]
    
    # Пороги обнаружения (КЛЮЧЕВЫЕ НАСТРОЙКИ!)
    THRESHOLDS = {
        # EARLY — начало движения, МОЖНО ВХОДИТЬ
        "early": {
            "percent": 1.0,      # ±1.0%
            "seconds": 120,      # за 2 минуты
            "action": "TRADE"    # отправить в Brain для входа
        },
        # CONFIRMED — движение подтверждено
        "confirmed": {
            "percent": 1.5,      # ±1.5%
            "seconds": 180,      # за 3 минуты
            "action": "CONFIRM"  # усилить позицию если есть
        },
        # LATE — уже поздно входить
        "late": {
            "percent": 3.0,      # ±3.0%
            "seconds": 300,      # за 5 минут
            "action": "INFO"     # только информация
        }
    }
    
    # Частота проверки
    CHECK_INTERVAL_SECONDS = 20  # каждые 20 секунд
    
    # Антиспам
    COOLDOWN_EARLY_MINUTES = 10      # Early сигнал: раз в 10 мин на монету
    COOLDOWN_CONFIRMED_MINUTES = 15  # Confirmed: раз в 15 мин
    COOLDOWN_LATE_MINUTES = 30       # Late info: раз в 30 мин
    
    # История цен
    MAX_HISTORY_SECONDS = 600  # хранить 10 минут истории
    
    # ═══════════════════════════════════════════════════════════
    # ИНИЦИАЛИЗАЦИЯ
    # ═══════════════════════════════════════════════════════════
    
    def __init__(self):
        self.running: bool = False
        self._task: Optional[asyncio.Task] = None
        
        # История цен: {symbol: [PricePoint, ...]}
        self.price_history: Dict[str, List[PricePoint]] = {}
        
        # Антиспам: {symbol_movetype: datetime}
        self.last_alerts: Dict[str, datetime] = {}
        
        # Обнаруженные движения
        self.detected_moves: List[MomentumMove] = []
        
        # Статистика
        self.stats = {
            "checks": 0,
            "early_detected": 0,
            "confirmed_detected": 0,
            "late_detected": 0,
            "sent_to_brain": 0
        }
        
        logger.info(f"⚡ MomentumDetector v2.0 initialized")
        logger.info(f"   📊 Coins: {len(self.COINS_TO_MONITOR)}")
        logger.info(f"   🎯 Early: ±{self.THRESHOLDS['early']['percent']}% / {self.THRESHOLDS['early']['seconds']}s")
        logger.info(f"   ✅ Confirmed: ±{self.THRESHOLDS['confirmed']['percent']}% / {self.THRESHOLDS['confirmed']['seconds']}s")
        logger.info(f"   ⚠️ Late: ±{self.THRESHOLDS['late']['percent']}% / {self.THRESHOLDS['late']['seconds']}s")
    
    # ═══════════════════════════════════════════════════════════
    # УПРАВЛЕНИЕ
    # ═══════════════════════════════════════════════════════════
    
    async def start(self, additional_coins: List[str] = None):
        """Запустить мониторинг"""
        if self.running:
            logger.warning("⚡ MomentumDetector already running")
            return
        
        # Добавить дополнительные монеты
        if additional_coins:
            for coin in additional_coins:
                coin = coin.upper().replace("USDT", "")
                if coin not in self.COINS_TO_MONITOR:
                    self.COINS_TO_MONITOR.append(coin)
                    logger.debug(f"⚡ Added {coin} to momentum monitoring")
        
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        
        logger.info(f"⚡ MomentumDetector STARTED")
        logger.info(f"   📊 Monitoring {len(self.COINS_TO_MONITOR)} coins")
        logger.info(f"   ⏱️ Check every {self.CHECK_INTERVAL_SECONDS}s")
        logger.info(f"   ⚠️ Will only work when MarketMonitor is running")
    
    async def stop(self):
        """Остановить мониторинг"""
        self.running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"⚡ MomentumDetector STOPPED")
        logger.info(f"   📊 Stats: {self.stats}")
    
    # ═══════════════════════════════════════════════════════════
    # ГЛАВНЫЙ ЦИКЛ
    # ═══════════════════════════════════════════════════════════
    
    async def _monitor_loop(self):
        """Главный цикл мониторинга"""
        from app.trading.bybit.client import bybit_client
        from app.core.monitor import market_monitor
        
        logger.info("⚡ Momentum monitor loop started")
        
        while self.running:
            try:
                # ═══════════════════════════════════════════════════════════
                # ПРОВЕРКА: Работать только если MarketMonitor запущен
                # ═══════════════════════════════════════════════════════════
                if not market_monitor.running:
                    await asyncio.sleep(5)
                    continue
                
                self.stats["checks"] += 1
                now = datetime.now(timezone.utc)
                
                # 1. Получить цены всех монет
                prices = await bybit_client.get_prices(self.COINS_TO_MONITOR)
                
                if not prices:
                    logger.warning("⚡ No prices received, retrying...")
                    await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
                    continue
                
                # 2. Обновить историю и проверить движения
                moves_detected = []
                
                for symbol, price in prices.items():
                    if not price or price <= 0:
                        continue
                    
                    # 🛡️ ЗАЩИТА: Проверить валидность цены (не скачок > 20%)
                    if not self._is_price_valid(symbol, price):
                        logger.warning(f"⚠️ Skipped invalid price for {symbol}: ${price:.4f}")
                        continue
                    
                    # Добавить в историю (только реальные цены!)
                    self._add_price_point(symbol, price, now)
                    
                    # Проверить все уровни движения
                    move = self._detect_move(symbol, now)
                    
                    if move:
                        moves_detected.append(move)
                
                # 3. Обработать обнаруженные движения
                for move in moves_detected:
                    await self._handle_move(move)
                
                # 4. Очистить старую историю
                self._cleanup_old_history(now)
                
                # 5. Периодический лог статуса (каждые 5 минут)
                if self.stats["checks"] % 15 == 0:  # ~5 мин при 20s интервале
                    logger.info(f"⚡ Momentum status: {len(prices)} coins | "
                               f"Early: {self.stats['early_detected']} | "
                               f"Confirmed: {self.stats['confirmed_detected']} | "
                               f"Late: {self.stats['late_detected']}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"⚡ Momentum loop error: {e}")
            
            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
    
    # ═══════════════════════════════════════════════════════════
    # РАБОТА С ИСТОРИЕЙ ЦЕН
    # ═══════════════════════════════════════════════════════════
    
    def _add_price_point(self, symbol: str, price: float, now: datetime):
        """Добавить точку цены в историю"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        point = PricePoint(time=now, price=price)
        self.price_history[symbol].append(point)
    
    def _is_price_valid(self, symbol: str, new_price: float) -> bool:
        """
        🛡️ Проверить что цена реальная (не скачок > 20% за цикл)
        
        Защита от:
        - Исторических данных из CSV
        - Флэш-крашей
        - Багов API
        """
        if symbol not in self.price_history or not self.price_history[symbol]:
            return True  # Первая цена — всегда валидна
        
        last_price = self.price_history[symbol][-1].price
        change = abs((new_price - last_price) / last_price) * 100
        
        # Если изменение > 20% за 20 секунд — это аномалия!
        # Реальные крипто-монеты не двигаются так быстро (кроме делистингов)
        if change > 20:
            logger.warning(
                f"⚠️ Price anomaly detected: {symbol} "
                f"${last_price:.4f} → ${new_price:.4f} "
                f"({change:+.1f}% in {self.CHECK_INTERVAL_SECONDS}s) - REJECTED!"
            )
            return False
        
        return True
    
    def _get_price_at_time(self, symbol: str, seconds_ago: int, now: datetime) -> Optional[float]:
        """Получить цену N секунд назад"""
        if symbol not in self.price_history:
            return None
        
        history = self.price_history[symbol]
        if not history:
            return None
        
        target_time = now - timedelta(seconds=seconds_ago)
        
        # Ищем ближайшую точку к target_time
        closest_point = None
        closest_diff = float('inf')
        
        for point in history:
            diff = abs((point.time - target_time).total_seconds())
            
            # Точка должна быть ДО или ОКОЛО target_time (±30 сек)
            if point.time <= target_time + timedelta(seconds=30):
                if diff < closest_diff:
                    closest_diff = diff
                    closest_point = point
        
        # Если нашли точку в пределах разумного времени
        if closest_point and closest_diff < 60:
            return closest_point.price
        
        return None
    
    def _cleanup_old_history(self, now: datetime):
        """Удалить старые точки истории"""
        cutoff = now - timedelta(seconds=self.MAX_HISTORY_SECONDS)
        
        for symbol in list(self.price_history.keys()):
            self.price_history[symbol] = [
                p for p in self.price_history[symbol]
                if p.time > cutoff
            ]
            
            # Удалить пустые списки
            if not self.price_history[symbol]:
                del self.price_history[symbol]
    
    # ═══════════════════════════════════════════════════════════
    # ДЕТЕКЦИЯ ДВИЖЕНИЙ
    # ═══════════════════════════════════════════════════════════
    
    def _detect_move(self, symbol: str, now: datetime) -> Optional[MomentumMove]:
        """
        Проверить все уровни движения для монеты
        
        Приоритет: EARLY > CONFIRMED > LATE
        (если есть EARLY — не проверяем остальные)
        """
        history = self.price_history.get(symbol, [])
        
        if len(history) < 2:
            return None
        
        current_price = history[-1].price
        
        # Проверяем уровни по приоритету
        for level_name in ["early", "confirmed", "late"]:
            threshold = self.THRESHOLDS[level_name]
            
            # Получить цену N секунд назад
            old_price = self._get_price_at_time(
                symbol, 
                threshold["seconds"], 
                now
            )
            
            if not old_price:
                continue
            
            # Рассчитать изменение
            change_percent = ((current_price - old_price) / old_price) * 100
            
            # Проверить порог
            if abs(change_percent) >= threshold["percent"]:
                # 🛡️ ЗАЩИТА: Игнорировать экстремальные движения > 15%
                # Скорее всего это баг или исторические данные из CSV
                if abs(change_percent) > 15:
                    logger.warning(
                        f"⚠️ Suspicious move detected: {symbol} "
                        f"{change_percent:+.2f}% / {threshold['seconds']}s - "
                        f"REJECTED (likely historical data or bug)"
                    )
                    # Очистить историю (оставить только последние 5 точек)
                    if symbol in self.price_history:
                        self.price_history[symbol] = self.price_history[symbol][-5:]
                    continue
                
                # Определить направление по ЦЕНЕ, не по проценту
                if current_price < old_price:
                    direction = MoveDirection.DUMP
                    change_percent = -abs(change_percent)  # Гарантировано минус
                else:
                    direction = MoveDirection.PUMP
                    change_percent = abs(change_percent)   # Гарантировано плюс
                
                # Определить тип
                move_type = MoveType[level_name.upper()]
                
                # Проверить антиспам
                if not self._can_alert(symbol, move_type):
                    continue
                
                # Создать объект движения
                return MomentumMove(
                    symbol=symbol,
                    direction=direction,
                    move_type=move_type,
                    change_percent=change_percent,
                    timeframe_seconds=threshold["seconds"],
                    price_start=old_price,
                    price_now=current_price,
                    detected_at=now
                )
        
        return None
    
    # ═══════════════════════════════════════════════════════════
    # АНТИСПАМ
    # ═══════════════════════════════════════════════════════════
    
    def _can_alert(self, symbol: str, move_type: MoveType) -> bool:
        """Проверить можно ли отправить алерт (антиспам)"""
        key = f"{symbol}_{move_type.value}"
        
        if key not in self.last_alerts:
            return True
        
        # Определить cooldown
        if move_type == MoveType.EARLY:
            cooldown = self.COOLDOWN_EARLY_MINUTES
        elif move_type == MoveType.CONFIRMED:
            cooldown = self.COOLDOWN_CONFIRMED_MINUTES
        else:
            cooldown = self.COOLDOWN_LATE_MINUTES
        
        elapsed = datetime.now(timezone.utc) - self.last_alerts[key]
        return elapsed.total_seconds() > (cooldown * 60)
    
    def _mark_alerted(self, symbol: str, move_type: MoveType):
        """Отметить что алерт отправлен"""
        key = f"{symbol}_{move_type.value}"
        self.last_alerts[key] = datetime.now(timezone.utc)
    
    # ═══════════════════════════════════════════════════════════
    # ОБРАБОТКА ДВИЖЕНИЙ
    # ═══════════════════════════════════════════════════════════
    
    async def _handle_move(self, move: MomentumMove):
        """Обработать обнаруженное движение"""
        
        # Отметить алерт
        self._mark_alerted(move.symbol, move.move_type)
        
        # Сохранить в историю
        self.detected_moves.append(move)
        
        # Обновить статистику
        if move.move_type == MoveType.EARLY:
            self.stats["early_detected"] += 1
        elif move.move_type == MoveType.CONFIRMED:
            self.stats["confirmed_detected"] += 1
        else:
            self.stats["late_detected"] += 1
        
        # Ограничить историю
        if len(self.detected_moves) > 100:
            self.detected_moves = self.detected_moves[-100:]
        
        # Логировать
        logger.info(f"⚡ MOMENTUM {move.move_type.value.upper()}: "
                   f"{move.symbol} {move.direction.value} "
                   f"{move.change_percent:+.2f}% / {move.timeframe_seconds}s")
        
        # Действия в зависимости от типа
        if move.move_type == MoveType.EARLY:
            await self._handle_early_move(move)
        elif move.move_type == MoveType.CONFIRMED:
            await self._handle_confirmed_move(move)
        else:
            await self._handle_late_move(move)
    
    async def _handle_early_move(self, move: MomentumMove):
        """
        EARLY движение — ГЛАВНОЕ для торговли!
        
        1. Добавить в Brain для AI анализа
        2. Отправить уведомление
        3. Brain решит входить или нет
        """
        from app.notifications.telegram_bot import telegram_bot
        
        try:
            # 1. Добавить в Brain
            from app.brain import adaptive_brain
            adaptive_brain.add_dynamic_coin(move.symbol)
            self.stats["sent_to_brain"] += 1
            
            # 2. Запросить анализ Brain
            decision = None
            try:
                decision = await adaptive_brain.analyze(move.symbol)
            except Exception as e:
                logger.error(f"Brain analyze error: {e}")
            
            # 3. Сформировать сообщение
            dir_emoji = "🟢" if move.direction == MoveDirection.PUMP else "🔴"
            dir_text = "РАСТЁТ" if move.direction == MoveDirection.PUMP else "ПАДАЕТ"
            
            # Рекомендация на основе Brain
            if decision and decision.action.value != "WAIT":
                brain_text = f"🧠 Brain: *{decision.action.value}* ({decision.confidence}%)"
                action_text = "✅ *Можно рассмотреть вход!*"
            else:
                brain_text = "🧠 Brain: анализирует..."
                action_text = "👀 *Наблюдаем за развитием*"
            
            text = f"""
⚡ *РАННЕЕ ДВИЖЕНИЕ*

{dir_emoji} *{move.symbol}* {dir_text}!

📊 *+{abs(move.change_percent):.2f}%* за {move.timeframe_seconds // 60} мин

💰 ${move.price_start:,.4f} → ${move.price_now:,.4f}

{brain_text}

{action_text}

⏰ {move.detected_at.strftime('%H:%M:%S UTC')}
"""
            
            await telegram_bot.send_message(text.strip())
            
        except Exception as e:
            logger.error(f"Handle early move error: {e}")
    
    async def _handle_confirmed_move(self, move: MomentumMove):
        """
        CONFIRMED движение — подтверждение тренда
        
        Если уже в позиции — можно усилить
        Если нет — всё ещё можно войти
        """
        from app.notifications.telegram_bot import telegram_bot
        
        try:
            dir_emoji = "🟡"
            dir_text = "РОСТ ПОДТВЕРЖДЁН" if move.direction == MoveDirection.PUMP else "ПАДЕНИЕ ПОДТВЕРЖДЕНО"
            
            text = f"""
✅ *ДВИЖЕНИЕ ПОДТВЕРЖДЕНО*

{dir_emoji} *{move.symbol}* — {dir_text}

📊 *{move.change_percent:+.2f}%* за {move.timeframe_seconds // 60} мин

💰 ${move.price_start:,.4f} → ${move.price_now:,.4f}

💡 Если в позиции — можно усилить
⚠️ Новый вход — повышенный риск

⏰ {move.detected_at.strftime('%H:%M:%S UTC')}
"""
            
            await telegram_bot.send_message(text.strip())
            
        except Exception as e:
            logger.error(f"Handle confirmed move error: {e}")
    
    async def _handle_late_move(self, move: MomentumMove):
        """
        LATE движение — только информация
        
        НЕ рекомендуем входить!
        Возможен откат.
        """
        from app.notifications.telegram_bot import telegram_bot
        
        try:
            dir_text = "вырос" if move.direction == MoveDirection.PUMP else "упал"
            
            # Рекомендация
            if move.direction == MoveDirection.PUMP:
                advice = "⚠️ *Не входить в лонг* — вероятен откат"
            else:
                advice = "⚠️ *Не входить в шорт* — возможен отскок"
            
            text = f"""
⚠️ *СИЛЬНОЕ ДВИЖЕНИЕ*

*{move.symbol}* {dir_text} на *{abs(move.change_percent):.2f}%*

💰 ${move.price_start:,.4f} → ${move.price_now:,.4f}

{advice}

📊 Это информация, не сигнал!

⏰ {move.detected_at.strftime('%H:%M:%S UTC')}
"""
            
            await telegram_bot.send_message(text.strip())
            
        except Exception as e:
            logger.error(f"Handle late move error: {e}")
    
    # ═══════════════════════════════════════════════════════════
    # API МЕТОДЫ
    # ═══════════════════════════════════════════════════════════
    
    def get_recent_moves(self, minutes: int = 60) -> List[MomentumMove]:
        """Получить движения за последние N минут"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return [m for m in self.detected_moves if m.detected_at > cutoff]
    
    def get_actionable_moves(self) -> List[MomentumMove]:
        """Получить движения по которым можно действовать"""
        recent = self.get_recent_moves(30)  # За последние 30 мин
        return [m for m in recent if m.is_actionable]
    
    def get_status(self) -> dict:
        """Статус для API"""
        recent = self.get_recent_moves(60)
        
        return {
            "running": self.running,
            "version": "2.0",
            "coins_monitored": len(self.COINS_TO_MONITOR),
            "check_interval_seconds": self.CHECK_INTERVAL_SECONDS,
            "thresholds": {
                "early": f"±{self.THRESHOLDS['early']['percent']}% / {self.THRESHOLDS['early']['seconds']}s",
                "confirmed": f"±{self.THRESHOLDS['confirmed']['percent']}% / {self.THRESHOLDS['confirmed']['seconds']}s",
                "late": f"±{self.THRESHOLDS['late']['percent']}% / {self.THRESHOLDS['late']['seconds']}s",
            },
            "stats": self.stats,
            "recent_moves_1h": {
                "early": len([m for m in recent if m.move_type == MoveType.EARLY]),
                "confirmed": len([m for m in recent if m.move_type == MoveType.CONFIRMED]),
                "late": len([m for m in recent if m.move_type == MoveType.LATE]),
            },
            "price_history_symbols": len(self.price_history)
        }


# ═══════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ═══════════════════════════════════════════════════════════

momentum_detector = MomentumDetector()
