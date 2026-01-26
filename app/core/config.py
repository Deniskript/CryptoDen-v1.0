"""
Configuration - Настройки приложения
====================================

Использует Pydantic Settings для загрузки из .env
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # === Telegram ===
    telegram_bot_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    admin_chat_id: Optional[int] = Field(default=None, env="ADMIN_CHAT_ID")
    
    # === Bybit ===
    bybit_api_key: Optional[str] = Field(default=None, env="BYBIT_API_KEY")
    bybit_api_secret: Optional[str] = Field(default=None, env="BYBIT_API_SECRET")
    bybit_testnet: bool = Field(default=False, env="BYBIT_TESTNET")  # False = mainnet
    
    # === AI ===
    openrouter_api_key: Optional[str] = Field(default=None, env="OPENROUTER_API_KEY")
    ai_model: str = Field(default="anthropic/claude-3.5-sonnet", env="AI_MODEL")
    parsing_ai_model: str = Field(
        default="liquid/lfm-2.5-1.2b-instruct:free",  # БЕСПЛАТНАЯ модель для парсинга
        env="PARSING_AI_MODEL"
    )
    
    # === News & Calendar ===
    cryptocompare_api_key: Optional[str] = Field(default=None, env="CRYPTOCOMPARE_API_KEY")
    coingecko_api_key: Optional[str] = Field(default=None, env="COINGECKO_API_KEY")
    news_check_interval: int = Field(default=300, env="NEWS_CHECK_INTERVAL")  # 5 минут
    
    # === Redis ===
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    # === PostgreSQL ===
    db_host: str = Field(default="localhost", env="DB_HOST")
    db_port: int = Field(default=5432, env="DB_PORT")
    db_name: str = Field(default="crypto_bot", env="DB_NAME")
    db_user: str = Field(default="postgres", env="DB_USER")
    db_password: str = Field(default="", env="DB_PASSWORD")
    
    # === Trading ===
    auto_trading_enabled: bool = Field(default=False, env="AUTO_TRADING_ENABLED")
    default_position_size_usdt: float = Field(default=100.0, env="DEFAULT_POSITION_SIZE_USDT")
    
    # === App ===
    debug: bool = Field(default=False, env="DEBUG")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}"
        return f"redis://{self.redis_host}:{self.redis_port}"
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


# Глобальный экземпляр
settings = Settings()
