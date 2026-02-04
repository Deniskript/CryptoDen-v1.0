"""
⚡ Momentum Detector — Детектор резких движений
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

from app.core.logger import logger


class MomentumType(Enum):
    PUMP = "pump"
    DUMP = "dump"
    NONE = "none"


@dataclass
class MomentumAlert:
    symbol: str
    momentum_type: MomentumType
    price_change_1m: float
    price_change_5m: float
    current_price: float
    timestamp: datetime


class MomentumDetector:
    
    THRESHOLDS = {
        "price_change_1m": 1.5,
        "price_change_5m": 3.0,
    }
    
    ALERT_COOLDOWN = 300
    
    def __init__(self):
        self._price_history: Dict[str, List[tuple]] = {}
        self._last_alert: Dict[str, datetime] = {}
        self._running = False
        self._alerts: List[MomentumAlert] = []
        logger.info("⚡ Momentum Detector initialized")
    
    async def start(self, coins: List[str]):
        self._running = True
        logger.info(f"⚡ Momentum Detector started for {len(coins)} coins")
        
        while self._running:
            try:
                await self._check_all_coins(coins)
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Momentum detector error: {e}")
                await asyncio.sleep(10)
    
    def stop(self):
        self._running = False
        logger.info("⚡ Momentum Detector stopped")
    
    async def _check_all_coins(self, coins: List[str]):
        try:
            from app.trading.bybit.client import bybit_client
            
            for coin in coins[:10]:
                try:
                    pair = f"{coin}USDT"
                    current_price = await bybit_client.get_price(pair)
                    
                    if current_price and current_price > 0:
                        self._update_price_history(coin, current_price)
                        alert = self._detect_momentum(coin, current_price)
                        
                        if alert and alert.momentum_type != MomentumType.NONE:
                            await self._handle_momentum(alert)
                except Exception as e:
                    continue
        except Exception as e:
            logger.error(f"Check coins error: {e}")
    
    def _update_price_history(self, symbol: str, price: float):
        now = datetime.utcnow()
        
        if symbol not in self._price_history:
            self._price_history[symbol] = []
        
        self._price_history[symbol].append((now, price))
        
        cutoff = now - timedelta(minutes=10)
        self._price_history[symbol] = [
            (ts, p) for ts, p in self._price_history[symbol] if ts > cutoff
        ]
    
    def _detect_momentum(self, symbol: str, current_price: float) -> Optional[MomentumAlert]:
        if symbol not in self._price_history:
            return None
        
        history = self._price_history[symbol]
        if len(history) < 5:
            return None
        
        now = datetime.utcnow()
        
        price_1m_ago = self._get_price_at_time(history, now - timedelta(minutes=1))
        price_5m_ago = self._get_price_at_time(history, now - timedelta(minutes=5))
        
        if price_1m_ago is None:
            price_1m_ago = history[0][1] if history else current_price
        if price_5m_ago is None:
            price_5m_ago = history[0][1] if history else current_price
        
        change_1m = ((current_price - price_1m_ago) / price_1m_ago) * 100 if price_1m_ago > 0 else 0
        change_5m = ((current_price - price_5m_ago) / price_5m_ago) * 100 if price_5m_ago > 0 else 0
        
        momentum_type = MomentumType.NONE
        
        if change_1m >= self.THRESHOLDS["price_change_1m"]:
            momentum_type = MomentumType.PUMP
        elif change_1m <= -self.THRESHOLDS["price_change_1m"]:
            momentum_type = MomentumType.DUMP
        elif change_5m >= self.THRESHOLDS["price_change_5m"]:
            momentum_type = MomentumType.PUMP
        elif change_5m <= -self.THRESHOLDS["price_change_5m"]:
            momentum_type = MomentumType.DUMP
        
        if momentum_type == MomentumType.NONE:
            return None
        
        if symbol in self._last_alert:
            if (now - self._last_alert[symbol]).total_seconds() < self.ALERT_COOLDOWN:
                return None
        
        return MomentumAlert(
            symbol=symbol,
            momentum_type=momentum_type,
            price_change_1m=change_1m,
            price_change_5m=change_5m,
            current_price=current_price,
            timestamp=now,
        )
    
    def _get_price_at_time(self, history: List[tuple], target_time: datetime) -> Optional[float]:
        for ts, price in reversed(history):
            if ts <= target_time:
                return price
        return None
    
    async def _handle_momentum(self, alert: MomentumAlert):
        logger.info(f"⚡ MOMENTUM: {alert.symbol} {alert.momentum_type.value} "
                   f"{alert.price_change_1m:+.2f}% (1m)")
        
        self._last_alert[alert.symbol] = alert.timestamp
        self._alerts.append(alert)
        
        # Оставляем только последние 100 алертов
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]
        
        try:
            from app.brain.adaptive_brain import adaptive_brain, TradeAction
            
            decision = await adaptive_brain.analyze(alert.symbol)
            decision.source = "momentum"
            
            if decision.action in [TradeAction.LONG, TradeAction.SHORT]:
                if decision.confidence >= 60:
                    await self._notify_momentum_signal(alert, decision)
        except Exception as e:
            logger.error(f"Handle momentum error: {e}")
    
    async def _notify_momentum_signal(self, alert: MomentumAlert, decision):
        try:
            from app.notifications.telegram_bot import telegram_bot
            from app.brain.adaptive_brain import TradeAction
            
            emoji = "🟢" if decision.action == TradeAction.LONG else "🔴"
            momentum_emoji = "🚀" if alert.momentum_type == MomentumType.PUMP else "💥"
            
            text = f"""
{momentum_emoji}⚡ *MOMENTUM DETECTED!*

{emoji} *{decision.action.value} {alert.symbol}USDT*

⚡ *Движение:*
• 1 мин: {alert.price_change_1m:+.2f}%
• 5 мин: {alert.price_change_5m:+.2f}%

📍 *Вход:* ${decision.entry_price:,.2f}
🛑 *Стоп:* ${decision.stop_loss:,.2f}
🎯 *Цель:* ${decision.take_profit:,.2f}

⚠️ *Уверенность:* {decision.confidence}%
"""
            await telegram_bot.send_message(text.strip())
        except Exception as e:
            logger.error(f"Notify momentum error: {e}")
    
    def get_status(self) -> dict:
        return {
            "name": "Momentum Detector",
            "running": self._running,
            "tracking": len(self._price_history),
            "alerts_count": len(self._alerts),
            "thresholds": self.THRESHOLDS,
            "cooldown": self.ALERT_COOLDOWN
        }
    
    def get_recent_alerts(self, limit: int = 10) -> List[dict]:
        return [
            {
                "symbol": a.symbol,
                "type": a.momentum_type.value,
                "change_1m": a.price_change_1m,
                "change_5m": a.price_change_5m,
                "price": a.current_price,
                "time": a.timestamp.isoformat()
            }
            for a in self._alerts[-limit:]
        ]


momentum_detector = MomentumDetector()
