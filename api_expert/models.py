"""Pydantic models for type safety and validation in ExpertOption API"""
import time
import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class OrderDirection(str, Enum):
    CALL = "call"
    PUT = "put"

class OrderStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"

class TradersChoice(BaseModel):
    asset_id: Optional[int] = None
    put: Optional[int] = None
    call: Optional[int] = None

class UserFeedInfo(BaseModel):
    count_unseen: int
    has_priority: bool

class MultipleActionResponse(BaseModel):
    actions: List[Dict[str, Any]]
    success: bool = True

class EnvironmentInfo(BaseModel):
    supportedFeatures: List[str]
    supportedAbTests: List[str]
    supportedInventoryItems: List[str]
    sessionTs: Optional[int] = None
    isBonusAvaliable: Optional[bool] = None

class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    RECONNECTING = "reconnecting"

class TimeFrame(int, Enum):
    S1 = 1
    S5 = 5
    S10 = 10
    S15 = 15
    S30 = 30
    M1 = 60
    M5 = 300
    M15 = 900
    M30 = 1800
    H1 = 3600
    H4 = 14400
    D1 = 86400
    W1 = 604800
    MN1 = 2592000

class Asset(BaseModel):
    id: int
    symbol: str
    name: str
    type: int
    payout: float
    is_otc: bool
    is_open: bool
    available_timeframes: List[int]

    class Config:
        frozen = True

class Balance(BaseModel):
    balance: float
    currency: str = "USD"
    is_demo: bool = True
    last_updated: datetime = Field(default_factory=datetime.now)

    class Config:
        frozen = True

class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    asset: str
    timeframe: int

    class Config:
        frozen = True

class Order(BaseModel):
    order_id: Optional[str] = None 
    asset_id: Optional[int] = None
    symbol: Optional[str] = None
    amount: float
    direction: OrderDirection
    duration: Optional[int] = None  # Added duration
    open_time: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    open_price: Optional[float] = None
    close_price: Optional[float] = None
    profit: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    refund: Optional[float] = 0.0

    class Config:
        frozen = True

class OrderResult(BaseModel):
    order_id: str
    server_id: Optional[str] = None
    asset_id: int
    asset: str
    amount: float
    direction: OrderDirection
    duration: int  # Added duration
    created_at: datetime
    expires_at: datetime
    open_price: float
    close_price: Optional[float] = None
    profit: Optional[float] = None
    payout: Optional[float] = None  # Added payout
    status: OrderStatus
    error_message: Optional[str] = None

    class Config:
        frozen = True

class ServerTime(BaseModel):
    server_timestamp: float
    local_timestamp: float
    offset: float
    last_sync: datetime = Field(default_factory=datetime.now)

    class Config:
        frozen = True

class ConnectionInfo(BaseModel):
    url: str
    region: str
    status: ConnectionStatus
    connected_at: Optional[datetime] = None
    last_ping: Optional[datetime] = None
    reconnect_attempts: int = 0

    class Config:
        frozen = True
