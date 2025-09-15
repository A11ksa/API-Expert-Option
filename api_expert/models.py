"""Pydantic models for type safety and validation in ExpertOption API"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class OrderDirection(str, Enum):
    CALL = "call"
    PUT = "put"

class OrderStatus(str, Enum):
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
    count_unseen: int = 0
    has_priority: bool = False

class MultipleActionResponse(BaseModel):
    actions: List[Dict[str, Any]]
    success: bool = True

class EnvironmentInfo(BaseModel):
    supportedFeatures: List[str] = Field(default_factory=list)
    supportedAbTests: List[str] = Field(default_factory=list)
    supportedInventoryItems: List[str] = Field(default_factory=list)
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
    type: str
    payout: int = 0
    is_otc: bool = False
    is_open: bool = True
    available_timeframes: List[int] = Field(default_factory=lambda: [60,120,180,300,420,600,900,1200,1800,2700,3600,7200,10800,14400])
    is_active: bool = True
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

# >>> Fixed to match client usage, while keeping backward fields for compatibility
class Order(BaseModel):
    order_id: str
    asset_id: int
    symbol: str
    amount: float
    direction: OrderDirection
    duration: int
    # New fields used by client:
    open_time: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    refund: float = 0.0
    # Backward-compatible fields:
    id: Optional[int] = None
    status: OrderStatus = OrderStatus.PENDING
    placed_at: Optional[float] = None  # legacy float timestamp

    class Config:
        frozen = True

class OrderResult(BaseModel):
    order_id: str
    server_id: Optional[str] = None
    asset: Optional[str] = None
    asset_id: Optional[int] = None
    amount: Optional[float] = None
    direction: Optional[OrderDirection] = None
    duration: Optional[int] = None
    status: Optional[OrderStatus] = None
    # New naming used by client:
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    # Legacy naming for compatibility:
    placed_at: Optional[datetime] = None
    # Pricing:
    open_price: Optional[float] = None
    close_price: Optional[float] = None
    profit: Optional[float] = None
    payout: Optional[float] = None
    error_message: Optional[str] = None
    latest_price: Optional[float] = None
    uid: Optional[int] = None

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

# New lightweight models for new actions
class PushNotification(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    created_at: Optional[int] = None
    read: Optional[bool] = None

class Achievement(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    progress: Optional[float] = None
    completed: Optional[bool] = None

class Badge(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    level: Optional[int] = None
    obtained_at: Optional[int] = None

class ActivatedBonus(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    percent: Optional[float] = None
    expires_at: Optional[int] = None

class ReferralOfferInfo(BaseModel):
    active: Optional[bool] = None
    reward_percent: Optional[float] = None
    code: Optional[str] = None

class DepositSum(BaseModel):
    total_usd: Optional[float] = None
    currency: Optional[str] = None

class TradeHistoryEntry(BaseModel):
    id: Optional[int] = None
    asset_id: Optional[int] = None
    amount: Optional[float] = None
    direction: Optional[OrderDirection] = None
    open_price: Optional[float] = None
    close_price: Optional[float] = None
    status: Optional[OrderStatus] = None
    opened_at: Optional[int] = None
    closed_at: Optional[int] = None
