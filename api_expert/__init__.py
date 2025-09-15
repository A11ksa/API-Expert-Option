"""
Professional Async API Expert Option - Core module
Fully async implementation with modern Python practices
"""
from .client import AsyncExpertOptionClient, candles_to_dataframe
from .exceptions import (
    ExpertOptionError,
    ConnectionError,
    AuthenticationError,
    OrderError,
    TimeoutError,
    InvalidParameterError,
    WebSocketError,
    InsufficientFundsError,
)
from .models import (
    Balance,
    Candle,
    Order,
    OrderResult,
    OrderStatus,
    OrderDirection,
    ConnectionStatus,
    ServerTime,
    Asset,
    TradersChoice,
    UserFeedInfo,
    MultipleActionResponse,
    EnvironmentInfo,
    Achievement,
    Badge,
    ActivatedBonus,
    ReferralOfferInfo,
    DepositSum,
    TradeHistoryEntry,
    PushNotification,
)
from .constants import ASSETS, TIMEFRAMES, API_LIMITS, CONNECTION_SETTINGS, CURRENCIES, REGIONS

# Expose the login/config helpers (implemented in config.py for config/session, login.py for token)
from .config import load_config, save_config, save_session, load_session
from .login import get_token, validate_token, expert_get_token

from .monitoring import (
    ErrorMonitor,
    HealthChecker,
    ErrorSeverity,
    ErrorCategory,
    CircuitBreaker,
    RetryPolicy,
    error_monitor,
    health_checker,
)
from .utils import (
    sanitize_symbol,
    format_session_id,
    timestamp_to_datetime,
    format_initial_message,
    format_timeframe,
)
from .connection_keep_alive import ConnectionKeepAlive

__version__ = "2.0.0"
__author__ = "APIExpertOption"
__all__ = [
    "AsyncExpertOptionClient",
    "ExpertOptionError",
    "ConnectionError",
    "AuthenticationError",
    "OrderError",
    "TimeoutError",
    "InvalidParameterError",
    "WebSocketError",
    "InsufficientFundsError",
    "Balance",
    "Candle",
    "Order",
    "OrderResult",
    "OrderStatus",
    "OrderDirection",
    "ConnectionStatus",
    "ServerTime",
    "Asset",
    "ASSETS",
    "TIMEFRAMES",
    "API_LIMITS",
    "CONNECTION_SETTINGS",
    "CURRENCIES",
    "REGIONS",
    # login/config helpers
    "get_token",
    "expert_get_token",
    "validate_token",
    "load_config",
    "save_config",
    "save_session",
    "load_session",
    # monitoring
    "ErrorMonitor",
    "HealthChecker",
    "ErrorSeverity",
    "ErrorCategory",
    "CircuitBreaker",
    "RetryPolicy",
    "error_monitor",
    "health_checker",
    # utils
    "sanitize_symbol",
    "format_session_id",
    "candles_to_dataframe",
    "timestamp_to_datetime",
    "format_initial_message",
    "format_timeframe",
    # connection keep alive
    "ConnectionKeepAlive",
    # new exports
    "TradersChoice",
    "UserFeedInfo",
    "MultipleActionResponse",
    "EnvironmentInfo",
    "Achievement",
    "Badge",
    "ActivatedBonus",
    "ReferralOfferInfo",
    "DepositSum",
    "TradeHistoryEntry",
    "PushNotification",
]
