"""
🔍 Parsers Module — Парсинг данных из внешних источников

Модули:
- twitter_parser: Парсинг Twitter через Nitter (киты, новости)
- rss_parser: Агрегация крипто новостей из RSS фидов
- coinglass_parser: Ликвидации, Open Interest, Funding Rate
"""

from app.parsers.twitter_parser import (
    TwitterParser,
    twitter_parser,
    WhaleTransaction,
    TwitterNews,
    get_whale_data,
    get_twitter_news,
)

from app.parsers.rss_parser import (
    RSSParser,
    rss_parser,
    NewsItem,
    get_latest_news,
    get_news_summary,
)

from app.parsers.coinglass_parser import (
    CoinglassParser,
    coinglass_parser,
    LiquidationData,
    OpenInterestData,
    FundingData,
    get_market_data,
    get_liquidations,
    get_open_interest,
    get_funding,
)

__all__ = [
    # Twitter
    'TwitterParser',
    'twitter_parser',
    'WhaleTransaction',
    'TwitterNews',
    'get_whale_data',
    'get_twitter_news',
    # RSS
    'RSSParser',
    'rss_parser',
    'NewsItem',
    'get_latest_news',
    'get_news_summary',
    # Coinglass
    'CoinglassParser',
    'coinglass_parser',
    'LiquidationData',
    'OpenInterestData',
    'FundingData',
    'get_market_data',
    'get_liquidations',
    'get_open_interest',
    'get_funding',
]
