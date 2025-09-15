"""Constants for ExpertOption API."""
from __future__ import annotations
import time
import random
from typing import List, Dict, Any, Optional
from .exceptions import InvalidParameterError

# Assets (Symbol -> ID), updated from API data
ASSETS: Dict[str, int] = {
    # Major Forex Pairs (Non-OTC)
    "EURUSD": 142,
    "AUDCAD": 151,
    "AUDJPY": 152,
    "AUDUSD": 153,
    "EURGBP": 154,
    "NZDUSD": 156,
    "USDCAD": 157,
    "USDCHF": 158,
    "EURAUD": 211,
    "EURCHF": 212,
    "GBPCAD": 214,
    "GBPCHF": 216,
    "EURJPY": 217,
    "AUDCHF": 218,
    "AUDNZD": 219,

    # Forex Pairs (OTC)
    "EURUSD_OTC": 245,
    "USDJPY_OTC": 248,
    "GBPUSD_OTC": 250,
    "XAUUSD_OTC": 251,
    "AUDUSD_OTC": 273,
    "USDCAD_OTC": 274,
    "NZDUSD_OTC": 275,
    "UKOIL_OTC": 267,

    # Commodities
    "UKOIL": 177,
    "SILVER_OTC": 268,
    "PLATINUM": 221,
    "COPPER": 247,

    # Cryptocurrencies
    "BTCUSD": 160,
    "ETHUSD": 162,
    "ALTCOIN": 229,
    "TOPCRYPTO": 230,

    # Stock Indices
    "WALLST30": 224,
    "HONGKONG33": 225,
    "GERMANY30": 227,
    "USDX": 233,
    "QQQ": 239,
    "SMRTY": 240,

    # Stocks
    "FB": 189,
    "BABA": 190,
    "GOOG_OTC": 270,
    "AAPL": 192,
    "AMZN": 193,
    "MSFT": 194,
    "TSLA": 195,
    "LMT": 196,
    "YUM": 199,
    "IBM": 200,
    "MCD": 202,
    "DIS": 203,
    "FORD": 204,
    "CITI": 205,
    "GS": 206,
    "COKE": 207,
    "BIDU": 208,
    "NFLX": 209,
    "CSCO": 279,
    "NVDA": 280,
    "XOM": 281,
    "PG": 282,
    "GM": 283,
    "NIKE": 284,
    "INTEL_OTC": 269,
    "META_OTC": 271,

    # OTC Indices
    "INDIA_OTC": 272,
    "CRICKET_OTC": 276,
    "CAMEL_OTC": 277,
    "FOOTBALL_OTC": 278,
    "AI_OTC": 285,
    "LUXURY_OTC": 286,

    # Placeholder
    "UNSUPPORTED": 20000,
}

# Mapping of shortened names to full API symbols (for certain non-forex assets)
SHORT_TO_FULL_NAME: Dict[str, str] = {
    "SILVER_OTC": "SI",
    "PLATINUM": "XPTUSD",
    "ALTCOIN": "ALTCOININDEX",
    "TOPCRYPTO": "TOPCRYPTOINDEX",
    "WALLST30": "USWALLST30",
    "HONGKONG33": "HONGKONG33",
    "GERMANY30": "GERMANY30",
    "QQQ": "USINDEX100",
    "SMRTY": "SMRTY",
    "FORD": "F",
    "CITI": "C",
    "GS": "GS",
    "COKE": "KO",
    "INTEL_OTC": "INTEL",
    "META_OTC": "META",
    "INDIA_OTC": "INDIAN_INDEX_OTC_R",
    "CRICKET_OTC": "CRICKET_INDEX_OTC_R",
    "CAMEL_OTC": "CAMEL_RACE_INDEX_OTC_R",
    "FOOTBALL_OTC": "FOOTBALL_INDEX_OTC_R",
    "AI_OTC": "AI_INDEX_OTC_R",
    "LUXURY_OTC": "LUXURY_INDEX_OTC_R",
    "UNSUPPORTED": "NOTSUPPORTEDBYCLIENT",
}

# Reverse mapping for ID-centric usage (ID -> short symbol)
ASSETS_ID_SYMBOL: Dict[int, str] = {}
def _rebuild_reverse_assets() -> None:
    ASSETS_ID_SYMBOL.clear()
    for sym, aid in ASSETS.items():
        try:
            ASSETS_ID_SYMBOL[int(aid)] = sym
        except Exception:
            continue
_rebuild_reverse_assets()

def update_assets_from_api(api_assets: List[Dict[str, Any]]) -> None:
    """Extend the ASSETS map from server payload, mapping API symbols to shortened names."""
    changed = False
    for a in api_assets or []:
        try:
            full_sym = str(a.get("symbol") or "").strip()
            aid = int(a.get("id"))
            short_sym = next((short for short, full in SHORT_TO_FULL_NAME.items() if full == full_sym), full_sym)
            if short_sym and aid and ASSETS.get(short_sym) != aid:
                ASSETS[short_sym] = aid
                changed = True
        except Exception:
            continue
    if changed:
        _rebuild_reverse_assets()

def get_asset_id(symbol: str) -> Optional[int]:
    try:
        return ASSETS.get(str(symbol).upper())
    except Exception:
        return None

