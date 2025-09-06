"""Utility functions for the ExpertOption API"""
import asyncio
import time
import uuid
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union, Callable, Coroutine
import pandas as pd
from .constants import TIMEFRAMES, CURRENCIES, ASSETS, get_asset_id, get_asset_symbol
from .models import Candle, OrderResult
from loguru import logger

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

def sanitize_symbol(symbol: str) -> str:
    s = str(symbol or "").strip().upper().replace(" ", "").replace("-", "")
    # Normalize OTC suffix to server's lower-case shape if needed elsewhere (client handles)
    return s

def format_session_id(token: str) -> str:
    if not token:
        return ""
    return f"{token[:6]}...{token[-4:]}" if len(token) > 12 else token

def timestamp_to_datetime(ts: Union[int, float]) -> datetime:
    return datetime.fromtimestamp(float(ts))

def now_ms() -> int:
    import time as _t
    return int(_t.time() * 1000)

def ensure_asset_id(asset: Union[int, str]) -> int:
    """
    Accept int asset_id or symbol string; always return numeric ID (ID-centric).
    """
    if isinstance(asset, int):
        return asset
    aid = get_asset_id(str(asset))
    if aid is None:
        raise ValueError(f"Unknown asset symbol: {asset}")
    return int(aid)

def format_initial_message(token: str, is_demo: bool) -> str:
    """
    Build multipleAction bootstrap message (kept compatible with original structure).
    """
    import uuid
    actions = [
        {"action": "userGroup", "ns": str(uuid.uuid4()), "token": token},
        {"action": "profile", "ns": str(uuid.uuid4()), "token": token},
        {"action": "assets", "ns": str(uuid.uuid4()), "token": token},
        {"action": "getCurrency", "ns": str(uuid.uuid4()), "token": token},
        {"action": "getCountries", "ns": str(uuid.uuid4()), "token": token},
        {"action": "environment", "message": {"supportedFeatures": [], "supportedAbTests": [], "supportedInventoryItems": []}, "ns": str(uuid.uuid4()), "token": token},
        {"action": "defaultSubscribeCandles", "message": {"timeframes": [0, 5, 60]}, "ns": str(uuid.uuid4()), "token": token},
        {"action": "setTimeZone", "message": {"timeZone": 180}, "ns": str(uuid.uuid4()), "token": token},
        {"action": "getCandlesTimeframes", "ns": str(uuid.uuid4()), "token": token},
    ]
    return json.dumps({"action": "multipleAction", "message": {"actions": actions}, "token": token, "ns": str(uuid.uuid4())})

def resolve_currency(profile: dict, currencies: Optional[dict]) -> str:
    try:
        cur = (profile or {}).get("currency") or (profile or {}).get("currency_id")
        if isinstance(cur, str) and cur.strip():
            cur_code = cur.strip().upper()
            return cur_code if not currencies else (cur_code if cur_code in currencies else "USD")
    except Exception:
        pass
    return "USD"

def calculate_payout_percentage(entry_price: float, exit_price: float, direction: str, payout_rate: float = 0.8) -> float:
    if direction.lower() == "call":
        win = exit_price > entry_price
    else:
        win = exit_price < entry_price
    return payout_rate if win else -1.0

