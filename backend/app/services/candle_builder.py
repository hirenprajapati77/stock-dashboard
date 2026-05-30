# backend/app/services/candle_builder.py
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd

class CandleBuilder:
    """
    Incremental Event-Driven Candle Builder (SFM-OS Module).
    Constructs rolling 1m, 5m, 15m, and Daily candles from live tick feeds.
    Maintains a thread-safe sliding history buffer of completed candles per symbol.
    """
    
    def __init__(self, max_history_len: int = 200):
        self.max_history_len = max_history_len
        # Nested dictionaries holding rolling state:
        # { symbol: { timeframe: [completed_candle_dict, ...] } }
        self._history: Dict[str, Dict[str, List[Dict]]] = {}
        # { symbol: { timeframe: current_uncompleted_candle_dict } }
        self._current_candles: Dict[str, Dict[str, Dict]] = {}
        # Mutex locks to ensure thread-safety during concurrent tick events
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, symbol: str) -> asyncio.Lock:
        if symbol not in self._locks:
            self._locks[symbol] = asyncio.Lock()
        return self._locks[symbol]

    def _get_timeframe_window(self, dt: datetime, timeframe: str) -> datetime:
        """Calculates the floor boundary timestamp for a specific timeframe."""
        # Convert offset-aware to naive for internal consistency if needed
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

        if timeframe == "1m":
            return dt.replace(second=0, microsecond=0)
        elif timeframe == "5m":
            minute = dt.minute - (dt.minute % 5)
            return dt.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == "15m":
            minute = dt.minute - (dt.minute % 15)
            return dt.replace(minute=minute, second=0, microsecond=0)
        elif timeframe == "1D":
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

    async def process_tick(self, symbol: str, price: float, volume: int, timestamp: datetime) -> List[Tuple[str, Dict]]:
        """
        Processes a raw tick event.
        Returns a list of tuples containing (timeframe, completed_candle) when a candle window completes.
        """
        async with self._get_lock(symbol):
            if symbol not in self._history:
                self._history[symbol] = {"1m": [], "5m": [], "15m": [], "1D": []}
                self._current_candles[symbol] = {"1m": {}, "5m": {}, "15m": {}, "1D": {}}
                
            completed_candles_emitted = []
            
            for tf in ["1m", "5m", "15m", "1D"]:
                window_start = self._get_timeframe_window(timestamp, tf)
                current = self._current_candles[symbol][tf]
                
                if not current:
                    # Initialize first candle for this timeframe
                    self._current_candles[symbol][tf] = {
                        "timestamp": window_start,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": volume
                    }
                elif window_start > current["timestamp"]:
                    # Tick belongs to a new window. Commit previous candle.
                    completed_candle = current.copy()
                    completed_candles_emitted.append((tf, completed_candle))
                    
                    # Store completed candle in history buffer
                    tf_history = self._history[symbol][tf]
                    tf_history.append(completed_candle)
                    if len(tf_history) > self.max_history_len:
                        tf_history.pop(0)
                        
                    # Initialize new current candle
                    self._current_candles[symbol][tf] = {
                        "timestamp": window_start,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": volume
                    }
                else:
                    # Update current candle metrics
                    current["high"] = max(current["high"], price)
                    current["low"] = min(current["low"], price)
                    current["close"] = price
                    current["volume"] += volume
                    
            return completed_candles_emitted

    def get_history_df(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """
        Retrieves the rolling history of completed candles as a Pandas DataFrame.
        Useful for running moving averages and breakout scans in vectorized formats.
        """
        if symbol not in self._history or timeframe not in self._history[symbol]:
            return None
            
        candles = self._history[symbol][timeframe]
        # Append the current in-progress candle so computations are live/current
        current_candle = self._current_candles.get(symbol, {}).get(timeframe)
        
        all_candles = list(candles)
        if current_candle:
            all_candles.append(current_candle)
            
        if not all_candles:
            return None
            
        df = pd.DataFrame(all_candles)
        df.set_index("timestamp", inplace=True)
        return df

    def seed_history(self, symbol: str, timeframe: str, historical_candles: List[Dict]):
        """
        Warm up the builder using historical data.
        """
        if symbol not in self._history:
            self._history[symbol] = {"1m": [], "5m": [], "15m": [], "1D": []}
            self._current_candles[symbol] = {"1m": {}, "5m": {}, "15m": {}, "1D": {}}
            
        # Clear existing
        self._history[symbol][timeframe] = []
        
        for c in sorted(historical_candles, key=lambda x: x["timestamp"]):
            # Make sure timestamps are parsed as datetime objects
            ts = c["timestamp"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", ""))
                
            self._history[symbol][timeframe].append({
                "timestamp": ts,
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": int(c["volume"])
            })
