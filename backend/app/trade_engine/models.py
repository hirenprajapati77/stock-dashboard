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

class MarketCondition(BaseModel):
    market_trend: str # UP, DOWN, SIDEWAYS
    market_bias: str # BULLISH, BEARISH, NEUTRAL
    volatility: str # HIGH, NORMAL, LOW
    strength: str # STRONG, WEAK
    confidence_adjustment: float # +/- points

class Allocation(BaseModel):
    capital_percent: float
    priority_rank: int
    max_positions_allowed: int = 3

class TradeIntent(Enum):
    SCALP = "SCALP"
    INTRADAY = "INTRADAY"
    SWING = "SWING"

class HistoricalPerformance(BaseModel):
    setup_win_rate: float
    avg_rr: float
    confidence_accuracy: float

class MarketRegimeType(Enum):
    TRENDING = "TRENDING"
    MEAN_REVERT = "MEAN_REVERT"
    VOLATILE = "VOLATILE"
    BREAKOUT_PHASE = "BREAKOUT_PHASE"

class MarketRegime(BaseModel):
    regime: MarketRegimeType
    confidence: float
    impact: Dict[str, bool]

class EntryType(Enum):
    MOMENTUM_ENTRY = "MOMENTUM"
    RETEST_ENTRY = "RETEST"
    EARLY_ENTRY = "EARLY"
    LATE_ENTRY = "LATE"
    NONE = "NONE"

class ExitStrategy(BaseModel):
    exit_strategy: str # TRAILING, STATIC, AGGRESSIVE
    dynamic_targets: bool
    early_exit_signal: bool

class Microstructure(BaseModel):
    orderflow_signal: str         # ABSORPTION, MOMENTUM, EXHAUSTION, NEUTRAL
    momentum_quality: str         # STRONG, WEAK
    confidence_adjustment: float

class Liquidity(BaseModel):
    nearest_liquidity_target: Optional[float]
    liquidity_strength: str       # HIGH, MEDIUM, LOW
    distance_to_liquidity: float  # pct

class Scaling(BaseModel):
    scaling_allowed: bool
    add_position_level: Optional[float]
    max_additions: int

class DrawdownStatus(BaseModel):
    status: str    # SAFE, WARNING, STOP
    action: str    # CONTINUE, REDUCE, HALT

class MetaScore(BaseModel):
    meta_score: float
    trade_grade: str              # A+, A, B, C, D
    final_decision: str           # EXECUTE, WATCH, REJECT

class TradeDecision(BaseModel):
    symbol: str
    action: ActionType
    setup: SetupType
    setup_state: SetupState
    entry: float
    stop_loss: float
    targets: List[float]
    confidence: float             # 0-100
    quality: TradeQuality
    quality_score: float          # 0-100
    entry_status: EntryStatus
    entry_type: EntryType
    state: TradeState
    intent: TradeIntent
    allocation: Allocation
    market_context: MarketCondition
    market_regime: MarketRegime
    microstructure: Microstructure
    liquidity: Liquidity
    confluence_score: float
    exit_strategy: ExitStrategy
    meta_score: MetaScore
    scaling: Scaling
    drawdown_status: DrawdownStatus
    narrative: str
    historical_performance: HistoricalPerformance
    validity: str
    reason: List[str]
    warnings: List[str]
    next_action: str
    option_strike: Optional[str] = None
    option_strategy: str = "SAFE"
    risk_reward: float
    state_message: str
    session: str = "MID"

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
    daily_volume_ratio: float = 1.0
    trend: str # "BULLISH", "BEARISH", "SIDEWAYS"
    higher_tf_trend: str = "NEUTRAL"
    oi_data: Optional[Dict[str, Any]] = None
    candles_since_setup: int = 0