def analyze_candles(candles: List[Candle], exp_times: Optional[List[Any]] = None) -> Dict[str, Any]:
    if not candles:
        return {}
    prices = [candle.close for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    result = {
        "count": len(candles),
        "first_price": prices[0],
        "last_price": prices[-1],
        "price_change": prices[-1] - prices[0],
        "price_change_percent": ((prices[-1] - prices[0]) / prices[0]) * 100,
        "highest": max(highs),
        "lowest": min(lows),
        "average_close": sum(prices) / len(prices),
        "volatility": calculate_volatility(prices),
        "trend": determine_trend(prices),
    }
    if exp_times:
        payout_data = []
        for exp_time in exp_times:
            if len(exp_time) >= 3:
                timestamp, _, rates = exp_time
                for rate in rates:
                    strike_price, call_payout, put_payout, _ = rate
                    payout_data.append({
                        "timestamp": timestamp_to_datetime(timestamp),
                        "strike_price": strike_price,
                        "call_payout": call_payout,
                        "put_payout": put_payout,
                    })
        result["payout_data"] = payout_data
    return result

def calculate_volatility(prices: List[float], periods: int = 14) -> float:
    if len(prices) < periods:
        periods = len(prices)
    recent_prices = prices[-periods:]
    mean = sum(recent_prices) / len(recent_prices)
    variance = sum((price - mean) ** 2 for price in recent_prices) / len(recent_prices)
    return variance ** 0.5

def determine_trend(prices: List[float], periods: int = 10) -> str:
    if len(prices) < periods:
        periods = len(prices)
    if periods < 2:
        return "sideways"
    recent_prices = prices[-periods:]
    first_half = recent_prices[: periods // 2]
    second_half = recent_prices[periods // 2 :]
    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)
    change_percent = ((second_avg - first_avg) / first_avg) * 100
    if change_percent > 0.1:
        return "bullish"
    elif change_percent < -0.1:
        return "bearish"
    else:
        return "sideways"

def calculate_support_resistance(candles: List[Candle], periods: int = 20) -> Dict[str, float]:
    if len(candles) < periods:
        periods = len(candles)
    recent_candles = candles[-periods:]
    highs = [candle.high for candle in recent_candles]
    lows = [candle.low for candle in recent_candles]
    resistance = max(highs)
    support = min(lows)
    return {"support": support, "resistance": resistance, "range": resistance - support}

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

def validate_asset_symbol(symbol: str, available_assets: Dict[str, int]) -> bool:
    return symbol in available_assets

def calculate_order_expiration(duration_seconds: int, current_time: Optional[datetime] = None) -> datetime:
    if current_time is None:
        current_time = datetime.now()
    return current_time + timedelta(seconds=duration_seconds)

async def retry_async(func: Callable[..., Coroutine], *args, attempts: int = 3, delay: float = 0.5, **kwargs):
    last_exc = None
    for i in range(attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if i == attempts - 1:
                break
            await asyncio.sleep(delay)
    if last_exc:
        raise last_exc

def performance_monitor(func):
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"{func.__name__} executed in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
            raise
    return wrapper

class RateLimiter:
    def __init__(self, max_calls: int = 100, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []

    async def acquire(self) -> bool:
        now = time.time()
        self.calls = [call_time for call_time in self.calls if now - call_time < self.time_window]
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        wait_time = self.time_window - (now - self.calls[0])
        if wait_time > 0:
            logger.warning(f"Rate limit exceeded, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            return await self.acquire()
        return True

class OrderManager:
    def __init__(self):
        self.active_orders: Dict[str, OrderResult] = {}
        self.completed_orders: Dict[str, OrderResult] = {}
        self.order_callbacks: Dict[str, List] = {}

    def add_order(self, order: OrderResult) -> None:
        self.active_orders[order.order_id] = order

    def complete_order(self, order_id: str, result: OrderResult) -> None:
        if order_id in self.active_orders:
            del self.active_orders[order_id]
        self.completed_orders[order_id] = result
        if order_id in self.order_callbacks[order_id]:
            for callback in self.order_callbacks[order_id]:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"Error in order callback: {e}")
            del self.order_callbacks[order_id]

    def add_order_callback(self, order_id: str, callback) -> None:
        if order_id not in self.order_callbacks:
            self.order_callbacks[order_id] = []
        self.order_callbacks[order_id].append(callback)

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        if order_id in self.active_orders:
            return self.active_orders[order_id]
        elif order_id in self.completed_orders:
            return self.completed_orders[order_id]
        return None

    def get_active_count(self) -> int:
        return len(self.active_orders)

    def get_completed_count(self) -> int:
        return len(self.completed_orders)

def candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    data = [
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "asset": c.asset,
        }
        for c in candles
    ]
    df = pd.DataFrame(data)
    if not df.empty:
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
    return df
