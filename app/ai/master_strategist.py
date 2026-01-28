"""
👑 Master Strategist — Главный стратег CryptoDen

Функции:
- Анализирует общую картину рынка каждые 30 минут
- Решает какие модули включить/выключить
- Устанавливает режимы работы (агрессивный/осторожный)
- Сохраняет решения в data/master_strategy.json
- Уведомляет в Telegram о своих решениях

НЕ управляет:
- Director AI (полностью независимый)
"""

import asyncio
import json
import httpx
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from pathlib import Path
from enum import Enum
import logging
import re
import os

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════

class MarketCondition(Enum):
    SIDEWAYS = "sideways"           # Боковик — Grid агрессивный
    BULLISH = "bullish"             # Тренд вверх — Technical ВКЛ
    BEARISH = "bearish"             # Тренд вниз — осторожно
    HIGH_VOLATILITY = "high_vol"    # Высокая волатильность — пауза
    DANGEROUS = "dangerous"         # Опасно — всё выкл (кроме Director)


class GridMode(Enum):
    AGGRESSIVE = "aggressive"       # 1% шаг, 10 уровней
    BALANCED = "balanced"           # 1.5% шаг, 7 уровней  
    CONSERVATIVE = "conservative"   # 2% шаг, 5 уровней
    OFF = "off"


# ═══════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════

@dataclass
class ModuleStrategy:
    """Стратегия для одного модуля"""
    enabled: bool = True
    mode: str = "balanced"  # Для Grid: aggressive/balanced/conservative
    reason: str = ""


@dataclass
class MasterStrategy:
    """Полная стратегия от Master"""
    timestamp: str = ""
    valid_until: str = ""
    market_condition: str = "sideways"
    confidence: int = 70
    
    # Модули которыми управляет Master
    grid: ModuleStrategy = field(default_factory=lambda: ModuleStrategy())
    funding: ModuleStrategy = field(default_factory=lambda: ModuleStrategy())
    technical: ModuleStrategy = field(default_factory=lambda: ModuleStrategy())
    
    # Общий анализ
    reasoning: str = ""
    risk_level: str = "normal"  # low, normal, elevated, high
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "valid_until": self.valid_until,
            "market_condition": self.market_condition,
            "confidence": self.confidence,
            "modules": {
                "grid": asdict(self.grid),
                "funding": asdict(self.funding),
                "technical": asdict(self.technical),
            },
            "reasoning": self.reasoning,
            "risk_level": self.risk_level
        }


# ═══════════════════════════════════════════════════════════
# MASTER STRATEGIST
# ═══════════════════════════════════════════════════════════

