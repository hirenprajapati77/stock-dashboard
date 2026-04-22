from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum

class ActionType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"

class SetupType(Enum):
    BREAKOUT = "BREAKOUT"
    BREAKDOWN = "BREAKDOWN"
    RANGE_BOUND = "RANGE_BOUND"
    RETEST = "RETEST"
    NONE = "NONE"

class SetupState(Enum):
    FORMING = "FORMING"
    READY = "READY"
    TRIGGERED = "TRIGGERED"
    INVALID = "INVALID"

class EntryStatus(Enum):
    EARLY = "EARLY"
    IDEAL = "IDEAL"
    LATE = "LATE"
    NONE = "NONE"

class TradeQuality(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class TradeState(Enum):
    WAITING = "WAITING"
    TRIGGERED = "TRIGGERED"
    RUNNING = "RUNNING"
    TARGET1_HIT = "TARGET1_HIT"
    TARGET2_HIT = "TARGET2_HIT"
    SL_HIT = "SL_HIT"
    CLOSED = "CLOSED"

class TradeDecision(BaseModel):
    symbol: str
    action: ActionType
    setup: SetupType
    setup_state: SetupState
    entry: float
    stop_loss: float
    targets: List[float]
    confidence: float # 0-100
    quality: TradeQuality
    quality_score: float # 0-100
    entry_status: EntryStatus
    state: TradeState
    validity: str
    reason: List[str]
    warnings: List[str]
    next_action: str
    option_strike: Optional[str] = None
    option_strategy: str = "SAFE" # MOMENTUM, SAFE, AGGRESSIVE
    risk_reward: float
    state_message: str

class MarketContext(BaseModel):
    symbol: str
    price: float
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    supports: List[float]
    resistances: List[float]
    atr: float
    adx: float
    volume_ratio: float
    trend: str # "BULLISH", "BEARISH", "SIDEWAYS"
    higher_tf_trend: str = "NEUTRAL"
    oi_data: Optional[Dict[str, Any]] = None
    candles_since_setup: int = 0
