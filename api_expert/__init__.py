"""
Professional Async API Expert Option - Core module
Fully async implementation with modern Python practices
"""
from .client import AsyncExpertOptionClient
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
)
from .constants import ASSETS, TIMEFRAMES, API_LIMITS, CONNECTION_SETTINGS, CURRENCIES, REGIONS
from .login import get_token, load_config, save_config, save_session, validate_token
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
    candles_to_dataframe,
    retry_async,
    timestamp_to_datetime,
    format_initial_message,
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
    "get_token",
    "load_config",
    "save_config",
    "save_session",
    "validate_token",
    "ErrorMonitor",
    "HealthChecker",
    "ErrorSeverity",
    "ErrorCategory",
    "CircuitBreaker",
    "RetryPolicy",
    "error_monitor",
    "health_checker",
    "sanitize_symbol",
    "format_session_id",
    "candles_to_dataframe",
    "retry_async",
    "timestamp_to_datetime",
    "format_initial_message",
    "ConnectionKeepAlive",
]