class MasterStrategist:
    """
    👑 Master Strategist — Главный стратег
    
    Claude Sonnet 4.5 анализирует рынок и решает:
    - Grid: aggressive/balanced/conservative/off
    - Funding: on/off
    - Technical: on/off
    
    НЕ трогает Director AI — он независимый!
    """
    
    MODEL = "anthropic/claude-sonnet-4.5"  # Sonnet 4.5!
    STRATEGY_FILE = Path("data/master_strategy.json")
    ANALYSIS_INTERVAL = 30 * 60  # 30 минут
    
    # Модули которыми управляет Master
    MANAGED_MODULES = ["grid", "funding", "technical"]
    
    def __init__(self):
        self.current_strategy: Optional[MasterStrategy] = None
        self.last_analysis: Optional[datetime] = None
        self.openrouter_key = None
        self._load_strategy()
        self._load_api_key()
        logger.info("👑 Master Strategist инициализирован")
    
    def _load_api_key(self):
        """Загрузить OpenRouter API key"""
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if not self.openrouter_key:
            # Попробовать из .env
            env_path = Path(".env")
            if env_path.exists():
                for line in env_path.read_text().split("\n"):
                    if line.startswith("OPENROUTER_API_KEY="):
                        self.openrouter_key = line.split("=", 1)[1].strip()
                        break
        
        if self.openrouter_key:
            logger.info("👑 OpenRouter API key загружен")
        else:
            logger.warning("👑 OpenRouter API key не найден!")
    
    def _load_strategy(self):
        """Загрузить стратегию из JSON"""
        try:
            if self.STRATEGY_FILE.exists():
                data = json.loads(self.STRATEGY_FILE.read_text())
                
                # Проверить срок действия
                valid_until_str = data.get("valid_until", "")
                if valid_until_str:
                    try:
                        valid_until = datetime.fromisoformat(valid_until_str)
                        if datetime.now() < valid_until:
                            self.current_strategy = MasterStrategy(
                                timestamp=data.get("timestamp", ""),
                                valid_until=data.get("valid_until", ""),
                                market_condition=data.get("market_condition", "sideways"),
                                confidence=data.get("confidence", 70),
                                reasoning=data.get("reasoning", ""),
                                risk_level=data.get("risk_level", "normal"),
                            )
                            
                            # Загрузить модули
                            modules = data.get("modules", {})
                            if "grid" in modules:
                                self.current_strategy.grid = ModuleStrategy(**modules["grid"])
                            if "funding" in modules:
                                self.current_strategy.funding = ModuleStrategy(**modules["funding"])
                            if "technical" in modules:
                                self.current_strategy.technical = ModuleStrategy(**modules["technical"])
                            
                            logger.info(f"👑 Loaded strategy: {self.current_strategy.market_condition}")
                            return
                    except ValueError:
                        pass
                
                logger.info("👑 Strategy expired, will analyze fresh")
        except Exception as e:
            logger.error(f"👑 Error loading strategy: {e}")
    
    def _save_strategy(self):
        """Сохранить стратегию в JSON"""
        try:
            self.STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.STRATEGY_FILE.write_text(
                json.dumps(self.current_strategy.to_dict(), indent=2, ensure_ascii=False)
            )
            logger.info("👑 Strategy saved to JSON")
        except Exception as e:
            logger.error(f"👑 Error saving strategy: {e}")
    
    async def analyze_market(self, market_data: Dict) -> MasterStrategy:
        """
        🧠 Главный метод — анализ рынка через Claude Sonnet 4.5
        
        Входные данные:
        - prices: текущие цены
        - whale_metrics: от WhaleAI
        - news: последние новости
        - volatility: волатильность
        - funding_rates: ставки фандинга
        """
        
        if not self.openrouter_key:
            logger.error("👑 No OpenRouter API key!")
            return self._default_strategy()
        
        # Формируем промпт для AI
        prompt = self._build_analysis_prompt(market_data)
        
        try:
            logger.info("👑 Запуск анализа рынка через Claude Sonnet 4.5...")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openrouter_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://cryptoden.ru",
                        "X-Title": "CryptoDen Master Strategist",
                    },
                    json={
                        "model": self.MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": """Ты Master Strategist криптовалютного бота CryptoDen.

Твоя задача — анализировать рынок и решать какие модули включить.

Ты управляешь:
- Grid Bot (режимы: aggressive/balanced/conservative/off)
- Funding Scalper (on/off)
- Technical Analysis (on/off)

Ты НЕ управляешь Director AI — он независимый.

ПРАВИЛА:
1. SIDEWAYS (боковик, 30-70 F&G) → Grid aggressive, остальные balanced
2. BULLISH (сильный тренд вверх, F&G > 60) → Grid conservative, Technical ON
3. BEARISH (тренд вниз, F&G < 40) → Grid conservative, осторожность
4. HIGH_VOL (высокая волатильность, OI change > 5%) → Grid OFF, только сигналы
5. DANGEROUS (экстремумы: F&G < 15 или > 85) → Всё OFF, только Director

Отвечай ТОЛЬКО в JSON формате:
{
    "market_condition": "sideways|bullish|bearish|high_vol|dangerous",
    "confidence": 70,
    "risk_level": "low|normal|elevated|high",
    "modules": {
        "grid": {"enabled": true, "mode": "aggressive|balanced|conservative", "reason": "..."},
        "funding": {"enabled": true, "reason": "..."},
        "technical": {"enabled": true, "reason": "..."}
    },
    "reasoning": "Краткое объяснение на русском (2-3 предложения)"
}"""
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1000,
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    
                    logger.info(f"👑 AI ответ получен: {len(content)} символов")
                    
                    # Парсим JSON из ответа
                    strategy = self._parse_ai_response(content)
                    self.current_strategy = strategy
                    self.last_analysis = datetime.now()
                    self._save_strategy()
                    
                    logger.info(f"👑 Analysis complete: {strategy.market_condition}, confidence: {strategy.confidence}%")
                    return strategy
                else:
                    error_text = response.text[:200]
                    logger.error(f"👑 API error {response.status_code}: {error_text}")
                    return self._default_strategy()
                    
        except httpx.TimeoutException:
            logger.error("👑 API timeout (60s)")
            return self._default_strategy()
        except Exception as e:
            logger.error(f"👑 Analysis error: {e}")
            return self._default_strategy()
    
    def _build_analysis_prompt(self, market_data: Dict) -> str:
        """Построить промпт для анализа"""
        
        prices = market_data.get("prices", {})
        whale = market_data.get("whale_metrics", {})
        news = market_data.get("news", [])
        
        prompt = f"""
📊 ТЕКУЩИЕ ДАННЫЕ РЫНКА (UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}):

