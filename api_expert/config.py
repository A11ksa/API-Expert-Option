"""Configuration file for the async ExpertOption API."""
import os
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional
from loguru import logger
from threading import Lock

# Keep original logger behavior
logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

@dataclass
class ConnectionConfig:
    ping_interval: int = 25
    ping_timeout: int = 5
    close_timeout: int = 10
    max_reconnect_attempts: int = 5
    reconnect_delay: int = 5
    message_timeout: int = 30

@dataclass
class TradingConfig:
    min_order_amount: float = 1.0
    max_order_amount: float = 50000.0
    min_duration: int = 30
    max_duration: int = 14400
    max_concurrent_orders: int = 10
    default_timeout: float = 30.0

@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = ("{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}")
    rotation: str = "1 day"
    retention: str = "7 days"
    log_file: str = f"log-{time.strftime('%Y-%m-%d')}.txt"

class Config:
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, resource_path: str = "sessions"):
        if hasattr(self, '_initialized') and self._initialized:
            logger.debug("Config instance already initialized, skipping redundant initialization")
            return
        # Anchor relative resource_path to package root (parent of this file's directory)
        base = Path(resource_path)
        if not base.is_absolute():
            base = Path(__file__).resolve().parents[1] / base
        self.resource_path = base
        self.config_file = self.resource_path / "config.json"
        self.session_file = self.resource_path / "session.json"
        self.connection = ConnectionConfig()
        self.trading = TradingConfig()
        self.logging = LoggingConfig()
        # Extended session schema for ExpertOption to match login.py
        self.session_data: Dict[str, Any] = {
            "token": None,
            "is_demo": 1,
            "ts": None
        }
        self._config_data: Dict[str, Any] = {
            "email": None,
            "password": None,
            "lang": "en",
            "user_data_dir": "."
        }
        self._session_loaded = False
        self._config_loaded = False
        self.resource_path.mkdir(parents=True, exist_ok=True)
        self._load_from_env()
        self._load_config()
        self._load_session()
        self._initialized = True
        logger.info("Config instance initialized successfully")

    def _load_from_env(self):
        """Load configuration from environment variables."""
        try:
            self.connection.ping_interval = int(os.getenv("PING_INTERVAL", self.connection.ping_interval))
            self.connection.ping_timeout = int(os.getenv("PING_TIMEOUT", self.connection.ping_timeout))
            self.connection.max_reconnect_attempts = int(os.getenv("MAX_RECONNECT_ATTEMPTS", self.connection.max_reconnect_attempts))
            self.trading.min_order_amount = float(os.getenv("MIN_ORDER_AMOUNT", self.trading.min_order_amount))
            self.trading.max_order_amount = float(os.getenv("MAX_ORDER_AMOUNT", self.trading.max_order_amount))
            self.trading.default_timeout = float(os.getenv("DEFAULT_TIMEOUT", self.trading.default_timeout))
            self.logging.level = os.getenv("LOG_LEVEL", self.logging.level)
            self.logging.log_file = os.getenv("LOG_FILE", self.logging.log_file)
            # Load credentials for login.py compatibility
            self._config_data["email"] = os.getenv("EO_EMAIL", self._config_data.get("email"))
            self._config_data["password"] = os.getenv("EO_PASSWORD", self._config_data.get("password"))
        except Exception as e:
            logger.warning(f"Failed to load environment variables: {e}")

    def _load_config(self) -> None:
        """Load configuration from config.json file."""
        with self._lock:
            if self._config_loaded:
                logger.debug("Config already loaded, skipping")
                return
            try:
                if self.config_file.exists():
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        loaded_data = json.load(f)
                        # Only update keys that exist in _config_data to avoid overwriting unexpected fields
                        for key in self._config_data:
                            if key in loaded_data:
                                self._config_data[key] = loaded_data[key]
                    self._config_loaded = True
                    logger.info("Configuration loaded from config.json")
            except Exception as e:
                logger.error(f"Failed to load config file: {e}")
            finally:
                self._config_loaded = True

    def _load_session(self) -> None:
        """Load session data from session.json file."""
        with self._lock:
            if self._session_loaded:
                logger.debug("Session already loaded, skipping")
                return
            try:
                if self.session_file.exists():
                    # Check file age (14 days)
                    file_mtime = os.path.getmtime(self.session_file)
                    current_time = time.time()
                    fourteen_days = 14 * 24 * 60 * 60  # 14 days in seconds
                    if (current_time - file_mtime) > fourteen_days:
                        logger.warning("Session file is older than 14 days, removing")
                        os.remove(self.session_file)
                        self.session_data = {"token": None, "is_demo": 1, "ts": None}
                    else:
                        with open(self.session_file, 'r', encoding='utf-8') as f:
                            loaded_data = json.load(f)
                            # Update session_data with loaded values, preserving schema
                            self.session_data.update({
                                "token": loaded_data.get("token"),
                                "is_demo": loaded_data.get("is_demo", 1),
                                "ts": loaded_data.get("ts")
                            })
                        logger.info("Session loaded from session.json")
                self._session_loaded = True
            except Exception as e:
                logger.error(f"Failed to load session file: {e}")
                self.session_data = {"token": None, "is_demo": 1, "ts": None}
            finally:
                self._session_loaded = True

    def load_config(self) -> Dict[str, Any]:
        """Return a copy of the configuration data."""
        self._load_config()
        return self._config_data.copy()

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration data to config.json."""
        with self._lock:
            try:
                self._config_data.update({
                    k: v for k, v in config.items() if k in self._config_data
                })
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._config_data, f, indent=2, ensure_ascii=False)
                logger.info("Configuration saved to config.json")
            except Exception as e:
                logger.error(f"Failed to save config file: {e}")

    def save_session(self, session_data: Dict[str, Any]) -> None:
        """Save session data to session.json."""
        with self._lock:
            try:
                self.session_data.update({
                    "token": session_data.get("token", self.session_data.get("token")),
                    "is_demo": session_data.get("is_demo", self.session_data.get("is_demo")),
                    "ts": session_data.get("ts", self.session_data.get("ts"))
                })
                with open(self.session_file, 'w', encoding='utf-8') as f:
                    json.dump(self.session_data, f, indent=2, ensure_ascii=False)
                logger.info("Session saved to session.json")
            except Exception as e:
                logger.error(f"Failed to save session file: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Return configuration as a dictionary."""
        return {
            "connection": {
                "ping_interval": self.connection.ping_interval,
                "ping_timeout": self.connection.ping_timeout,
                "close_timeout": self.connection.close_timeout,
                "max_reconnect_attempts": self.connection.max_reconnect_attempts,
                "reconnect_delay": self.connection.reconnect_delay,
                "message_timeout": self.connection.message_timeout,
            },
            "trading": {
                "min_order_amount": self.trading.min_order_amount,
                "max_order_amount": self.trading.max_order_amount,
                "min_duration": self.trading.min_duration,
                "max_duration": self.trading.max_duration,
                "max_concurrent_orders": self.trading.max_concurrent_orders,
                "default_timeout": self.trading.default_timeout,
            },
            "logging": {
                "level": self.logging.level,
                "format": self.logging.format,
                "rotation": self.logging.rotation,
                "retention": self.logging.retention,
                "log_file": self.logging.log_file,
            },
            "user": self._config_data,
            "session": self.session_data
        }

    @property
    def lang(self) -> str:
        """Return the configured language."""
        return self._config_data.get("lang", "en")

    @property
    def user_data_dir(self) -> str:
        """Return the user data directory."""
        return self._config_data.get("user_data_dir", ".")

# Global configuration instance
config = Config()