def get_asset_symbol(asset_id: int) -> Optional[str]:
    try:
        return ASSETS_ID_SYMBOL.get(int(asset_id))
    except Exception:
        return None

def get_full_symbol(short_symbol: str) -> Optional[str]:
    try:
        return SHORT_TO_FULL_NAME.get(str(short_symbol).upper(), short_symbol.upper())
    except Exception:
        return None

class Regions:
    """WebSocket region endpoints for ExpertOption."""
    _REGIONS = {
        "EUROPE": "wss://fr24g1eu.expertoption.com/",
        "INDIA": "wss://fr24g1in.expertoption.com/",
        "HONG_KONG": "wss://fr24g1hk.expertoption.com/",
        "SINGAPORE": "wss://fr24g1sg.expertoption.com/",
        "UNITED_STATES": "wss://fr24g1us.expertoption.com/",
    }

    @classmethod
    def get_all(cls, randomize: bool = True) -> List[str]:
        urls = list(cls._REGIONS.values())
        if randomize:
            random.shuffle(urls)
        return urls

    @classmethod
    def get_all_regions(cls) -> Dict[str, str]:
        return cls._REGIONS.copy()

    @classmethod
    def get_region(cls, region_name: str) -> Optional[str]:
        return cls._REGIONS.get(str(region_name or "").upper())

    @classmethod
    def get_demo_regions(cls) -> List[str]:
        return list(cls._REGIONS.values())

# Global instance
REGIONS = Regions()

# Timeframes in seconds (canonical)
TIMEFRAMES: Dict[str, int] = {
    "1m": 60,
    "2m": 120,
    "3m": 180,
    "5m": 300,
    "7m": 420,
    "10m": 600,
    "15m": 900,
    "20m": 1200,
    "30m": 1800,
    "45m": 2700,
    "1h": 3600,
    "2h": 7200,
    "3h": 10800,
    "4h": 14400,
}

# Seconds -> label helper for formatting
_TIMEFRAME_LABELS: Dict[int, str] = {v: k for k, v in TIMEFRAMES.items()}
def format_timeframe(tf_seconds: int) -> str:
    return _TIMEFRAME_LABELS.get(int(tf_seconds), f"{int(tf_seconds)}s")

# Misc constants
CURRENCIES: Dict[str, Dict[str, Any]] = {
    "USD": {"code": "USD", "symbol": "$", "precision": 2},
    "EUR": {"code": "EUR", "symbol": "€", "precision": 2},
    "GBP": {"code": "GBP", "symbol": "£", "precision": 2},
    "RUB": {"code": "RUB", "symbol": "₽", "precision": 2},
    "INR": {"code": "INR", "symbol": "₹", "precision": 2},
    "SAR": {"code": "SAR", "symbol": "﷼", "precision": 2},
    "AED": {"code": "AED", "symbol": "د.إ", "precision": 2},
}

CONNECTION_SETTINGS = {
    "ping_interval": 20,
    "ping_timeout": 10,
    "close_timeout": 10,
    "max_reconnect_attempts": 5,
    "reconnect_delay": 5,
    "message_timeout": 30,
}

API_LIMITS = {
    "min_order_amount": 1.0,
    "max_order_amount": 50000.0,
    "min_duration": 5,
    "max_duration": 43200,
    "max_concurrent_orders": 10,
    "rate_limit": 100,
}

# Updated list with all server actions
WS_MESSAGE_TYPES = {
    # Framework / session
    "multipleAction": "multipleAction",
    "profile": "profile",
    "userGroup": "userGroup",
    "error": "error",
    "getOneTimeToken": "getOneTimeToken",
    "setContext": "setContext",
    "setTimeZone": "setTimeZone",
    "getCandlesTimeframes": "getCandlesTimeframes",
    "getCurrency": "getCurrency",
    "getCountries": "getCountries",
    "environment": "environment",
    "setConversionData": "setConversionData",

    # Assets & market data
    "assets": "assets",
    "candles": "candles",
    "assetHistoryCandles": "assetHistoryCandles",
    "defaultSubscribeCandles": "defaultSubscribeCandles",
    "subscribeCandles": "subscribeCandles",
    "tradersChoice": "tradersChoice",
    "expertOption": "expertOption",
    "expertSubscribe": "expertSubscribe",

    # Orders & results
    "buyOption": "buyOption",
    "buySuccessful": "buySuccessful",
    "openTradeSuccessful": "openTradeSuccessful",
    "closeTradeSuccessful": "closeTradeSuccessful",
    "optionFinished": "optionFinished",
    "tradesStatus": "tradesStatus",
    "cancelOption": "cancelOption",

    # Account / user meta
    "userFeedInfo": "userFeedInfo",
    "userAchievements": "userAchievements",
    "userBadges": "userBadges",
    "activatedBonuses": "activatedBonuses",
    "userDepositSum": "userDepositSum",
    "referralOfferInfo": "referralOfferInfo",
    "tradeHistory": "tradeHistory",
    "promoOpen": "promoOpen",
    "checkPushNotifications": "checkPushNotifications",

    # Ping/Pong
    "ping": "ping",
    "pong": "pong",
}

DEFAULT_HEADERS = {
    "Origin": "https://app.expertoption.com",
    "Referer": "https://app.expertoption.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
}