💰 ЦЕНЫ:
{self._format_prices(prices)}

🐋 WHALE METRICS:
- Fear & Greed Index: {whale.get('fear_greed', 50)}
- Long Ratio: {whale.get('long_ratio', 50)}%
- Short Ratio: {whale.get('short_ratio', 50)}%
- Funding Rate: {whale.get('funding_rate', 0):.4f}%
- OI Change 1h: {whale.get('oi_change_1h', 0):.2f}%
- OI Change 24h: {whale.get('oi_change_24h', 0):.2f}%
- Liquidations Long: ${whale.get('liq_long', 0):,.0f}
- Liquidations Short: ${whale.get('liq_short', 0):,.0f}

📰 НОВОСТИ (последние):
{self._format_news(news)}

🎯 ЗАДАЧА:
Проанализируй данные и реши:
1. Какое сейчас состояние рынка? (sideways/bullish/bearish/high_vol/dangerous)
2. Какой режим для Grid Bot? (боковик = aggressive, тренд = balanced/conservative)
3. Включить Funding Scalper? (высокий funding rate = да)
4. Включить Technical Analysis? (явный тренд = да)

Учти:
- Grid Bot лучше работает в боковике (sideways)
- При высокой волатильности лучше отключить Grid
- Director AI работает независимо от твоих решений
- Если F&G < 25 или > 75 — осторожность!
"""
        return prompt
    
    def _format_prices(self, prices: Dict) -> str:
        """Форматировать цены для промпта"""
        if not prices:
            return "- Нет данных о ценах"
        
        lines = []
        for symbol, price in prices.items():
            if isinstance(price, (int, float)):
                lines.append(f"- {symbol}: ${price:,.2f}")
            else:
                lines.append(f"- {symbol}: {price}")
        return "\n".join(lines) if lines else "- Нет данных"
    
    def _format_news(self, news: List) -> str:
        """Форматировать новости для промпта"""
        if not news:
            return "- Нет важных новостей"
        
        lines = []
        for n in news[:5]:  # Последние 5
            sentiment = n.get("sentiment", 0)
            if isinstance(sentiment, str):
                sentiment = 0.5 if sentiment == "bullish" else -0.5 if sentiment == "bearish" else 0
            emoji = "📈" if sentiment > 0.2 else "📉" if sentiment < -0.2 else "➖"
            title = n.get("title", "Unknown")[:60]
            lines.append(f"{emoji} {title}")
        return "\n".join(lines)
    
    def _parse_ai_response(self, content: str) -> MasterStrategy:
        """Парсить JSON ответ от AI"""
        try:
            # Найти JSON в ответе
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                
                now = datetime.now()
                strategy = MasterStrategy(
                    timestamp=now.isoformat(),
                    valid_until=(now + timedelta(minutes=30)).isoformat(),
                    market_condition=data.get("market_condition", "sideways"),
                    confidence=data.get("confidence", 70),
                    reasoning=data.get("reasoning", ""),
                    risk_level=data.get("risk_level", "normal"),
                )
                
                modules = data.get("modules", {})
                
                if "grid" in modules:
                    strategy.grid = ModuleStrategy(
                        enabled=modules["grid"].get("enabled", True),
                        mode=modules["grid"].get("mode", "balanced"),
                        reason=modules["grid"].get("reason", "")
                    )
                
                if "funding" in modules:
                    strategy.funding = ModuleStrategy(
                        enabled=modules["funding"].get("enabled", True),
                        reason=modules["funding"].get("reason", "")
                    )
                
                if "technical" in modules:
                    strategy.technical = ModuleStrategy(
                        enabled=modules["technical"].get("enabled", True),
                        reason=modules["technical"].get("reason", "")
                    )
                
                return strategy
        except json.JSONDecodeError as e:
            logger.error(f"👑 JSON parse error: {e}")
        except Exception as e:
            logger.error(f"👑 Error parsing AI response: {e}")
        
        return self._default_strategy()
    
    def _default_strategy(self) -> MasterStrategy:
        """Стратегия по умолчанию"""
        now = datetime.now()
        return MasterStrategy(
            timestamp=now.isoformat(),
            valid_until=(now + timedelta(minutes=30)).isoformat(),
            market_condition="sideways",
            confidence=50,
            grid=ModuleStrategy(enabled=True, mode="balanced", reason="Default strategy"),
            funding=ModuleStrategy(enabled=True, reason="Default strategy"),
            technical=ModuleStrategy(enabled=True, reason="Default strategy"),
            reasoning="Используется стратегия по умолчанию (AI недоступен или ошибка)",
            risk_level="normal"
        )
    
    def should_analyze(self) -> bool:
        """Пора ли делать новый анализ?"""
        if not self.last_analysis:
            return True
        
        elapsed = (datetime.now() - self.last_analysis).total_seconds()
        return elapsed >= self.ANALYSIS_INTERVAL
    
    def get_module_settings(self, module_name: str) -> Dict:
        """Получить настройки для модуля"""
        if not self.current_strategy:
            return {"enabled": True, "mode": "balanced"}
        
        if module_name == "grid":
            return {
                "enabled": self.current_strategy.grid.enabled,
                "mode": self.current_strategy.grid.mode
            }
        elif module_name == "funding":
            return {"enabled": self.current_strategy.funding.enabled}
        elif module_name == "technical":
            return {"enabled": self.current_strategy.technical.enabled}
        
        return {"enabled": True}
    
    def get_grid_config(self) -> Dict:
        """Получить конфиг Grid Bot на основе режима"""
        if not self.current_strategy:
            mode = "balanced"
        else:
            mode = self.current_strategy.grid.mode
        
        configs = {
            "aggressive": {
                "enabled": True,
                "grid_step_percent": 1.0,
                "grid_count": 10,
                "profit_per_grid": 0.3,
                "description": "Агрессивный: узкие шаги, много уровней"
            },
            "balanced": {
                "enabled": True,
                "grid_step_percent": 1.5,
                "grid_count": 7,
                "profit_per_grid": 0.5,
                "description": "Сбалансированный: средние параметры"
            },
            "conservative": {
                "enabled": True,
                "grid_step_percent": 2.0,
                "grid_count": 5,
                "profit_per_grid": 0.7,
                "description": "Консервативный: широкие шаги, меньше риска"
            },
            "off": {
                "enabled": False,
                "description": "Grid отключён"
            }
        }
        
        return configs.get(mode, configs["balanced"])
    
    def format_notification(self) -> str:
        """Форматировать уведомление для Telegram"""
        if not self.current_strategy:
            return ""
        
        s = self.current_strategy
        
        # Эмодзи для состояния рынка
        condition_emoji = {
            "sideways": "↔️",
            "bullish": "📈",
            "bearish": "📉",
            "high_vol": "⚡",
            "dangerous": "🚨"
        }
        
        condition_text = {
            "sideways": "БОКОВИК",
            "bullish": "РОСТ",
            "bearish": "ПАДЕНИЕ",
            "high_vol": "ВОЛАТИЛЬНОСТЬ",
            "dangerous": "ОПАСНОСТЬ"
        }
        
        # Эмодзи для режима Grid
        grid_emoji = {
            "aggressive": "🔥",
            "balanced": "⚖️",
            "conservative": "🛡️",
            "off": "⏸️"
        }
        
        grid_text = {
            "aggressive": "АГРЕССИВНЫЙ",
            "balanced": "СБАЛАНСИРОВАННЫЙ",
            "conservative": "КОНСЕРВАТИВНЫЙ",
            "off": "ВЫКЛ"
        }
        
        risk_emoji = {
            "low": "🟢",
            "normal": "🟡",
            "elevated": "🟠",
            "high": "🔴"
        }
        
        # Форматируем сообщение
        grid_status = grid_text.get(s.grid.mode, s.grid.mode.upper()) if s.grid.enabled else "ВЫКЛ"
        
        msg = f"""👑 *MASTER STRATEGIST*

