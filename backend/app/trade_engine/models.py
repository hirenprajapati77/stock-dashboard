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
    NONE = "NONE"

class TradeDecision(BaseModel):
    symbol: str
    action: ActionType
    setup: SetupType
    entry: float
    stop_loss: float
    targets: List[float]
    confidence: float
    validity: str
    reason: List[str]
    option_strike: Optional[str] = None
    risk_reward: float

class MarketContext(BaseModel):
    symbol: str
    price: float
    supports: List[float]
    resistances: List[float]
    atr: float
    adx: float
    trend: str # "BULLISH", "BEARISH", "SIDEWAYS"
    oi_data: Optional[Dict[str, Any]] = None
