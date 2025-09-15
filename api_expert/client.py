"""Professional Async ExpertOption API Client – Unified & Cleaned."""
# Imports
import asyncio
import json
import time
import uuid
from typing import Dict, List, Any, Callable, Optional, Union, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
from loguru import logger

from .monitoring import error_monitor, health_checker, ErrorCategory, ErrorSeverity
from .websocket_client import AsyncWebSocketClient
from .models import (
    Balance,
    Candle,
    Order,
    OrderResult,
    OrderStatus,
    OrderDirection,
    ConnectionStatus,
    ServerTime,
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
from .constants import (
    ASSETS,
    REGIONS,
    TIMEFRAMES,
    API_LIMITS,
    WS_MESSAGE_TYPES,
    get_asset_symbol,
    ASSETS_ID_SYMBOL,
    update_assets_from_api,
    get_full_symbol,
)
from .exceptions import ConnectionError, AuthenticationError, OrderError, InvalidParameterError
from .utils import (
    sanitize_symbol,
    format_session_id,
    format_initial_message,
    resolve_currency,
    format_timeframe,  # Add this line
)

# Logging setup
logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

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

class _ConnectionState:
    def __init__(self, getter: Callable[[], bool]):
        self._getter = getter
    def __bool__(self) -> bool:
        return self._getter()
    def __call__(self) -> bool:
        return self._getter()

class AsyncExpertOptionClient:
    """Professional async ExpertOption API client with modern Python practices"""

    # region Initialization and Setup
    def __init__(
        self,
        token: str,
        is_demo: bool = True,
        region: Optional[str] = None,
        uid: int = 0,
        is_fast_history: bool = True,
        persistent_connection: bool = False,
        auto_reconnect: bool = True,
        enable_logging: bool = True,
    ):
        self.raw_token = token
        self.token = token
        self.is_demo = is_demo
        self.preferred_region = region
        self.uid = uid
        self.is_fast_history = is_fast_history
        self.persistent_connection = persistent_connection
        self.auto_reconnect = auto_reconnect
        self.enable_logging = enable_logging

        self._websocket = AsyncWebSocketClient()

        # Balances
        self._balance: Optional[Balance] = None
        self._balance_demo: Optional[Balance] = None
        self._balance_real: Optional[Balance] = None

        # Orders
        self._orders: Dict[str, OrderResult] = {}
        self._active_orders: Dict[str, OrderResult] = {}
        self._order_results: Dict[str, OrderResult] = {}
        self._pending_order_requests: Dict[str, Order] = {}
        self._pending_fingerprints: Dict[tuple, str] = {}
        self._pending_ns: Dict[str, str] = {}
        self._order_state: Dict[int, Dict[str, Any]] = {}

        # Assets / Candles / Requests
        self._candles_cache: Dict[str, List[Candle]] = {}
        self._assets_data: Dict[str, Dict[str, Any]] = {}
        self._assets_requests: Dict[str, asyncio.Future] = {}
        self._candle_requests: Dict[str, asyncio.Future] = {}
        self._balance_requests: Dict[str, asyncio.Future] = {}
        self._payout_data: Dict[str, float] = {}
        self._traders_choice: Dict[int, TradersChoice] = {}
        self._user_feed_info: Optional[UserFeedInfo] = None
        self._environment_info: Optional[EnvironmentInfo] = None
        self._server_time: Optional[ServerTime] = None
        self._event_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self._request_id_to_server_id: Dict[str, str] = {}

        # New stores for new actions
        self._achievements: List[Achievement] = []
        self._badges: List[Badge] = []
        self._bonuses: List[ActivatedBonus] = []
        self._deposit_sum: Optional[DepositSum] = None
        self._referral_info: Optional[ReferralOfferInfo] = None
        self._trade_history: List[TradeHistoryEntry] = []
        self._push_notifications: List[PushNotification] = []
        self._promo_open_payload: Optional[Dict[str, Any]] = None

        # Fast candle pipeline
        self._live_last: Dict[str, Dict[str, float]] = {}
        self._ring_limit: int = 600
        self._candle_stream_subs: Dict[str, asyncio.Queue] = {}
        self._tick_counts: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._active_subscriptions: Set[Tuple[int, int]] = set()

        # Asset readiness synchronization (to prevent race conditions)
        self._asset_ready: defaultdict[int, asyncio.Event] = defaultdict(asyncio.Event)
        self._assets_index_ready: asyncio.Event = asyncio.Event()

        self._setup_event_handlers()

        self._error_monitor = error_monitor
        self._health_checker = health_checker
        self._operation_metrics: Dict[str, List[float]] = defaultdict(list)
        self._last_health_check = time.time()
        self._last_assets_update = 0
        self._keep_alive_manager = None
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._assets_update_task: Optional[asyncio.Task] = None
        self._is_persistent = False
        self.websocket_is_connected = False

        self.is_connected = _ConnectionState(self._check_connected)
        self._connection_stats = {
            "total_connections": 0,
            "successful_connections": 0,
            "total_reconnects": 0,
            "last_ping_time": None,
            "messages_sent": 0,
            "messages_received": 0,
            "connection_start_time": None,
        }

        self._auth_emitted: bool = False

        logger.info(
            f"Initialized ExpertOption client (demo={is_demo}, persistent={persistent_connection}) with enhanced monitoring"
            if enable_logging else ""
        )

    def _setup_event_handlers(self):
        """Setup WebSocket event handlers"""
        self._websocket.add_event_handler('token', self._on_token)
        self._websocket.add_event_handler('authenticated', self._on_authenticated)
        self._websocket.add_event_handler('multipleAction', self._on_multiple_action)
        self._websocket.add_event_handler('assets', self._on_assets)
        self._websocket.add_event_handler('balance_updated', self._on_balance_updated)
        self._websocket.add_event_handler('balance_data', self._on_balance_data)
        self._websocket.add_event_handler('order_opened', self._on_order_opened)
        self._websocket.add_event_handler('order_closed', self._on_order_closed)
        self._websocket.add_event_handler('stream_update', self._on_stream_update)
        self._websocket.add_event_handler('candles_received', self._on_candles_received)
        self._websocket.add_event_handler('assets_updated', self._on_assets_updated)
        self._websocket.add_event_handler('price_update', self._on_price_update)
        self._websocket.add_event_handler('tradersChoice', self._on_traders_choice)
        self._websocket.add_event_handler('userFeedInfo', self._on_user_feed_info)
        self._websocket.add_event_handler('json_data', self._on_json_data)
        self._websocket.add_event_handler('error', self._on_error)
    # endregion

    # region Connection Management
    async def connect(self, regions: Optional[List[str]] = None, persistent: Optional[bool] = None) -> bool:
        logger.info("Connecting to ExpertOption...")
        if persistent is not None:
            self.persistent_connection = persistent
        try:
            self.websocket_is_connected = False
            if self.persistent_connection:
                return await self._start_persistent_connection(regions)
            else:
                return await self._start_regular_connection(regions)
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            await self._error_monitor.record_error(
                error_type="connection_failed",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.CONNECTION,
                message=f"Connection failed: {e}",
            )
            return False

    async def _start_regular_connection(self, regions: Optional[List[str]] = None) -> bool:
        logger.info("Starting regular connection...")
        if not regions:
            regions = list(REGIONS.get_all_regions().keys())
        self._connection_stats["total_connections"] += 1
        self._connection_stats["connection_start_time"] = time.time()
        for region in regions:
            try:
                region_url = REGIONS.get_region(region)
                if not region_url:
                    logger.warning(f"Region '{region}' has no URL. Skipping.")
                    continue
                success = await self._websocket.connect([region_url], initial_message=None)
                if not success:
                    logger.warning(f"WebSocket connect failed for region '{region}', trying next.")
                    continue

                await self._send_set_context()
                initial_message = format_initial_message(self.token, self.is_demo)
                await self._websocket.send_message(initial_message)
                await self._request_balance_update()
                await asyncio.sleep(0.2)
                await self._start_keep_alive_tasks()
                self._connection_stats["successful_connections"] += 1
                self.websocket_is_connected = True
                logger.info("WebSocket connected successfully")
                return True
            except Exception as e:
                logger.warning(f"Failed to connect to region {region}: {e}")
                continue
        return False

    async def _start_persistent_connection(self, urls: Optional[List[str]]) -> bool:
        logger.info("Starting persistent connection with automatic keep-alive...")
        from .connection_keep_alive import ConnectionKeepAlive
        self._keep_alive_manager = ConnectionKeepAlive(self.token, self.is_demo)
        # wire all known events
        self._keep_alive_manager.add_event_handler('connected', self._on_keep_alive_connected)
        self._keep_alive_manager.add_event_handler('reconnected', self._on_keep_alive_reconnected)
        self._keep_alive_manager.add_event_handler('message_received', self._on_keep_alive_message)
        self._keep_alive_manager.add_event_handler('authenticated', self._on_authenticated)
        self._keep_alive_manager.add_event_handler('multipleAction', self._on_multiple_action)
        self._keep_alive_manager.add_event_handler('balance_data', self._on_balance_data)
        self._keep_alive_manager.add_event_handler('balance_updated', self._on_balance_updated)
        self._keep_alive_manager.add_event_handler('order_opened', self._on_order_opened)
        self._keep_alive_manager.add_event_handler('order_closed', self._on_order_closed)
        self._keep_alive_manager.add_event_handler('candles_received', self._on_candles_received)
        self._keep_alive_manager.add_event_handler('assets_updated', self._on_assets_updated)
        self._keep_alive_manager.add_event_handler('stream_update', self._on_stream_update)
        # forward everything else
        self._keep_alive_manager.add_event_handler('json_data', self._on_json_data)
        self._keep_alive_manager.add_event_handler('tradersChoice', self._on_traders_choice)
        self._keep_alive_manager.add_event_handler('userFeedInfo', self._on_user_feed_info)

        success = await self._keep_alive_manager.connect_with_keep_alive(urls)
        if success:
            try:
                await self._keep_alive_manager.send_message(
                    format_initial_message(token=self.token, is_demo=self.is_demo)
                )
            except Exception as e:
                logger.warning(f"Failed to send initial messages on persistent connection: {e}")
            self._is_persistent = True
            self.websocket_is_connected = True
            logger.info("Persistent connection established successfully")
            return True
        else:
            logger.error("Failed to establish persistent connection")
            return False

    async def disconnect(self) -> None:
        logger.info("Disconnecting...")
        for task_attr in ("_ping_task", "_reconnect_task", "_assets_update_task"):
            task = getattr(self, task_attr)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, task_attr, None)
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.disconnect()
        else:
            await self._websocket.disconnect()
        self._is_persistent = False
        self.websocket_is_connected = False
        self._balance = None
        self._active_orders.clear()
        self._order_results.clear()
        self._pending_order_requests.clear()
        logger.info("WebSocket connection closed")

    async def _start_keep_alive_tasks(self):
        logger.info("Starting keep-alive tasks for regular connection...")
        self._ping_task = asyncio.create_task(self._ping_loop())
        if self.auto_reconnect:
            self._reconnect_task = asyncio.create_task(self._reconnection_monitor())
        self._assets_update_task = asyncio.create_task(self._update_raw_assets())

    async def _ping_loop(self):
        while self.is_connected and not self._is_persistent:
            try:
                payload = json.dumps({
                    "action": "ping",
                    "v": 23,
                    "message": {"data": str(int(time.time() * 1000))},
                })
                await self._websocket.send_message(payload)
                self._connection_stats["last_ping_time"] = time.time()
                await asyncio.sleep(20)
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
                break

    async def _reply_pong(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message") or {}
            stamp = msg.get("data")
            payload = {
                "action": "pong",
                "message": {"data": stamp},
                "token": self.token,
                "ns": data.get("ns") or self._next_ns(),
            }
            await self.send_message(json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to reply pong: {e}")

    async def _reconnection_monitor(self):
        while not self._is_persistent:
            await asyncio.sleep(1)
            if not self.is_connected:
                logger.info("Connection lost, attempting reconnection...")
                self._connection_stats["total_reconnects"] += 1
                try:
                    await self._start_regular_connection()
                    self.websocket_is_connected = True
                    logger.info("Reconnection successful")
                except Exception as e:
                    logger.error(f"Reconnection error: {e}")
                await asyncio.sleep(1)

    def _check_connected(self) -> bool:
        if self._is_persistent and self._keep_alive_manager:
            return self._keep_alive_manager.is_connected
        else:
            return self._websocket.websocket_is_connected and self.websocket_is_connected

    @property
    def connection_info(self):
        if self._is_persistent and self._keep_alive_manager:
            return self._keep_alive_manager.connection_info
        else:
            return self._websocket.connection_info

    async def _ensure_connection(self, timeout: float = 5.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self._keep_alive_manager and self._keep_alive_manager.is_connected:
                return True
            if self._websocket.is_connected:
                return True
            await asyncio.sleep(0.05)
        return (self._keep_alive_manager.is_connected if self._keep_alive_manager else self._websocket.is_connected)

    async def send_message(self, message: str) -> bool:
        try:
            if not await self._ensure_connection():
                raise ConnectionError("WebSocket is not connected")
            if self._keep_alive_manager and self._keep_alive_manager.is_connected:
                await self._keep_alive_manager.send_message(message)
            else:
                await self._websocket.send_message(message)
            self._connection_stats["messages_sent"] += 1
            logger.info(f"SENT: {message}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    def get_connection_stats(self) -> Dict[str, Any]:
        stats = self._connection_stats.copy()
        stats.update({
            "websocket_connected": self._websocket.websocket_is_connected,
            "connection_info": self.connection_info,
        })
        return stats
    # endregion

    # region Token & Profile Management
    def _next_ns(self) -> str:
        return str(uuid.uuid4())

    async def _send_set_context(self) -> None:
        mode = 1 if self.is_demo else 0
        payload = {
            "action": "setContext",
            "message": {"is_demo": mode},
            "ns": self._next_ns(),
            "token": self.token,
        }
        await self.send_message(json.dumps(payload))
        logger.debug(f"setContext sent (is_demo={mode}).")

    async def _on_error(self, data: Dict[str, Any]) -> None:
        msg = data.get("message")
        reason = msg.get("reason") if isinstance(msg, dict) else (msg or "Unknown error")
        ns = data.get("ns") or (msg.get("ns") if isinstance(msg, dict) else None)
        if ns and ns in self._pending_order_requests:
            order = self._pending_order_requests.pop(ns, None)
            try:
                result = OrderResult(
                    order_id=ns,
                    server_id=None,
                    asset_id=int(order.asset_id) if order else 0,
                    asset=(order.symbol if order else "UNKNOWN"),
                    amount=(order.amount if order else 0.0),
                    direction=(order.direction if order else OrderDirection.CALL),
                    duration=(order.duration if order else 0),
                    created_at=(order.open_time if order else datetime.now()),
                    expires_at=(order.expires_at if order else datetime.now()),
                    open_price=0.0,
                    close_price=0.0,
                    profit=0.0,
                    payout=0.0,
                    status=OrderStatus.CANCELLED,
                    error_message=str(reason),
                )
                self._order_results[ns] = result
            except Exception:
                self._order_results[ns] = OrderResult(
                    order_id=ns,
                    server_id=None,
                    asset_id=0,
                    asset="UNKNOWN",
                    amount=0.0,
                    direction=OrderDirection.CALL,
                    duration=0,
                    created_at=datetime.now(),
                    expires_at=datetime.now(),
                    open_price=0.0,
                    close_price=0.0,
                    profit=0.0,
                    payout=0.0,
                    status=OrderStatus.CANCELLED,
                    error_message=str(reason),
                )
            logger.error(f"Server rejected order {ns}: {reason}")
            await self._emit_event("error", data)
            return
        logger.error(f"Received server error: {reason}")
        await self._emit_event("error", data)

    async def _on_token(self, data: Dict[str, Any]) -> None:
        new_token = data.get("message", {}).get("token")
        if new_token:
            self.token = new_token
            self.raw_token = new_token
            logger.info(f"Token updated from server: {new_token[:12]}...")
            await self._emit_event("token", data)

    async def _on_profile(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message", {}) if isinstance(data, dict) else {}
            profile = msg.get("profile", msg) if isinstance(msg, dict) else {}
            if not isinstance(profile, dict):
                return
            uid = profile.get("id") or profile.get("uid")
            if uid:
                self.uid = uid
                logger.info(f"Profile UID updated: {self.uid}")
            try:
                from .constants import CURRENCIES
            except Exception:
                CURRENCIES = None
            currency = resolve_currency(profile, CURRENCIES)

            demo_amount: Optional[float] = None
            real_amount: Optional[float] = None

            if "demo_balance" in profile or "real_balance" in profile:
                if profile.get("demo_balance") is not None:
                    demo_amount = float(profile["demo_balance"])
                if profile.get("real_balance") is not None:
                    real_amount = float(profile["real_balance"])

            if demo_amount is None and real_amount is None and "balance" in profile:
                bal = profile.get("balance")
                is_demo_flag = str(profile.get("is_demo")).lower() in ("1", "true")
                try:
                    bal = float(bal)
                except Exception:
                    bal = None
                if bal is not None:
                    if is_demo_flag: demo_amount = bal
                    else: real_amount = bal

            balances = msg.get("balances") or profile.get("balances")
            if isinstance(balances, list):
                for b in balances:
                    try:
                        t = str(b.get("type", "")).lower()
                        amt = b.get("amount") or b.get("balance") or b.get("value")
                        if amt is not None:
                            amt = float(amt)
                        cur = b.get("currency")
                        if isinstance(cur, str) and cur.strip():
                            currency = cur.strip()
                        if t in ("demo", "virtual", "practice") and demo_amount is None and amt is not None:
                            demo_amount = amt
                        elif t in ("real", "live") and real_amount is None and amt is not None:
                            real_amount = amt
                    except Exception:
                        continue

            if demo_amount is not None:
                self._balance_demo = Balance(balance=float(demo_amount), currency=str(currency), is_demo=True)
                logger.info(f"Demo balance: {self._balance_demo.balance} {self._balance_demo.currency}")
            if real_amount is not None:
                self._balance_real = Balance(balance=float(real_amount), currency=str(currency), is_demo=False)
                logger.info(f"Real balance: {self._balance_real.balance} {self._balance_real.currency}")

            self._balance = self._balance_demo if self.is_demo else (self._balance_real or self._balance_demo)
        except Exception as e:
            logger.error(f"Failed to process profile (non-fatal): {e}")
        finally:
            if not getattr(self, "_auth_emitted", False):
                self._auth_emitted = True
                await self._emit_event("authenticated", {"source": "profile"})

    async def _on_json_data(self, data: Dict[str, Any]) -> None:
        try:
            action = (data or {}).get("action")
            if action == "setContext":
                await self._on_set_context(data)
            if action == "getOneTimeToken":
                await self._on_token(data)
            if action == "assets":
                await self._on_assets(data)
            if action == "buyOption":
                await self._on_buy_option_ack(data)
            if action == "assetHistoryCandles":
                await self._on_asset_history_candles(data)
            if action in ("candles", "subscribeCandles", "defaultSubscribeCandles"):
                await self._on_candles_received(data)
            if action in ("buySuccessful", "openTradeSuccessful"):
                await self._on_order_opened(data)
            if action in ("optionFinished", "closeTradeSuccessful"):
                await self._on_order_closed(data)
            if action == "tradesStatus":
                await self._on_trades_status(data)
            if action == "profile":
                await self._on_profile(data)
            if action == "multipleAction":
                await self._on_multiple_action(data)
            if action == "tradersChoice":
                await self._on_traders_choice(data)
            if action == "userFeedInfo":
                await self._on_user_feed_info(data)
            if action == "optStatus":
                await self._on_opt_status(data)
            if action in ("openOptionsStat", "expertOption"):
                await self._on_feed_or_stats(data)
            if action in ("environment", "getCandlesTimeframes", "setTimeZone", "getCurrency", "getCountries"):
                await self._on_environment(data)
            # NEW actions:
            if action == "checkPushNotifications": 
                await self._on_check_push_notifications(data)
            if action == "userAchievements":       
                await self._on_user_achievements(data)
            if action == "userBadges":             
                await self._on_user_badges(data)
            if action == "activatedBonuses":       
                await self._on_activated_bonuses(data)
            if action == "userDepositSum":         
                await self._on_user_deposit_sum(data)
            if action == "referralOfferInfo":      
                await self._on_referral_offer_info(data)
            if action == "tradeHistory":           
                await self._on_trade_history(data)
            if action == "promoOpen":              
                await self._on_promo_open(data)
            if action == "expertSubscribe":        
                await self._on_expert_subscribe(data)
            if action == "cancelOption":           
                await self._on_cancel_option(data)
            if action == "setConversionData":      
                await self._on_set_conversion_data(data)
            if action == "getOneTimeToken":        
                await self._on_token(data)
            if action == "ping":
                await self._reply_pong(data)
                return
            if action == "pong":
                return
            if action == "error":
                await self._on_error(data)
        except Exception as e:
            logger.error(f"Error in _on_json_data: {e}")

    async def _on_multiple_action(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message", {})
            actions = msg.get("actions") if isinstance(msg, dict) else []
            if not isinstance(actions, list):
                return
            for a in actions:
                act = a.get("action")
                a["message"] = a.get("message", {})
                if act == "environment":
                    await self._on_environment(a)
                elif act == "userFeedInfo":
                    await self._on_user_feed_info(a)
                elif act == "profile":
                    await self._on_profile(a)
                elif act in ("candles", "subscribeCandles", "defaultSubscribeCandles"):
                    await self._on_candles_received(a)
                elif act == "assets":
                    await self._on_assets(a)
                # NEW in multipleAction as well
                elif act == "userAchievements":
                    await self._on_user_achievements(a)
                elif act == "userBadges":
                    await self._on_user_badges(a)
                elif act == "activatedBonuses":
                    await self._on_activated_bonuses(a)
                elif act == "userDepositSum":
                    await self._on_user_deposit_sum(a)
                elif act == "referralOfferInfo":
                    await self._on_referral_offer_info(a)
                elif act == "tradeHistory":
                    await self._on_trade_history(a)
                elif act == "checkPushNotifications":
                    await self._on_check_push_notifications(a)
                elif act == "promoOpen":
                    await self._on_promo_open(a)
                elif act == "expertSubscribe":
                    await self._on_expert_subscribe(a)
                elif act == "setConversionData":
                    await self._on_set_conversion_data(a)
        except Exception as e:
            logger.error(f"Error processing multipleAction: {e}")

    def _symbol_from_asset_id(self, aid: Any) -> str:
        try:
            aid_int = int(aid)
            symbol = get_asset_symbol(aid_int)
            if symbol:
                return symbol
        except Exception:
            pass
        for symbol, info in self._assets_data.items():
            try:
                if int(info.get("id")) == aid_int:
                    return sanitize_symbol(str(symbol))
            except Exception:
                continue
        return f"ASSET_{aid_int}"

    # Helper: known asset ids & waiting
    def _known_asset_ids(self) -> Set[int]:
        try:
            from .constants import ASSETS_ID_SYMBOL
            static_ids = set(int(k) for k in ASSETS_ID_SYMBOL.keys())
        except Exception:
            static_ids = set()
        try:
            dynamic_ids = {int(v.get("id")) for v in self._assets_data.values() if v.get("id") is not None}
        except Exception:
            dynamic_ids = set()
        return static_ids | dynamic_ids

    async def wait_asset(self, asset_id: int, timeout: float = 2.0) -> bool:
        """Wait until asset_id is known (indexed) or timeout."""
        aid = int(asset_id)
        if aid in self._known_asset_ids():
            # mark as ready for any concurrent waiters
            try: self._asset_ready[aid].set()
            except Exception: pass
            return True
        # trigger a fresh assets request (non-blocking) to speed up indexing
        try:
            asyncio.create_task(self._get_raw_asset())
        except Exception:
            pass
        try:
            await asyncio.wait_for(self._asset_ready[aid].wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return aid in self._known_asset_ids()
    # endregion

    # region New Message Handlers
    async def _on_check_push_notifications(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message", {}) or {}
            items = msg.get("notifications") or msg.get("items") or []
            parsed = []
            for it in items or []:
                parsed.append(PushNotification(
                    id=str(it.get("id")) if it.get("id") is not None else None,
                    title=it.get("title"),
                    body=it.get("body"),
                    created_at=it.get("created_at") or it.get("ts"),
                    read=it.get("read"),
                ))
            self._push_notifications = parsed
            logger.info(f"Push notifications: {len(parsed)}")
            await self._emit_event("checkPushNotifications", {"notifications": [n.dict() for n in parsed]})
        except Exception as e:
            logger.error(f"Error processing push notifications: {e}")

    async def _on_user_achievements(self, data: Dict[str, Any]) -> None:
        try:
            arr = (data.get("message") or {}).get("achievements") or (data.get("message") or {}).get("items") or []
            self._achievements = [Achievement(**a) if isinstance(a, dict) else Achievement() for a in arr]
            logger.info(f"Achievements received: {len(self._achievements)}")
            await self._emit_event("userAchievements", {"achievements": [a.dict() for a in self._achievements]})
        except Exception as e:
            logger.error(f"userAchievements error: {e}")

    async def _on_user_badges(self, data: Dict[str, Any]) -> None:
        try:
            arr = (data.get("message") or {}).get("badges") or (data.get("message") or {}).get("items") or []
            self._badges = [Badge(**b) if isinstance(b, dict) else Badge() for b in arr]
            logger.info(f"Badges received: {len(self._badges)}")
            await self._emit_event("userBadges", {"badges": [b.dict() for b in self._badges]})
        except Exception as e:
            logger.error(f"userBadges error: {e}")

    async def _on_activated_bonuses(self, data: Dict[str, Any]) -> None:
        try:
            arr = (data.get("message") or {}).get("bonuses") or (data.get("message") or {}).get("items") or []
            self._bonuses = [ActivatedBonus(**b) if isinstance(b, dict) else ActivatedBonus() for b in arr]
            logger.info(f"Activated bonuses: {len(self._bonuses)}")
            await self._emit_event("activatedBonuses", {"bonuses": [b.dict() for b in self._bonuses]})
        except Exception as e:
            logger.error(f"activatedBonuses error: {e}")

    async def _on_user_deposit_sum(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message") or {}
            payload = {"total_usd": msg.get("total") or msg.get("sum"), "currency": msg.get("currency")}
            self._deposit_sum = DepositSum(**payload)
            await self._emit_event("userDepositSum", {"sum": self._deposit_sum.dict()})
        except Exception as e:
            logger.error(f"userDepositSum error: {e}")

    async def _on_referral_offer_info(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message") or {}
            info = msg.get("referralOfferInfo") or msg
            if isinstance(info, dict):
                self._referral_info = ReferralOfferInfo(
                    active=info.get("active", info.get("isActive")),
                    reward_percent=info.get("reward_percent", info.get("percent")),
                    code=info.get("code"),
                )
                await self._emit_event("referralOfferInfo", {"info": self._referral_info.dict()})
        except Exception as e:
            logger.error(f"referralOfferInfo error: {e}")

    async def _on_trade_history(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message") or {}
            items = msg.get("trades") or msg.get("history") or msg.get("items") or []
            parsed: List[TradeHistoryEntry] = []
            for it in items:
                try:
                    d = dict(it)
                    # normalize naming
                    d.setdefault("status", it.get("result") or it.get("status"))
                    d.setdefault("direction", it.get("type"))
                    d.setdefault("opened_at", it.get("open_time") or it.get("opened_at"))
                    d.setdefault("closed_at", it.get("close_time") or it.get("closed_at"))
                    parsed.append(TradeHistoryEntry(**d))
                except Exception:
                    parsed.append(TradeHistoryEntry())
            self._trade_history = parsed
            logger.info(f"Trade history received: {len(parsed)} entries")
            await self._emit_event("tradeHistory", {"history": [t.dict() for t in parsed]})
        except Exception as e:
            logger.error(f"tradeHistory error: {e}")

    async def _on_promo_open(self, data: Dict[str, Any]) -> None:
        try:
            self._promo_open_payload = data.get("message") or {}
            await self._emit_event("promoOpen", self._promo_open_payload)
        except Exception as e:
            logger.error(f"promoOpen error: {e}")

    async def _on_expert_subscribe(self, data: Dict[str, Any]) -> None:
        try:
            await self._emit_event("expertSubscribe", data)
        except Exception as e:
            logger.error(f"expertSubscribe error: {e}")

    async def _on_cancel_option(self, data: Dict[str, Any]) -> None:
        try:
            await self._emit_event("cancelOption", data)
        except Exception as e:
            logger.error(f"cancelOption error: {e}")

    async def _on_set_conversion_data(self, data: Dict[str, Any]) -> None:
        try:
            await self._emit_event("setConversionData", data)
        except Exception as e:
            logger.error(f"setConversionData error: {e}")

    async def _get_one_time_token(self) -> str:
        if not self.token:
            raise AuthenticationError("Missing session token. Please connect/login first.")
        return self.token

    async def _on_traders_choice(self, data: Dict[str, Any]) -> None:
        """Handle tradersChoice response"""
        try:
            msg = data.get("message", {}) if isinstance(data, dict) else {}
            # Broker may send the list under different keys
            traders_data = (
                msg.get("tradersChoice")
                or msg.get("assets")
                or msg.get("traders_choice", [])
            )
            if not isinstance(traders_data, list):
                traders_data = []
            for trader in traders_data:
                asset_id = trader.get("assetId") or trader.get("asset_id")
                put_value = trader.get("put")
                if asset_id is not None:
                    self._traders_choice[asset_id] = TradersChoice(
                        asset_id=asset_id, put=put_value
                    )
            # logger.info(f"Received traders choice data: {len(traders_data)} recommendations")
            await self._emit_event("tradersChoice", traders_data)
        except Exception as e:
            logger.error(f"Error processing traders choice: {e}")

    async def _on_feed_or_stats(self, data: Dict[str, Any]) -> None:
        """Handle openOptionsStat/expertOption messages containing traders choice"""
        try:
            msg = data.get("message", {}) if isinstance(data, dict) else {}
            traders = msg.get("tradersChoice")
            if traders:
                await self._on_traders_choice({"message": {"tradersChoice": traders}})
        except Exception as e:
            logger.error(f"Error processing feed or stats data: {e}")

    async def _on_environment(self, data: Dict[str, Any]) -> None:
        try:
            env_data = data.get("message", {}) if isinstance(data, dict) else data
            self._environment_info = EnvironmentInfo(
                supportedFeatures=env_data.get("supportedFeatures", []),
                supportedAbTests=env_data.get("supportedAbTests", []),
                supportedInventoryItems=env_data.get("supportedInventoryItems", []),
                sessionTs=env_data.get("sessionTs"),
                isBonusAvaliable=env_data.get("isBonusAvaliable"),
            )
        except Exception as e:
            logger.error(f"Error processing environment data: {e}")

    async def _on_user_feed_info(self, data: Dict[str, Any]) -> None:
        try:
            feed_info = data.get("message", {})
            self._user_feed_info = UserFeedInfo(
                count_unseen=feed_info.get("count_unseen", 0),
                has_priority=feed_info.get("has_priority", False),
            )
        except Exception as e:
            logger.error(f"Error processing user feed info: {e}")

    async def _on_trades_status(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message", {}) or {}
            trades = msg.get("trades", []) or []
            for tr in trades:
                sid = tr.get("id")
                if not sid:
                    continue
                try:
                    sid = int(sid)
                except Exception:
                    continue
                st = self._order_state.setdefault(sid, {})
                if "p" in tr:
                    try:
                        st["last_price"] = float(tr["p"])
                    except Exception:
                        pass
                if "t" in tr:
                    try:
                        st["last_t"] = int(tr["t"])
                    except Exception:
                        pass
                if "w" in tr:
                    try:
                        st["w"] = int(tr["w"])
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"tradesStatus tracking error: {e}")
    # endregion

    # region Balance Management
    async def _request_balance_update(self) -> None:
        ns = self._next_ns()
        message = json.dumps({"action": "profile", "ns": ns, "token": self.token})
        if self._is_persistent and self._keep_alive_manager:
            await self._keep_alive_manager.send_message(message)
        else:
            await self._websocket.send_message(message)

    async def get_balance(self) -> Optional[Balance]:
        """Return current active balance. Will trigger a profile request if missing and wait briefly."""
        if not self.is_connected:
            raise ConnectionError("Not connected to ExpertOption")
        if self._balance is None:
            await self._request_balance_update()
            for _ in range(30):
                if self._balance is not None:
                    break
                await asyncio.sleep(0.1)
        return self._balance

    async def get_balances(self) -> Dict[str, Optional[Balance]]:
        """Return both balances (demo/real). Triggers update if both missing."""
        if not self.is_connected:
            raise ConnectionError("Not connected to ExpertOption")
        if self._balance_demo is None and self._balance_real is None:
            await self._request_balance_update()
            for _ in range(30):
                if self._balance_demo is not None or self._balance_real is not None:
                    break
                await asyncio.sleep(0.1)
        return {"demo": self._balance_demo, "real": self._balance_real}

    async def get_demo_balance(self) -> Optional[Balance]:
        return (await self.get_balances()).get("demo")

    async def get_real_balance(self) -> Optional[Balance]:
        return (await self.get_balances()).get("real")
    # endregion

    # region Order Management
    def _get_asset_id(self, symbol: str) -> int:
        """Resolve asset id from a symbol, falling back to cached assets."""
        sym = sanitize_symbol(symbol)
        if sym in ASSETS:
            try:
                return int(ASSETS[sym])
            except Exception:
                pass
        # fallback to cached assets map
        info = self._assets_data.get(sym)
        if info and "id" in info:
            try:
                return int(info["id"])
            except Exception:
                pass
        raise InvalidParameterError(f"Unknown asset symbol: {symbol}")

    async def _on_buy_option_ack(self, data: Dict[str, Any]) -> None:
        try:
            ns = data.get("ns") or (data.get("message") or {}).get("ns")
            if ns:
                logger.info(f"Order ack received for request_id={ns}")
        except Exception as e:
            logger.warning(f"Error handling buyOption ack: {e}")

    def _compute_expiration_shift(self, duration: int, asset_id: int, now: Optional[int] = None) -> int:
        import math
        now = int(now or time.time())
        step = 60
        max_sec = 86400
        purchase_time = 30
        try:
            info = next((v for v in self._assets_data.values() if int(v.get("id", -1)) == int(asset_id)), None)
            if info:
                tfs = [int(t) for t in (info.get("available_timeframes") or []) if int(t) >= 30]
                if tfs:
                    step = max(30, min(tfs))
                max_sec = int(info.get("expiration_max_seconds", max_sec) or max_sec)
                purchase_time = int(info.get("purchase_time") or purchase_time)
        except Exception:
            pass
        if step <= 0:
            step = 60
        if purchase_time < 1 or purchase_time > 300:
            purchase_time = 30
        boundary = ((now // step) + 1) * step
        shift_to_boundary = boundary - now
        min_to_expire = max(purchase_time + 2, 1)
        while shift_to_boundary < min_to_expire:
            boundary += step
            shift_to_boundary = boundary - now
        k = max(1, math.ceil(duration / step))
        shift = int(shift_to_boundary + (k - 1) * step)
        if shift > max_sec:
            shift = max_sec
        logger.debug(f"Computed shift={shift} (step={step}, purchase_time={purchase_time}, now={now})")
        return max(1, shift)

    async def place_order(
        self,
        asset: Optional[Union[str, int]] = None,
        amount: Optional[float] = None,
        direction: Optional[OrderDirection] = None,
        duration: int = 60,
        *,
        asset_id: Optional[int] = None,
        refund: Optional[float] = None,
    ) -> OrderResult:
        """
        Backward-compatible order placement.
        Accepts either `asset` (symbol like "EURUSD" or int id) or explicit `asset_id=...`.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to ExpertOption")

        # Resolve asset_id and symbol
        if asset is None and asset_id is None:
            raise InvalidParameterError("You must provide either `asset` or `asset_id`")

        if asset is not None and asset_id is None:
            if isinstance(asset, (int, float)) or (isinstance(asset, str) and str(asset).isdigit()):
                asset_id = int(asset)
                asset_symbol = self._symbol_from_asset_id(asset_id)
            else:
                asset_symbol = sanitize_symbol(str(asset))
                asset_id = self._get_asset_id(asset_symbol)
        elif asset_id is not None:
            asset_id = int(asset_id)
            asset_symbol = self._symbol_from_asset_id(asset_id)
        else:
            asset_symbol = sanitize_symbol(str(asset))

        # Validate params
        if amount is None or direction is None:
            raise InvalidParameterError("`amount` and `direction` are required.")
        self._validate_order_parameters(asset_id, float(amount), direction, int(duration))

        # Build Pydantic Order (immutable) with an order_id for tracking
        now_dt = datetime.now()
        request_id = str(uuid.uuid4())
        order = Order(
            order_id=request_id,
            asset_id=int(asset_id),
            symbol=asset_symbol,
            amount=float(amount),
            direction=direction,
            duration=int(duration),
            open_time=now_dt,
            expires_at=now_dt + timedelta(seconds=int(duration)),
            status=OrderStatus.PENDING,
            refund=0.0,
        )

        # Track and send
        self._pending_order_requests[request_id] = order
        await self._send_order(order, refund=refund)
        result = await self._wait_for_order_result(request_id, order, timeout=60.0)
        if self.enable_logging:
            logger.info(f"Order placed: {result.order_id} - {result.status}")
        return result

    async def get_active_orders(self) -> List[OrderResult]:
        return list(self._active_orders.values())

    async def _send_order(self, order: Order, refund: Optional[float] = None) -> None:
        asset_id = int(order.asset_id or 0)
        direction_str = "call" if order.direction == OrderDirection.CALL else "put"
        type_int = 0 if order.direction == OrderDirection.CALL else 1
        now = int(time.time())
        token = await self._get_one_time_token()
        shift = self._compute_expiration_shift(int(order.duration or 60), asset_id, now)
        fp = (asset_id, int(type_int), round(float(order.amount), 2), int(now))
        self._pending_fingerprints[fp] = order.order_id
        payload = {
            "action": "buyOption",
            "message": {
                "type": direction_str,
                "amount": float(order.amount),
                "assetid": asset_id,
                "strike_time": now,
                "is_demo": 1 if self.is_demo else 0,
                "expiration_shift": int(shift),
                "ratePosition": 0,
            },
            "ns": order.order_id,
            "token": token,
        }
        sent = await self.send_message(json.dumps(payload))
        if not sent:
            raise ConnectionError("Failed to send order payload")
        logger.debug(
            f"Sent order payload (asset_id={asset_id}, dir={direction_str}, amount={order.amount}, "
            f"duration={order.duration}, shift={shift}, now={now})"
        )

    async def _wait_for_order_result(self, request_id: str, order: Order, timeout: float = 60.0) -> OrderResult:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if request_id in self._active_orders:
                self._pending_order_requests.pop(request_id, None)
                return self._active_orders[request_id]
            if request_id in self._order_results:
                self._pending_order_requests.pop(request_id, None)
                return self._order_results[request_id]
            await asyncio.sleep(0.2)
        logger.error(f"Order {request_id} timed out waiting for server response")
        self._pending_order_requests.pop(request_id, None)
        raise OrderError(f"Order {request_id} timed out waiting for server confirmation")

    async def check_win(self, order_id: str) -> tuple[Optional[float], str]:
        logger.info(f"Waiting for order {order_id} result.")
        while True:
            try:
                result = await self.check_order_result(order_id)
                if result and result.status in [
                    OrderStatus.WIN,
                    OrderStatus.LOSS,
                    OrderStatus.DRAW,
                    OrderStatus.CANCELLED,
                ]:
                    profit = result.profit if result.profit is not None else 0.0
                    status = result.status.value
                    details = {"id": order_id, "is_demo": 1 if self.is_demo else 0}
                    logger.info(
                        f"Order {order_id} finished: result='{status}', profit={profit}, details={details}"
                    )
                    return profit, status
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error in check_win for {order_id}: {e}")
                await asyncio.sleep(1)

    async def check_order_result(self, order_id: str) -> Optional[OrderResult]:
        if order_id in self._active_orders:
            return self._active_orders[order_id]
        if order_id in self._order_results:
            return self._order_results[order_id]
        return None
    # endregion

    # region Asset Management
    async def get_available_assets(self) -> Dict[str, Dict[str, Any]]:
        """
        Return a symbol->info mapping of currently available assets as reported by the server.
        The info dictionary contains fields such as id, symbol, name, type, payout, is_otc, is_open,
        available_timeframes, rates, expiration_max_seconds, shutdown_time, custom_time_enabled,
        purchase_time and expiration_step.
        """
        while True:
            try:
                if self._assets_data:
                    return self._assets_data.copy()
                raw_assets = await self._get_raw_asset()
                logger.info(f"Raw assets received: {len(raw_assets)} assets")

                # Re-use existing update logic to parse and store assets
                await self._on_assets_updated({"assets": raw_assets})
                return self._assets_data.copy()
            except Exception as e:
                logger.error(f"Failed to fetch assets: {e}")
                await asyncio.sleep(1)

    async def get_assets_and_payouts(self) -> Dict[str, int]:
        if not self.is_connected:
            raise ConnectionError("Not connected to ExpertOption")
        while True:
            try:
                assets = await self.get_available_assets()
                payouts: Dict[str, int] = {}
                for symbol, info in assets.items():
                    try:
                        payout_val = float(info.get("payout", 0) or 0)
                        if payout_val <= 1:
                            payout_val *= 100
                        payout = int(payout_val)
                        if info.get("is_open") and payout > 0:
                            payouts[sanitize_symbol(symbol)] = payout
                    except Exception:
                        continue
                return payouts
            except Exception:
                await asyncio.sleep(1)

    async def get_payout(self, asset: Union[str, int], timeframe: Union[str, int]) -> float:
        if isinstance(asset, (int, float)) or str(asset).isdigit():
            asset_val = int(asset)
            if asset_val not in ASSETS.values():
                raise InvalidParameterError(f"Invalid asset: {asset}")
            asset_name = get_asset_symbol(asset_val) or str(asset_val)
        else:
            asset_name = sanitize_symbol(str(asset))
        if isinstance(timeframe, (int, float)) or str(timeframe).isdigit():
            tf_val = int(timeframe)
            if tf_val not in TIMEFRAMES.values():
                raise InvalidParameterError(f"Invalid timeframe: {timeframe}")
        else:
            if timeframe not in TIMEFRAMES:
                raise InvalidParameterError(f"Invalid timeframe: {timeframe}")
            tf_val = TIMEFRAMES[timeframe]
        while True:
            try:
                raw_assets = await self._get_raw_asset()
                for a in raw_assets:
                    if isinstance(a, dict):
                        sym = sanitize_symbol(a.get("symbol"))
                        is_otc_flag = bool(a.get("is_otc", False)) or (
                            "otc" in str(a.get("symbol")).lower()
                        )
                        if is_otc_flag and not sym.endswith("_OTC"):
                            sym = f"{sym}_OTC"
                        if sym == asset_name:
                            if not bool(a.get("is_active", a.get("is_open", a.get("active", False)))):
                                logger.warning(f"Asset {asset_name} is closed")
                                return 0.0
                            raw_payout = (
                                a.get("profit")
                                or a.get("profit_percent")
                                or a.get("payout")
                                or a.get("profitRate")
                            )
                            try:
                                payout_val = float(raw_payout) if raw_payout is not None else 0.0
                            except (TypeError, ValueError):
                                return 0.0
                            if payout_val <= 1:
                                payout_val *= 100
                            return float(payout_val)
                await asyncio.sleep(1)
            except Exception:
                await asyncio.sleep(1)

    async def _on_assets(self, data: Dict[str, Any]) -> None:
        try:
            assets_data = data.get("message", {}).get("assets", [])
            logger.info(f"Received assets message: {len(assets_data)} assets")
            await self._on_assets_updated({"assets": assets_data})
        except Exception as e:
            logger.error(f"Error processing assets response: {e}")

    async def _on_assets_updated(self, data: Any) -> None:
        try:
            parsed_assets: Dict[str, Dict[str, Any]] = {}
            assets_list = data.get("assets") or []
            logger.info(f"Processing assets update: {len(assets_list)} assets")
            try:
                update_assets_from_api(assets_list)
            except Exception:
                pass
            for asset_info in assets_list:
                #try:
                #    if int(asset_info.get("ps", 1)) != 1:
                #        continue
                #except Exception:
                #    pass
                # Accept symbol or fallback to name/id so we don't drop assets
                symbol_in = asset_info.get("symbol") or asset_info.get("name") or asset_info.get("id")
                if symbol_in is None:
                    logger.warning(f"Skipping asset with no symbol/name/id: {asset_info}")
                    continue
                symbol = str(symbol_in)
                # Normalize timing fields
                try:
                    step = int(asset_info.get("expiration_step", 60) or 60)
                except Exception:
                    step = 60
                if step <= 0:
                    step = 60
                try:
                    max_sec = int(asset_info.get("expiration_max_seconds", 86400) or 86400)
                except Exception:
                    max_sec = 86400
                if max_sec < 60:
                    max_sec = 60
                # Build timeframes from constants filtered by step/max
                candidate_tfs = sorted(set(TIMEFRAMES.values()))
                available_tfs = [t for t in candidate_tfs if (t % step == 0) and (t <= max_sec)]
                if not available_tfs:
                    available_tfs = [60, 120, 180, 300, 600, 900]
                # Payout / flags
                raw_payout = (
                    asset_info.get("profit")
                    or asset_info.get("profit_percent")
                    or asset_info.get("payout")
                    or asset_info.get("profitRate")
                )
                try:
                    payout_val = float(raw_payout or 0)
                    if payout_val <= 1:
                        payout_val *= 100
                    payout = int(payout_val)
                except Exception:
                    payout = 0
                name_str = str(asset_info.get("name", symbol) or "")
                is_otc_flag = (
                    bool(asset_info.get("is_otc", False))
                    or ("otc" in name_str.lower())
                    or ("otc" in symbol.lower())
                )
                is_open_flag = bool(asset_info.get("is_active", asset_info.get("is_open", False)))
                purchase_time = int(
                    asset_info.get("purchase_time") or asset_info.get("purchaseTime") or 30
                )
                if purchase_time < 1 or purchase_time > 300:
                    purchase_time = 30
                    
                asset_key = sanitize_symbol(symbol)
                if is_otc_flag and not asset_key.endswith("_OTC"):
                    asset_key = f"{asset_key}_OTC"
                    
                info = {
                    "id": asset_info.get("id"),
                    "symbol": asset_key,
                    "name": name_str,
                    "type": asset_info.get("asset_type", asset_info.get("type", "unknown")),
                    "payout": payout,
                    "is_otc": is_otc_flag,
                    "is_open": is_open_flag,
                    "available_timeframes": available_tfs,
                    "rates": asset_info.get("rates", []),
                    "expiration_max_seconds": max_sec,
                    "shutdown_time": asset_info.get("shutdown_time", None),
                    "custom_time_enabled": bool(asset_info.get("custom_time_enabled", 1)),
                    "purchase_time": purchase_time,
                    "expiration_step": step,
                }
                parsed_assets[asset_key] = info
            if parsed_assets:
                # Atomic swap of the whole map to avoid empty windows
                self._assets_data = parsed_assets
                logger.info(f"Stored {len(parsed_assets)} assets")
                # Signal readiness (global and per-asset)
                try:
                    self._assets_index_ready.set()
                    for info in parsed_assets.values():
                        try:
                            aid = int(info.get("id"))
                            self._asset_ready[aid].set()
                        except Exception:
                            pass
                except Exception:
                    pass
                for request_id, future in list(self._assets_requests.items()):
                    if not future.done():
                        future.set_result(list(parsed_assets.values()))
        except Exception as e:
            logger.error(f"Error processing assets update: {e}")

    async def _update_raw_assets(self):
        while self.is_connected:
            try:
                await self._get_raw_asset()
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Failed to update assets: {e}")
                await asyncio.sleep(60)

    async def _get_raw_asset(self) -> List[Any]:
        request_id = self._next_ns()
        future = asyncio.get_event_loop().create_future()
        self._assets_requests[request_id] = future
        await self.send_message(
            json.dumps(
                {
                    "action": "assets",
                    "message": {"mode": ["vanilla"], "subscribeMode": ["vanilla"]},
                    "ns": request_id,
                    "token": self.token,
                }
            )
        )
        try:
            raw_assets = await asyncio.wait_for(future, timeout=30.0)
            logger.info(f"Raw assets fetched: {len(raw_assets)} assets")
            return raw_assets
        finally:
            self._assets_requests.pop(request_id, None)

    # endregion

    # region Candle Management
    async def get_candles(self, asset_id: int, timeframe: Union[str, int], count: int = 100, end_time: Optional[datetime] = None) -> List[Candle]:
        """Fetch historical candles for a given asset ID and timeframe."""
        if isinstance(timeframe, str):
            timeframe_seconds = TIMEFRAMES.get(timeframe, 60)
        else:
            timeframe_seconds = int(timeframe)
        # Wait for asset indexing if needed (prevents 'not found' during races)
        ok = await self.wait_asset(int(asset_id), timeout=2.0)
        if not ok:
            raise InvalidParameterError(f"Invalid asset ID: {asset_id}")
        try:
            candles = await self._request_candles(asset_id, timeframe_seconds, count, end_time)
            if not candles:
                return []
            cache_key = f"{asset_id}_{timeframe_seconds}"
            self._candles_cache[cache_key] = candles[-self._ring_limit :]
            return candles[-count:]
        except Exception as e:
            logger.error(f"Error fetching candles for asset ID {asset_id}: {e}")
            return []

    async def get_candles_dataframe(self, asset_id: int, timeframe: Union[str, int], count: int = 100, end_time: Optional[datetime] = None) -> pd.DataFrame:
        """Fetch candles and convert them to a pandas DataFrame."""
        candles = await self.get_candles(asset_id, timeframe, count, end_time)
        return candles_to_dataframe(candles)

    async def _request_candles(self, asset_id: int, timeframe: int, count: int, end_time: Optional[datetime]):
        # Ensure asset is known before asking history
        ok = await self.wait_asset(int(asset_id), timeout=2.0)
        if not ok:
            raise InvalidParameterError(f"Asset ID not found for {asset_id}")
        now = int(time.time()) if end_time is None else int(end_time.timestamp())
        end_ts = now - (now % timeframe)
        start_ts = end_ts - (max(count, 1) * timeframe)
        # request key normalized by asset ID
        request_key = f"{asset_id}_{timeframe}"
        candle_future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._candle_requests[request_key] = candle_future
        # (1) ensure subscription for live stream
        await self.subscribe_symbol(asset_id, [timeframe])
        # (2) ask history for the window
        hist_msg = {
            "action": "assetHistoryCandles",
            "message": {
                "assetid": int(asset_id),
                "periods": [[int(start_ts), int(end_ts)]],
                "timeframes": [int(timeframe)],
            },
            "token": self.token,
            "ns": self._next_ns(),
        }
        sender = (
            self._keep_alive_manager.send_message
            if self._is_persistent and self._keep_alive_manager
            else self._websocket.send_message
        )
        await sender(json.dumps(hist_msg))
        try:
            candles: List[Candle] = await asyncio.wait_for(candle_future, timeout=15.0)
            return candles[-count:]
        except asyncio.TimeoutError:
            self._candle_requests.pop(request_key, None)
            return []

    async def _on_asset_history_candles(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message", {}) or {}
            asset_id = msg.get("assetId") or msg.get("assetid")
            blocks = msg.get("candles", [])
            if not blocks:
                return
            try:
                aid = int(asset_id)
            except Exception:
                aid = asset_id
            asset_symbol = get_asset_symbol(aid) or str(aid)
            parsed: List[Candle] = []
            # Expected shape: blocks -> [{ "tf": 60, "periods": [[start, [[o,h,l,c], ...]], ...] }, ...]
            for block in blocks:
                tf = int(block.get("tf", 60))
                for period in block.get("periods", []):
                    start_ts = int(period[0])
                    ohlcs = period[1]
                    t = start_ts
                    for arr in ohlcs:
                        if len(arr) >= 4:
                            o, h, l, c = float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3])
                            parsed.append(
                                Candle(
                                    timestamp=datetime.fromtimestamp(t),
                                    open=o,
                                    high=h,
                                    low=l,
                                    close=c,
                                    volume=0.0,
                                    asset=str(asset_symbol),
                                    timeframe=tf,
                                )
                            )
                            t += tf
            if parsed:
                key = f"{asset_id}_{parsed[0].timeframe}"
                fut = self._candle_requests.pop(key, None)
                if fut and not fut.done():
                    fut.set_result(parsed)
                # store cache ring
                self._candles_cache[key] = parsed[-self._ring_limit :]
        except Exception as e:
            logger.error(f"Error in assetHistoryCandles handler: {e}")

    async def _on_candles_received(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message", {}) or {}
            candles = msg.get("candles", []) or []
            asset_id = msg.get("assetId")
            asset_symbol = None
            try:
                aid = int(asset_id)
            except Exception:
                aid = asset_id
            # If candles arrive before indexing, mark this asset as ready to unblock waiters
            try:
                if isinstance(aid, int):
                    self._asset_ready[aid].set()
            except Exception:
                pass
            if isinstance(aid, int):
                asset_symbol = get_asset_symbol(aid)
            asset = asset_symbol if isinstance(asset_symbol, str) else sanitize_symbol(str(aid))
            for item in candles:
                if not isinstance(item, dict):
                    continue
                tf = int(item.get("tf", 60))
                t_raw = item.get("t", 0)
                if not t_raw:
                    continue
                if tf == 0:
                    try:
                        for key, cur in list(self._live_last.items()):
                            if not key.startswith(f"{asset}_"):
                                continue
                            cur_tf = int(key.split("_")[-1])
                            if cur_tf <= 0:
                                continue
                            bar_t = (int(float(t_raw)) // cur_tf) * cur_tf
                            self._tick_counts[key][bar_t] += 1
                    except Exception:
                        pass
                    continue
                t = int(float(t_raw))
                vals = item.get("v", [])
                if len(vals) < 4:
                    continue
                o, h, l, c = float(vals[0]), float(vals[1]), float(vals[2]), float(vals[3])
                vol_from_server = None
                if len(vals) >= 5:
                    try:
                        vol_from_server = float(vals[4])
                    except Exception:
                        vol_from_server = None
                key = f"{asset_id}_{tf}"
                cur = self._live_last.get(key)

                def _get_vol(ts: int) -> float:
                    if vol_from_server is not None:
                        return float(vol_from_server)
                    return float(self._tick_counts.get(key, {}).get(ts, 0))

                if cur and int(cur["t"]) == t:
                    if h > cur["h"]:
                        cur["h"] = h
                    if l < cur["l"]:
                        cur["l"] = l
                    cur["c"] = c
                    cur["v"] = _get_vol(t)
                    out_candle = Candle(
                        timestamp=datetime.fromtimestamp(int(cur["t"])),
                        open=cur["o"],
                        high=cur["h"],
                        low=cur["l"],
                        close=cur["c"],
                        volume=float(cur.get("v", 0.0)),
                        asset=str(asset),
                        timeframe=tf,
                    )
                else:
                    if cur:
                        prev_t = int(cur["t"])
                        prev_vol = cur.get("v", None)
                        if prev_vol is None:
                            prev_vol = float(self._tick_counts.get(key, {}).pop(prev_t, 0))
                        closed = Candle(
                            timestamp=datetime.fromtimestamp(prev_t),
                            open=cur["o"],
                            high=cur["h"],
                            low=cur["l"],
                            close=cur["c"],
                            volume=float(prev_vol or 0.0),
                            asset=str(asset),
                            timeframe=tf,
                        )
                        buf = self._candles_cache.setdefault(key, [])
                        buf.append(closed)
                        if len(buf) > self._ring_limit:
                            del buf[: len(buf) - self._ring_limit]
                    self._live_last[key] = {"t": t, "o": o, "h": h, "l": l, "c": c, "v": _get_vol(t)}
                    out_candle = Candle(
                        timestamp=datetime.fromtimestamp(t),
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=float(self._live_last[key]["v"] or 0.0),
                        asset=str(asset),
                        timeframe=tf,
                    )
                q = self._candle_stream_subs.get(key)
                if q and not q.full():
                    try:
                        q.put_nowait(out_candle)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error processing live candles: {e}")

    def _parse_candles_data(self, candles_data: List[Any], asset: str, timeframe: int):
        candles = []
        try:
            if isinstance(candles_data, list):
                for candle_data in candles_data:
                    if isinstance(candle_data, dict) and "v" in candle_data:
                        v = candle_data["v"]
                        if len(v) >= 4:
                            vol = None
                            if len(v) >= 5:
                                try:
                                    vol = float(v[4])
                                except Exception:
                                    vol = None
                            if vol is None:
                                vol = float(candle_data.get("volume", 0.0))
                            candles.append(
                                Candle(
                                    timestamp=datetime.fromtimestamp(candle_data.get("t", 0)),
                                    open=float(v[0]),
                                    high=float(v[1]),
                                    low=float(v[2]),
                                    close=float(v[3]),
                                    volume=float(vol or 0.0),
                                    asset=asset,
                                    timeframe=timeframe,
                                )
                            )
        except Exception as e:
            if self.enable_logging:
                logger.error("Error parsing candles data: {}", e)
        return candles

    # Streaming API
    async def subscribe_symbol(self, asset_id: int, timeframes: List[int]):
        """Subscribe to live candle updates for an asset ID across the provided timeframes.
        The server enforces a cap on the number of simultaneous subscriptions. We track
        active subscriptions locally and only send a subscribe request for new pairs,
        mirroring the lightweight approach used by the PocketOption client.
        """
        try:
            new_tfs: List[int] = []
            for tf in timeframes:
                pair = (int(asset_id), int(tf))
                if pair not in self._active_subscriptions:
                    self._active_subscriptions.add(pair)
                    new_tfs.append(int(tf))
            if not new_tfs:
                return
            sub_msg = {
                "action": "subscribeCandles",
                "message": {"assets": [{"id": int(asset_id), "timeframes": new_tfs}]},
                "token": self.token,
                "ns": self._next_ns(),
            }
            sender = (
                self._keep_alive_manager.send_message
                if self._is_persistent and self._keep_alive_manager
                else self._websocket.send_message
            )
            await sender(json.dumps(sub_msg))
            symbol = self._symbol_from_asset_id(asset_id)
            for tf in new_tfs:
                key = f"{sanitize_symbol(symbol)}_{int(tf)}"
                self._candle_stream_subs.setdefault(key, asyncio.Queue(maxsize=100))
        except Exception as e:
            logger.error(f"subscribe_symbol error: {e}")

    async def unsubscribe_symbol(self, asset_id: int, timeframes: List[int]):
        """ExpertOption doesn't expose an unsubscribe in our samples; clear local channels."""
        symbol = self._symbol_from_asset_id(asset_id)
        for tf in timeframes:
            key = f"{sanitize_symbol(symbol)}_{int(tf)}"
            self._candle_stream_subs.pop(key, None)
            self._active_subscriptions.discard((int(asset_id), int(tf)))
            
    async def get_stream_candle(self, asset: str, timeframe: int, timeout: float = 0.0) -> Optional[Candle]:
        """Pull one candle from the stream queue."""
        key = f"{sanitize_symbol(asset)}_{int(timeframe)}"
        q = self._candle_stream_subs.get(key)
        if not q:
            return None
        try:
            if timeout and timeout > 0:
                return await asyncio.wait_for(q.get(), timeout=timeout)
            return q.get_nowait()
        except asyncio.QueueEmpty:
            return None
    # endregion

    # region Event Handling
    async def _on_set_context(self, data: Dict[str, Any]) -> None:
        """Just acknowledge setContext to keep logs clean."""
        try:
            msg = data.get("message", {})
            result = msg.get("result")
            logger.debug(f"setContext acknowledged (result={result})")
        except Exception as e:
            logger.debug(f"setContext handler error (non-fatal): {e}")

    async def _on_authenticated(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.info("Successfully authenticated with ExpertOption")
        self._connection_stats["successful_connections"] += 1
        await self._emit_event("authenticated", data)
        await self.send_message(json.dumps({"action": "assets", "message": {"mode": ["vanilla"], "subscribeMode": ["vanilla"]}, "token": self.token, "ns": self._next_ns()}))

    async def _on_balance_updated(self, data: Dict[str, Any]) -> None:
        if data.get("balance") is None:
            logger.debug("Ignoring empty balance_updated event: {}", data)
            return
        try:
            balance_value = float(data.get("balance"))
            balance = Balance(
                balance=balance_value,
                currency=data.get("currency", "USD"),
                is_demo=self.is_demo,
            )
            self._balance = balance
            if self.enable_logging:
                logger.info("Balance updated: ${:.2f}", balance.balance)
            await self._emit_event("balance_updated", data)
        except Exception as e:
            logger.error("Failed to update balance: {}", e)

    async def _on_balance_data(self, data: Dict[str, Any]) -> None:
        try:
            profile = data.get("message", {}).get("profile", {})
            uid = profile.get("id") or profile.get("userId") or profile.get("uid")
            if uid is not None:
                try:
                    self.uid = int(uid)
                    logger.info("Profile UID updated (balance_data): {}", self.uid)
                except Exception:
                    pass
            balance_value = float(profile.get("demo_balance", 0))
            balance = Balance(
                balance=balance_value,
                currency=profile.get("currency", "USD"),
                is_demo=bool(profile.get("is_demo", self.is_demo)),
            )
            self._balance = balance
            if self.enable_logging:
                logger.info("Balance data received: ${:.2f}", balance.balance)
            await self._emit_event("balance_data", data)
        except Exception as e:
            logger.error("Failed to process balance data: {}", e)

    async def _on_order_opened(self, data: Dict[str, Any]) -> None:
        msg = (data.get("message", {}) or {})
        trade = msg.get("trade") or msg.get("option") or {}
        if not trade and isinstance(msg, dict):
            keys = set(msg.keys())
            if {"id", "asset_id", "type", "amount"}.issubset(keys):
                trade = msg
        if not trade:
            logger.warning("open/buy successful event without trade/option payload: {}", data)
            return
        try:
            server_id = str(trade.get("id", ""))
            aid = int(trade.get("asset_id"))
            t_raw = trade.get("type")
            type_int = 0 if t_raw in (0, "call", "CALL") else 1
            amt = round(float(trade.get("amount", 0.0)), 2)
            strike_time = int(float(trade.get("strike_time", 0)) or 0)
            open_rate = float(trade.get("strike_rate", trade.get("open_rate", 0.0)) or 0.0)
            exp_time = int(float(trade.get("exp_time", 0)) or 0)
            req_id = self._pending_fingerprints.pop((aid, type_int, amt, strike_time), None)
            if not req_id:
                for delta in (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5):
                    req_id = self._pending_fingerprints.pop((aid, type_int, amt, strike_time + delta), None)
                    if req_id:
                        break
            if not req_id:
                logger.warning(
                    "Got successful-open event but no matching pending request. "
                    "fp=(asset_id={}, type={}, amount={}, strike_time={})",
                    aid,
                    type_int,
                    amt,
                    strike_time,
                )
                return
            order = self._pending_order_requests.get(req_id)
            asset_symbol = self._symbol_from_asset_id(aid)
            direction = OrderDirection.CALL if type_int == 0 else OrderDirection.PUT
            created_at = datetime.fromtimestamp(strike_time) if strike_time else datetime.now()
            expires_at = (
                datetime.fromtimestamp(exp_time)
                if exp_time
                else created_at + timedelta(seconds=order.duration if order else 0)
            )
            result = OrderResult(
                order_id=req_id,
                server_id=server_id,
                asset=(order.symbol if order else asset_symbol),
                asset_id=aid,
                amount=(order.amount if order else float(amt)),
                direction=(order.direction if order else direction),
                duration=(order.duration if order else 0),
                status=OrderStatus.ACTIVE,
                created_at=created_at,
                expires_at=expires_at,
                payout=float(trade.get("profit", 0) or 0),
                open_price=open_rate,
            )
            self._request_id_to_server_id[req_id] = server_id
            self._active_orders[req_id] = result
            if req_id in self._pending_order_requests:
                del self._pending_order_requests[req_id]
            if self.enable_logging:
                logger.info("Order opened: {} (Server ID: {})", req_id, server_id)
            await self._emit_event("order_opened", data)
        except Exception as e:
            logger.error("Error in _on_order_opened parsing trade: {}", e)

    async def _on_order_closed(self, data: Dict[str, Any]) -> None:
        """Simplified close handler."""
        msg = data.get("message", {}) or {}
        rows = msg.get("trades") or msg.get("options") or []
        if not rows:
            single = msg.get("trade") or msg.get("option")
            if single:
                rows = [single]

        for deal in rows:
            try:
                server_id = str(deal.get("id"))
                request_id = next(
                    (rid for rid, sid in self._request_id_to_server_id.items() if sid == server_id), None
                )
                if not request_id or request_id not in self._active_orders:
                    logger.warning("No active order found for server id {}", server_id)
                    continue

                active = self._active_orders[request_id]

                # Close rate
                close_rate = None
                for key in ("close_rate", "p", "price", "closePrice"):
                    if deal.get(key) is not None:
                        try:
                            close_rate = float(deal.get(key))
                            break
                        except Exception:
                            pass
                if close_rate is None:
                    try:
                        st = self._order_state.get(int(server_id), {}) or {}
                        if st.get("last_price") is not None:
                            close_rate = float(st["last_price"])
                    except Exception:
                        pass
                if close_rate is None:
                    close_rate = 0.0

                # Determine status
                raw_status = str(deal.get("status", "")).lower()
                if raw_status in ("win", "won", "profit"):
                    status = OrderStatus.WIN
                elif raw_status in ("loss", "lose", "lost"):
                    status = OrderStatus.LOSS
                elif raw_status in ("draw", "equal"):
                    status = OrderStatus.DRAW
                else:
                    EPS = 1e-8
                    diff = float(close_rate or 0.0) - float(active.open_price or 0.0)
                    if abs(diff) <= EPS:
                        status = OrderStatus.DRAW
                    else:
                        if active.direction == OrderDirection.CALL:
                            status = OrderStatus.WIN if diff > 0 else OrderStatus.LOSS
                        else:
                            status = OrderStatus.WIN if diff < 0 else OrderStatus.LOSS

                # Profit (net)
                amount = float(active.amount or 0.0)
                payout_field = float(active.payout or 0.0)
                payout_frac = (payout_field / 100.0) if payout_field > 1.0 else payout_field
                server_profit = None
                for key in ("win_amount", "result_amount", "resultAmount", "profit"):
                    if deal.get(key) is not None:
                        try:
                            server_profit = float(deal.get(key))
                            break
                        except Exception:
                            pass
                if server_profit is not None:
                    net_profit = server_profit - amount if server_profit > amount + 1e-6 else server_profit
                else:
                    net_profit = (
                        amount * payout_frac
                        if status == OrderStatus.WIN
                        else (-amount if status == OrderStatus.LOSS else 0.0)
                    )
                try:
                    net_profit = round(net_profit, 2)
                except Exception:
                    pass

                result = OrderResult(
                    order_id=request_id,
                    server_id=server_id,
                    asset=active.asset,
                    asset_id=active.asset_id,
                    amount=active.amount,
                    direction=active.direction,
                    duration=active.duration,
                    status=status,
                    created_at=active.created_at,
                    expires_at=active.expires_at,
                    profit=float(net_profit),
                    payout=payout_field,
                    open_price=float(active.open_price or 0.0),
                    close_price=float(close_rate or 0.0),
                )

                # Move from active to final
                self._active_orders.pop(request_id, None)
                self._order_results[request_id] = result
                if self.enable_logging:
                    logger.info(
                        "Order {} finished: result='{}', profit={}, details={}",
                        request_id,
                        result.status.value,
                        result.profit,
                        {"id": request_id, "is_demo": 1 if self.is_demo else 0},
                    )
                await self._emit_event("order_closed", result)
            except Exception as e:
                logger.error("Error in simplified _on_order_closed: {}", e)

    async def _on_opt_status(self, data: Dict[str, Any]) -> None:
        try:
            msg = data.get("message", {}) or {}
            options = msg.get("options", []) or []
            for o in options:
                sid = o.get("id")
                if not sid:
                    continue
                try:
                    sid = int(sid)
                except Exception:
                    continue
                st = self._order_state.setdefault(sid, {})
                if "p" in o:
                    st["last_price"] = float(o["p"])
                if "t" in o:
                    st["last_t"] = int(o["t"])
                if "w" in o:
                    try:
                        st["w"] = int(o["w"])
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"optStatus tracking error: {e}")

    async def _on_stream_update(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.debug("Received stream update: {}", data)
        await self._emit_event("stream_update", data)

    async def _on_keep_alive_connected(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.info("Keep-alive connection established")
        self.websocket_is_connected = True
        await self._emit_event("connected", data)

    async def _on_keep_alive_reconnected(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.info("Keep-alive reconnected")
        self.websocket_is_connected = True
        await self._emit_event("reconnected", data)

    async def _on_keep_alive_message(self, data: Dict[str, Any]) -> None:
        if self.enable_logging:
            logger.debug("Received keep-alive message: {}", data)
        await self._emit_event("message_received", data)

    async def _on_price_update(self, data: Dict[str, Any]) -> None:
        logger.debug("Price update received: {}", data)
        await self._emit_event("price_update", data)

    async def _emit_event(self, event: str, data: Any) -> None:
        if event in self._event_callbacks:
            for callback in self._event_callbacks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    if self.enable_logging:
                        logger.error("Error in event callback for {}: {}", event, e)

    def add_event_callback(self, event: str, callback: Callable) -> None:
        if event not in self._event_callbacks:
            self._event_callbacks[event] = []
        self._event_callbacks[event].append(callback)

    def remove_event_callback(self, event: str, callback: Callable) -> None:
        if event in self._event_callbacks:
            try:
                self._event_callbacks[event].remove(callback)
            except ValueError:
                pass
    # endregion

    # region Helper Methods
    async def _wait_for_authentication(self, timeout: float = 10.0) -> None:
        auth_received = False
        def on_auth(data):
            nonlocal auth_received
            auth_received = True
        self.add_event_callback("authenticated", on_auth)
        try:
            start_time = time.time()
            while not auth_received and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)
            if not auth_received:
                raise AuthenticationError("Authentication timeout")
        finally:
            self.remove_event_callback("authenticated", on_auth)

    async def _setup_time_sync(self) -> None:
        local_time = datetime.now().timestamp()
        self._server_time = ServerTime(server_timestamp=local_time, local_timestamp=local_time, offset=0.0)

    def _validate_order_parameters(self, asset: Union[str, int], amount: float, direction: OrderDirection, duration: int) -> None:
        # Accept either a known symbol or an int id that may arrive via live cache
        if isinstance(asset, (int, float)) or str(asset).isdigit():
            aid = int(asset)
            from .constants import ASSETS
            if aid not in ASSETS.values():
                # Try dynamic cache / wait briefly before failing
                # (sync wait via loop.run_until_complete is unsafe here; we only do a quick presence check)
                if aid not in self._known_asset_ids():
                    raise InvalidParameterError(f"Invalid asset: {asset}")
        else:
            from .constants import ASSETS
            if asset not in ASSETS:
                # try dynamic symbols map
                sym = sanitize_symbol(str(asset))
                if sym not in self._assets_data:
                    raise InvalidParameterError(f"Invalid asset: {asset}")
        if amount < API_LIMITS["min_order_amount"] or amount > API_LIMITS["max_order_amount"]:
            raise InvalidParameterError(f"Amount must be between {API_LIMITS['min_order_amount']} and {API_LIMITS['max_order_amount']}")
        if duration < API_LIMITS["min_duration"] or duration > API_LIMITS["max_duration"]:
            raise InvalidParameterError(f"Duration must be between {API_LIMITS['min_duration']} and {API_LIMITS['max_duration']} seconds")
        if len(self._active_orders) >= API_LIMITS["max_concurrent_orders"]:
            raise OrderError("Maximum concurrent orders reached")
    # endregion