{condition_emoji.get(s.market_condition, "📊")} Рынок: *{condition_text.get(s.market_condition, s.market_condition.upper())}*
🎯 Уверенность: *{s.confidence}%*
{risk_emoji.get(s.risk_level, "⚪")} Риск: *{s.risk_level.upper()}*

*Решения по модулям:*

📊 Grid Bot: {grid_emoji.get(s.grid.mode, "📊")} *{grid_status}*
   {s.grid.reason}

💰 Funding: *{"ВКЛ ✅" if s.funding.enabled else "ВЫКЛ ❌"}*
   {s.funding.reason}

📈 Technical: *{"ВКЛ ✅" if s.technical.enabled else "ВЫКЛ ❌"}*
   {s.technical.reason}

💭 *Анализ:*
{s.reasoning}

_Следующий анализ через 30 минут_
_Director AI работает независимо_"""
        
        return msg.strip()
    
    def get_status(self) -> Dict:
        """Получить статус для API/WebApp"""
        if not self.current_strategy:
            return {
                "active": False,
                "last_analysis": None,
                "market_condition": "unknown",
                "modules": {}
            }
        
        return {
            "active": True,
            "last_analysis": self.last_analysis.isoformat() if self.last_analysis else None,
            "market_condition": self.current_strategy.market_condition,
            "confidence": self.current_strategy.confidence,
            "risk_level": self.current_strategy.risk_level,
            "modules": {
                "grid": {
                    "enabled": self.current_strategy.grid.enabled,
                    "mode": self.current_strategy.grid.mode,
                    "reason": self.current_strategy.grid.reason
                },
                "funding": {
                    "enabled": self.current_strategy.funding.enabled,
                    "reason": self.current_strategy.funding.reason
                },
                "technical": {
                    "enabled": self.current_strategy.technical.enabled,
                    "reason": self.current_strategy.technical.reason
                }
            },
            "reasoning": self.current_strategy.reasoning,
            "valid_until": self.current_strategy.valid_until
        }


# Глобальный экземпляр
master_strategist = MasterStrategist()
