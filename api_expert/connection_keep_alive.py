"""Connection Keep-Alive Manager for ExpertOption API."""
import asyncio
import time
import json
from collections import defaultdict
from typing import Dict, List, Any, Callable, Optional, Union
from websockets.exceptions import ConnectionClosed  # noqa: F401
from datetime import datetime
import uuid
from loguru import logger

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

class ConnectionKeepAlive:
    def __init__(self, token: str, is_demo: bool = True):
        self.token = token
        self.is_demo = is_demo
        self.is_connected = False
        self._websocket = None  # AsyncWebSocketClient instance
        self._event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._ping_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
        self._assets_request_task: Optional[asyncio.Task] = None
        self._last_assets_request: Optional[datetime] = None
        self._connection_stats = {
            "last_ping_time": None,
            "last_pong_time": None,
            "total_reconnections": 0,
            "messages_sent": 0,
            "messages_received": 0,
        }
        from .websocket_client import AsyncWebSocketClient
        self._websocket_client_class = AsyncWebSocketClient

    # Event API
    def add_event_handler(self, event: str, handler: Callable):
        self._event_handlers[event].append(handler)

    async def _trigger_event_async(self, event: str, data: Dict[str, Any]) -> None:
        try:
            for handler in self._event_handlers.get(event, []):
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
        except Exception as e:
            logger.error(f"Error in {event} handler: {e}")

    # Forwarders
    async def _forward_balance_data(self, data): await self._trigger_event_async("balance_data", data=data)
    async def _forward_balance_updated(self, data): await self._trigger_event_async("balance_updated", data=data)
    async def _forward_authenticated(self, data): await self._trigger_event_async("authenticated", data=data)
    async def _forward_order_opened(self, data): await self._trigger_event_async("order_opened", data=data)
    async def _forward_order_closed(self, data): await self._trigger_event_async("order_closed", data=data)
    async def _forward_order_updated(self, data): await self._trigger_event_async("order_updated", data=data)
    async def _forward_candles_received(self, data): await self._trigger_event_async("candles_received", data=data)
    async def _forward_assets_updated(self, data): await self._trigger_event_async("assets_updated", data=data)
    async def _forward_stream_update(self, data): await self._trigger_event_async("stream_update", data=data)
    async def _forward_json_data(self, data): await self._trigger_event_async("json_data", data=data)

    # Connection
    async def connect_with_keep_alive(self, regions: Optional[List[str]] = None) -> bool:
        if not self._websocket:
            self._websocket = self._websocket_client_class()
            # Wire WS events
            self._websocket.add_event_handler("balance_data", self._forward_balance_data)
            self._websocket.add_event_handler("balance_updated", self._forward_balance_updated)
            self._websocket.add_event_handler("authenticated", self._forward_authenticated)
            self._websocket.add_event_handler("order_opened", self._forward_order_opened)
            self._websocket.add_event_handler("order_closed", self._forward_order_closed)
            self._websocket.add_event_handler("order_updated", self._forward_order_updated)
            self._websocket.add_event_handler("candles_received", self._forward_candles_received)
            self._websocket.add_event_handler("assets_updated", self._forward_assets_updated)
            self._websocket.add_event_handler("stream_update", self._forward_stream_update)
            self._websocket.add_event_handler("json_data", self._forward_json_data)
        # [UPDATE] Send setContext and verify response
        set_context_ns = str(uuid.uuid4())
        set_context = json.dumps({
            "action": "setContext",
            "message": {"is_demo": 1 if self.is_demo else 0},
            "token": self.token,
            "ns": set_context_ns
        })
        initial_message = self._format_initial_message()
        from .constants import REGIONS
        if not regions:
            if self.is_demo:
                all_regions = REGIONS.get_all_regions()
                demo_urls = REGIONS.get_demo_regions()
                regions = [name for name, url in all_regions.items() if url in demo_urls]
            else:
                all_regions = REGIONS.get_all_regions()
                regions = [name for name, url in all_regions.items() if "DEMO" not in name.upper()]
        for region_name in regions:
            region_url = REGIONS.get_region(region_name)
            if not region_url:
                continue
            try:
                urls = [region_url]
                logger.info(f"Trying to connect to {region_name} ({region_url})")
                success = await asyncio.wait_for(self._websocket.connect(urls, set_context), timeout=10.0)
                if success:
                    # [UPDATE] Wait for setContext
                    try:
                        logger.warning(f"setContext {region_name}: mode.")
                    except asyncio.TimeoutError:
                        logger.info(f"setContext {region_name}")
                    logger.info(f"WebSocket connected successfully to {region_name}")
                    self.is_connected = True
                    self._start_keep_alive_tasks()
                    await self._trigger_event_async("connected", data={"region": region_name, "url": region_url})
                    await self._websocket.send_message(initial_message) # bootstrap immediately
                    self._connection_stats["messages_sent"] += 1
                    return True
            except asyncio.TimeoutError:
                logger.warning(f"Connection timeout to {region_name}")
            except Exception as e:
                logger.warning(f"Failed to connect to {region_name}: {e}")
        return False

    # Tasks
    def _start_keep_alive_tasks(self):
        logger.info("Starting keep-alive tasks")
        if self._ping_task: self._ping_task.cancel()
        self._ping_task = asyncio.create_task(self._ping_loop())
        if self._reconnect_task: self._reconnect_task.cancel()
        self._reconnect_task = asyncio.create_task(self._reconnection_monitor())
        if self._health_task: self._health_task.cancel()
        self._health_task = asyncio.create_task(self._health_monitor_loop())
        if self._assets_request_task: self._assets_request_task.cancel()
        self._assets_request_task = asyncio.create_task(self._assets_request_loop())

    async def _ping_loop(self):
        while self.is_connected and self._websocket:
            try:
                ping_message = json.dumps({"action": "ping", "v": 23, "message": {}})
                await self._websocket.send_message(ping_message)
                self._connection_stats["last_ping_time"] = time.time()
                self._connection_stats["messages_sent"] += 1
                logger.debug("Sent ping")
                await asyncio.sleep(20)
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
                self.is_connected = False

    async def _health_monitor_loop(self):
        logger.info("Starting health monitor...")
        while True:
            try:
                await asyncio.sleep(30)
                if not self.is_connected or not self._websocket:
                    continue
                if not self._websocket.is_connected:
                    logger.warning("WebSocket is closed")
                    self.is_connected = False
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                self.is_connected = False

    async def _assets_request_loop(self):
        logger.info("Starting assets request loop...")
        while self.is_connected and self._websocket:
            try:
                # throttle every 30s
                assets_message = json.dumps({
                    "action": "assets",
                    "token": self.token,
                    "ns": str(uuid.uuid4())
                })
                await self._websocket.send_message(assets_message)
                self._connection_stats["messages_sent"] += 1
                logger.debug("Assets data request sent")
                await asyncio.sleep(30)
            except Exception as e:
                logger.warning(f"Assets request failed: {e}")
                self.is_connected = False

    async def _reconnection_monitor(self):
        logger.info("Starting reconnection monitor...")
        while True:
            await asyncio.sleep(30)
            if not self.is_connected or not self._websocket or not self._websocket.is_connected:
                logger.info("Connection lost, reconnecting...")
                self.is_connected = False
                self._connection_stats["total_reconnections"] += 1
                try:
                    success = await self.connect_with_keep_alive()
                    if success:
                        logger.info("Reconnection successful")
                        await self._trigger_event_async("reconnected", data={})
                    else:
                        logger.error("Reconnection failed")
                except Exception as e:
                    logger.error(f"Reconnection error: {e}")

    # Public API
    async def disconnect(self):
        logger.info("Disconnecting...")
        for task in (self._ping_task, self._reconnect_task, self._health_task, self._assets_request_task):
            if task: task.cancel()
        if self._websocket:
            await self._websocket.disconnect()
        self.is_connected = False
        logger.info("WebSocket connection closed")
        await self._trigger_event_async("disconnected", data={})

    async def send_message(self, message):
        if not self.is_connected or not self._websocket:
            raise ConnectionError("Not connected")
        try:
            await self._websocket.send_message(message)
            self._connection_stats["messages_sent"] += 1
            logger.info(f"SENT: {str(message)[:150]}...")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self.is_connected = False
            raise ConnectionError(f"Failed to send message: {e}")

    async def on_message(self, message: Union[str, bytes]):
        try:
            self._connection_stats["messages_received"] += 1
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            logger.info(f"RECEIVED: {str(message)[:150]}...")
            data = json.loads(message)
            action = data.get("action")
            if action == "pong":
                self._connection_stats["last_pong_time"] = time.time()
            elif action == "assets":
                await self._trigger_event_async("assets_updated", data=data)
            elif action == "candles":
                await self._trigger_event_async("candles_received", data=data)
            elif action == "optStatus":
                await self._trigger_event_async("order_updated", data=data)
            elif action == "optionFinished":
                await self._trigger_event_async("order_closed", data=data)
            elif action == "profile":
                await self._trigger_event_async("authenticated", data={"via": "profile"})
                await self._trigger_event_async("balance_data", data=data)
            elif action == "userGroup":
                await self._trigger_event_async("authenticated", data={"via": "userGroup"})
            elif action == "tradersChoice" or action == "expertOption":
                await self._trigger_event_async("stream_update", data=data)
            else:
                await self._trigger_event_async("message_received", data=data)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON message: {e}")
            await self._trigger_event_async("message_received", data=message)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.is_connected = False

    def _format_initial_message(self) -> str:
        actions = [
            {"action": "userGroup", "ns": str(uuid.uuid4()), "token": self.token},
            {"action": "profile", "ns": str(uuid.uuid4()), "token": self.token},
            {"action": "assets", "ns": str(uuid.uuid4()), "token": self.token},
            {"action": "getCurrency", "ns": str(uuid.uuid4()), "token": self.token},
            {"action": "getCountries", "ns": str(uuid.uuid4()), "token": self.token},
            {
                "action": "environment",
                "message": {
                    "supportedFeatures": [
                        "achievements","trade_result_share","tournaments","referral","twofa",
                        "inventory","deposit_withdrawal_error_handling","report_a_problem_form",
                        "ftt_trade","stocks_trade"
                    ],
                    "supportedAbTests": [
                        "tournament_glow","floating_exp_time","tutorial","tutorial_account_type",
                        "tutorial_account_type_reg","hide_education_section","in_app_update_android_2",
                        "auto_consent_reg","btn_finances_to_register","battles_4th_5th_place_rewards",
                        "show_achievements_bottom_sheet","kyc_webview","promo_story_priority",
                        "force_lang_in_app","one_click_deposit"
                    ],
                    "supportedInventoryItems": [
                        "riskless_deal","profit","eopoints","tournaments_prize_x3","mystery_box",
                        "special_deposit_bonus","cashback_offer"
                    ]
                },
                "ns": str(uuid.uuid4()),
                "token": self.token
            },
            {"action": "defaultSubscribeCandles", "message": {"timeframes": [0, 5, 60]}, "ns": str(uuid.uuid4()), "token": self.token},
            {"action": "setTimeZone", "message": {"timeZone": 180}, "ns": str(uuid.uuid4()), "token": self.token},
            {"action": "getCandlesTimeframes", "ns": str(uuid.uuid4()), "token": self.token}
        ]
        return json.dumps({"action": "multipleAction", "message": {"actions": actions}, "token": self.token, "ns": str(uuid.uuid4())})

    def get_stats(self) -> Dict[str, Any]:
        """Expose basic keep-alive stats to the client."""
        return {
            **self._connection_stats,
            "websocket_connected": bool(getattr(self._websocket, "is_connected", False)),
            "connection_info": getattr(self._websocket, "connection_info", None),
        }
