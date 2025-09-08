"""Async WebSocket client for ExpertOption API."""
import asyncio
import json
import ssl
import time
from typing import Optional, Callable, Dict, Any, List, Deque
from datetime import datetime
from collections import deque

import websockets
from websockets.exceptions import ConnectionClosed

from .models import ConnectionInfo, ConnectionStatus, ServerTime
from .constants import CONNECTION_SETTINGS, DEFAULT_HEADERS, REGIONS
from .exceptions import WebSocketError, ConnectionError
from loguru import logger

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

class MessageBatcher:
    def __init__(self, batch_size: int = 10, batch_timeout: float = 0.1):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.pending_messages: Deque[str] = deque()
        self._last_batch_time = time.time()
        self._batch_lock = asyncio.Lock()

    async def add_message(self, message: str) -> List[str]:
        async with self._batch_lock:
            self.pending_messages.append(message)
            current_time = time.time()
            if (len(self.pending_messages) >= self.batch_size) or (current_time - self._last_batch_time >= self.batch_timeout):
                batch = list(self.pending_messages)
                self.pending_messages.clear()
                self._last_batch_time = current_time
                return batch
            return []

    async def flush_batch(self) -> List[str]:
        async with self._batch_lock:
            if self.pending_messages:
                batch = list(self.pending_messages)
                self.pending_messages.clear()
                self._last_batch_time = time.time()
                return batch
            return []

class ConnectionPool:
    def __init__(self, max_connections: int = 3):
        self.max_connections = max_connections
        self.active_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.connection_stats: Dict[str, Dict[str, Any]] = {}
        self._pool_lock = asyncio.Lock()

    async def get_best_connection(self) -> Optional[str]:
        async with self._pool_lock:
            if not self.connection_stats:
                return None
            best_url = min(
                self.connection_stats.keys(),
                key=lambda url: (
                    self.connection_stats[url].get("avg_response_time", float("inf")),
                    -self.connection_stats[url].get("success_rate", 0),
                ),
            )
            return best_url

    async def update_stats(self, url: str, response_time: float, success: bool):
        async with self._pool_lock:
            if url not in self.connection_stats:
                self.connection_stats[url] = {
                    "response_times": deque(maxlen=100),
                    "successes": 0,
                    "failures": 0,
                    "avg_response_time": 0,
                    "success_rate": 0,
                }
            stats = self.connection_stats[url]
            stats["response_times"].append(response_time)
            if success:
                stats["successes"] += 1
            else:
                stats["failures"] += 1
            if stats["response_times"]:
                stats["avg_response_time"] = sum(stats["response_times"]) / len(stats["response_times"])
            total_attempts = stats["successes"] + stats["failures"]
            if total_attempts > 0:
                stats["success_rate"] = stats["successes"] / total_attempts

