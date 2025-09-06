"""Custom exceptions for the ExpertOption API"""
import time
from typing import Optional
from loguru import logger

# Logging (keep your existing style)
logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

__all__ = [
    "ExpertOptionError",
    "ConnectionError",
    "AuthenticationError",
    "OrderError",
    "TimeoutError",
    "InvalidParameterError",
    "WebSocketError",
    "InsufficientFundsError",
    "Base64DecodeError",
]

class ExpertOptionError(Exception):
    """Base class for Expert Option API errors."""
    def __init__(self, message: str, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        # Log once at creation (matches original intent)
        if error_code:
            logger.error(f"ExpertOptionError: {message} (Code: {error_code})")
        else:
            logger.error(f"ExpertOptionError: {message}")
    def __str__(self) -> str:
        return f"{self.message} (Code: {self.error_code})" if self.error_code else self.message

class ConnectionError(ExpertOptionError):
    """Raised for transport/connection errors."""
    pass

class AuthenticationError(ExpertOptionError):
    """Raised for authentication/login/token errors."""
    pass

class OrderError(ExpertOptionError):
    """Raised for order placement/validation errors."""
    pass

class TimeoutError(ExpertOptionError):
    """Raised when an operation exceeds the allowed time."""
    pass

class InvalidParameterError(ExpertOptionError):
    """Raised for invalid or missing parameters."""
    pass

class WebSocketError(ExpertOptionError):
    """Raised for websocket protocol/stream errors."""
    pass

class InsufficientFundsError(ExpertOptionError):
    """Raised when balance is insufficient to place an order."""
    def __init__(self, message: str = "Insufficient funds for order", error_code: str = "not_money") -> None:
        super().__init__(message, error_code)

class Base64DecodeError(ExpertOptionError):
    """Raised when a base64 message cannot be decoded."""
    def __init__(self, message: str = "Failed to decode base64 message", error_code: str = "base64_decode") -> None:
        super().__init__(message, error_code)
