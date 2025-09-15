"""Lightweight helpers for ExpertOption API integration."""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import Optional, Union, Dict, Any

def sanitize_symbol(symbol: str) -> str:
    """Return a normalized asset symbol (uppercased, no spaces or dashes)."""
    return str(symbol or "").strip().upper().replace(" ", "").replace("-", "")

def format_session_id(token: str) -> str:
    """Shorten long session tokens for logging."""
    return f"{token[:6]}...{token[-4:]}" if token and len(token) > 12 else token or ""

def timestamp_to_datetime(ts: Union[int, float]) -> datetime:
    """Convert a UNIX timestamp to ``datetime``."""
    return datetime.fromtimestamp(float(ts))
    
def format_initial_message(token: str, is_demo: bool) -> str:
    """Build the websocket bootstrap message used during connection setup."""
    actions = [
        {"action": "userGroup", "ns": str(uuid.uuid4()), "token": token},
        {"action": "profile", "ns": str(uuid.uuid4()), "token": token},
        {"action": "assets", "ns": str(uuid.uuid4()), "token": token},
        {"action": "getCurrency", "ns": str(uuid.uuid4()), "token": token},
        {"action": "getCountries", "ns": str(uuid.uuid4()), "token": token},
        {
            "action": "environment",
            "message": {"supportedFeatures": [], "supportedAbTests": [], "supportedInventoryItems": []},
            "ns": str(uuid.uuid4()),
            "token": token,
        },
        {"action": "defaultSubscribeCandles", "message": {"timeframes": [0, 5, 60]}, "ns": str(uuid.uuid4()), "token": token},
        {"action": "setTimeZone", "message": {"timeZone": 180}, "ns": str(uuid.uuid4()), "token": token},
        {"action": "getCandlesTimeframes", "ns": str(uuid.uuid4()), "token": token},
    ]
    return json.dumps({"action": "multipleAction", "message": {"actions": actions}, "token": token, "ns": str(uuid.uuid4())})

def resolve_currency(profile: dict, currencies: Optional[dict]) -> str:
    """Extract the account currency code with graceful fallbacks."""
    try:
        cur = (profile or {}).get("currency") or (profile or {}).get("currency_id")
        if isinstance(cur, str) and cur.strip():
            cur_code = cur.strip().upper()
            return cur_code if not currencies else (cur_code if cur_code in currencies else "USD")
    except Exception:
        pass
    return "USD"

def format_timeframe(value: int | str) -> str:
    tf_map = {
        60: "1m", 120: "2m", 180: "3m", 300: "5m", 420: "7m",
        600: "10m", 900: "15m", 1200: "20m", 1800: "30m",
        2700: "45m", 3600: "1h", 7200: "2h", 10800: "3h", 14400: "4h"
    }
    if isinstance(value, str):
        v = value.strip().lower()
        if v.endswith("m") or v.endswith("h"):
            return v
        try:
            secs = int(float(v))
            return tf_map.get(secs, f"{secs}s")
        except Exception:
            return v
    try:
        secs = int(value)
        return tf_map.get(secs, f"{secs}s")
    except Exception:
        return "1m"

__all__ = [
    "sanitize_symbol",
    "format_session_id",
    "timestamp_to_datetime",
    "format_initial_message",
    "resolve_currency",
    "format_timeframe",
]