class AsyncWebSocketClient:
    def __init__(self):
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connection_info: Optional[ConnectionInfo] = None
        self.server_time: Optional[ServerTime] = None

        self._ping_task: Optional[asyncio.Task] = None
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = CONNECTION_SETTINGS["max_reconnect_attempts"]
        self._message_batcher = MessageBatcher()
        self._connection_pool = ConnectionPool()
        self._rate_limiter = asyncio.Semaphore(10)
        self._message_cache: Dict[str, Any] = {}
        self._cache_ttl = 5.0

        self.websocket_is_connected: bool = False
        self.ssl_mutual_exclusion: bool = False
        self.ssl_mutual_exclusion_write: bool = False

        # Response funnels (fixed)
        self.response_queue: Deque[Dict] = deque(maxlen=1000)
        self.unhandled_messages: Deque[Dict] = deque(maxlen=1000)

        # Back-compat containers used by some code paths
        self._responses: Deque[Dict] = deque(maxlen=1000)
        self._others: Deque[Dict] = deque(maxlen=1000)

        # Single-reader guard for recv()
        self._recv_lock = asyncio.Lock()

    async def connect(self, urls: List[str], initial_message: Optional[str] = None) -> bool:
        headers = dict(DEFAULT_HEADERS)
        for url in urls:
            try:
                logger.info(f"Attempting to connect to {url}")
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                self.websocket = await asyncio.wait_for(
                    websockets.connect(
                        url,
                        ssl=ssl_context,
                        extra_headers=headers,
                        ping_interval=CONNECTION_SETTINGS["ping_interval"],
                        ping_timeout=CONNECTION_SETTINGS["ping_timeout"],
                        close_timeout=CONNECTION_SETTINGS["close_timeout"],
                        compression="deflate",
                        max_queue=None,
                        max_size=2**22,
                    ),
                    timeout=10.0,
                )

                self.connection_info = ConnectionInfo(
                    url=url,
                    region=self._extract_region_from_url(url),
                    status=ConnectionStatus.CONNECTED,
                    connected_at=datetime.now(),
                    last_ping=None,
                    reconnect_attempts=self._reconnect_attempts,
                )

                self.websocket_is_connected = True
                self._running = True
                asyncio.create_task(self.receive_messages())

                if initial_message:
                    await self.send_message(initial_message)

                self._ping_task = asyncio.create_task(self._ping_loop())
                logger.info("WebSocket connected successfully")
                return True

            except Exception as e:
                logger.warning(f"Failed to connect to {url}: {e}")
                self.websocket_is_connected = False
                if self.websocket:
                    try:
                        await self.websocket.close()
                    except Exception:
                        pass
                self.websocket = None
                continue
        return False

    async def disconnect(self):
        logger.info("Disconnecting from WebSocket")
        self._running = False
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        if self.websocket:
            try:
                await self.websocket.close()
                await asyncio.sleep(0.1)
            except Exception:
                pass
            self.websocket = None
        if self.connection_info:
            self.connection_info = ConnectionInfo(
                url=self.connection_info.url,
                region=self.connection_info.region,
                status=ConnectionStatus.DISCONNECTED,
                connected_at=self.connection_info.connected_at,
                last_ping=self.connection_info.last_ping,
                reconnect_attempts=self._reconnect_attempts,
            )
        self.websocket_is_connected = False
        self.ssl_mutual_exclusion = False
        self.ssl_mutual_exclusion_write = False
        self.response_queue.clear()
        self.unhandled_messages.clear()
        self._responses.clear()
        self._others.clear()
        await self._emit_event("disconnected", {})

    async def send_message(self, message: str) -> None:
        if not self.websocket or self.websocket.closed:
            self.websocket_is_connected = False
            raise WebSocketError("WebSocket is not connected")
        try:
            while self.ssl_mutual_exclusion or self.ssl_mutual_exclusion_write:
                await asyncio.sleep(0.05)
            self.ssl_mutual_exclusion_write = True
            start_time = time.time()
            await self.websocket.send(message)
            # logger.info(f"SENT: {message[:20000]}...")
            if self.connection_info:
                await self._connection_pool.update_stats(self.connection_info.url, time.time() - start_time, True)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self.websocket_is_connected = False
            if self.connection_info:
                await self._connection_pool.update_stats(self.connection_info.url, 0, False)
            raise WebSocketError(f"Failed to send message: {e}")
        finally:
            self.ssl_mutual_exclusion_write = False

    async def send_message_optimized(self, message: str) -> None:
        async with self._rate_limiter:
            if not self.websocket or self.websocket.closed:
                self.websocket_is_connected = False
                raise WebSocketError("WebSocket is not connected")
            try:
                while self.ssl_mutual_exclusion or self.ssl_mutual_exclusion_write:
                    await asyncio.sleep(0.05)
                self.ssl_mutual_exclusion_write = True
                start_time = time.time()
                batch = await self._message_batcher.add_message(message)
                if batch:
                    for msg in batch:
                        await self.websocket.send(msg)
                        logger.info(f"SENT: {msg[:150]}...")
                response_time = time.time() - start_time
                if self.connection_info:
                    await self._connection_pool.update_stats(self.connection_info.url, response_time, True)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                self.websocket_is_connected = False
                if self.connection_info:
                    await self._connection_pool.update_stats(self.connection_info.url, 0, False)
                raise WebSocketError(f"Failed to send message: {e}")
            finally:
                self.ssl_mutual_exclusion_write = False

    async def receive_messages(self) -> None:
        try:
            while self._running and self.websocket:
                try:
                    async with self._recv_lock:
                        message = await asyncio.wait_for(
                            self.websocket.recv(),
                            timeout=CONNECTION_SETTINGS["message_timeout"],
                        )
                    await self._process_message(message)
                except asyncio.TimeoutError:
                    logger.warning("Message receive timeout")
                    continue
                except ConnectionClosed as e:
                    code = getattr(e, "code", None)
                    reason = getattr(e, "reason", "")
                    logger.warning(f"WebSocket connection closed (code={code}, reason={reason})")
                    self.websocket_is_connected = False
                    await self._handle_disconnect()
                    if self._reconnect_attempts < self._max_reconnect_attempts:
                        self._reconnect_attempts += 1
                        logger.info(
                            f"Attempting reconnection {self._reconnect_attempts}/{self._max_reconnect_attempts} after {CONNECTION_SETTINGS['reconnect_delay']}s"
                        )
                        await asyncio.sleep(CONNECTION_SETTINGS["reconnect_delay"])
                        await self._emit_event("reconnecting", {})
                    break
        except Exception as e:
            logger.error(f"Error in message receiving: {e}")
            self.websocket_is_connected = False
            await self._handle_disconnect()

    def add_event_handler(self, event: str, handler: Callable) -> None:
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def remove_event_handler(self, event: str, handler: Callable) -> None:
        if event in self._event_handlers:
            try:
                self._event_handlers[event].remove(handler)
            except ValueError:
                pass

    async def _ping_loop(self) -> None:
        while self._running and self.websocket:
            try:
                await asyncio.sleep(CONNECTION_SETTINGS["ping_interval"])
                if self.websocket and not self.websocket.closed:
                    ping_message = json.dumps({
                        "action": "ping",
                        "v": 23,
                        "message": {"data": str(int(time.time() * 1000))},
                    })
                    await self.send_message(ping_message)
                    if self.connection_info:
                        self.connection_info = ConnectionInfo(
                            url=self.connection_info.url,
                            region=self.connection_info.region,
                            status=self.connection_info.status,
                            connected_at=self.connection_info.connected_at,
                            last_ping=datetime.now(),
                            reconnect_attempts=self._reconnect_attempts,
                        )
            except Exception as e:
                logger.error(f"Ping failed: {e}")
                self.websocket_is_connected = False
                break

    async def _process_message(self, message) -> None:
        # logger.info(f"RAW WS MESSAGE: {message}")
        try:
            if isinstance(message, bytes):
                try:
                    message = message.decode("utf-8", errors="replace")
                except UnicodeDecodeError:
                    return
            if not isinstance(message, str):
                return
            # logger.info(f"RECEIVED: {message[:20000]}...")
            data = json.loads(message)
            action = data.get("action")
            if action == "ping":
                msg = data.get("message", {}) or {}
                pong = {"action": "pong", "v": data.get("v", 23), "message": msg, "ns": ""}
                await self.send_message(json.dumps(pong))
                return
            ROUTED = (
                "token", "error",
                "assets", "candles", "assetHistoryCandles",
                "defaultSubscribeCandles", "subscribeCandles",
                "buySuccessful", "openTradeSuccessful",
                "tradesStatus", "closeTradeSuccessful", "optionFinished",
                "expertOption", "openOptionsStat",
                "tradersChoice", "multipleAction",
                "profile", "userGroup", "userFeedInfo",
                "environment", "getCandlesTimeframes",
                "setTimeZone", "getCurrency", "getCountries",
                "getOneTimeToken",
            )
            if action in ROUTED:
                self._responses.append(data)
                self.response_queue.append(data)
            else:
                self._others.append(data)
                self.unhandled_messages.append(data)
            await self._emit_event("json_data", data)
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.websocket_is_connected = False

    async def receive(self, action: str, ns: str = None, timeout: float = 15.0, asset_id: Optional[int] = None, server_id: Optional[str] = None) -> Dict:
        end_time = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end_time:
            for payload in list(self.response_queue):
                payload_action = payload.get("action")
                if (payload_action == action or (action == "expertSubscribe" and payload_action == "expertOption")) and (ns is None or payload.get("ns") == ns):
                    if action == "candles" and asset_id is not None:
                        if payload.get("message", {}).get("assetId") == asset_id:
                            self.response_queue.remove(payload)
                            return payload
                    elif action in ["optStatus", "optionFinished"] and server_id is not None:
                        options = payload.get("message", {}).get("options", [])
                        for opt in options:
                            if str(opt.get("id")) == server_id:
                                self.response_queue.remove(payload)
                                return payload
                    else:
                        self.response_queue.remove(payload)
                        return payload
            for payload in list(self.unhandled_messages):
                payload_action = payload.get("action")
                if (payload_action == action or (action == "expertSubscribe" and payload_action == "expertOption")) and (ns is None or payload.get("ns") == ns):
                    if action == "candles" and asset_id is not None:
                        if payload.get("message", {}).get("assetId") == asset_id:
                            self.unhandled_messages.remove(payload)
                            return payload
                    elif action in ["optStatus", "optionFinished"] and server_id is not None:
                        options = payload.get("message", {}).get("options", [])
                        for opt in options:
                            if str(opt.get("id")) == server_id:
                                self.unhandled_messages.remove(payload)
                                return payload
                    else:
                        self.unhandled_messages.remove(payload)
                        return payload
            await asyncio.sleep(0.01)
        logger.warning(f"Timeout waiting for {action} response.")
        raise TimeoutError(f"Timeout waiting for {action}")

    async def _emit_event(self, event: str, data: Dict[str, Any]) -> None:
        handlers = self._event_handlers.get(event, [])
        for h in list(handlers):
            try:
                if asyncio.iscoroutinefunction(h):
                    await h(data)
                else:
                    await asyncio.get_event_loop().run_in_executor(None, h, data)
            except Exception as e:
                logger.error(f"Event handler error for {event}: {e}")

    async def _handle_disconnect(self):
        try:
            await self._emit_event("disconnected", {})
        except Exception:
            pass

    def _extract_region_from_url(self, url: str) -> str:
        try:
            for region_name, region_url in REGIONS.get_all_regions().items():
                if region_url == url:
                    return region_name
            parts = url.split("//")[1].split(".")[0]
            if "fr24g1" in parts:
                region = parts.replace("fr24g1", "").upper()
                if region in REGIONS.get_all_regions():
                    return region
            return "UNKNOWN"
        except Exception:
            return "UNKNOWN"

    @property
    def is_connected(self) -> bool:
        return (
            self.websocket is not None
            and not self.websocket.closed
            and self.connection_info
            and self.connection_info.status == ConnectionStatus.CONNECTED
            and self.websocket_is_connected
        )
