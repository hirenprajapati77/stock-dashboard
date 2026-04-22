"""
FyersSocketService - Production-Grade WebSocket Streaming
==========================================================
Architecture:
  - Connects to Fyers V3 Data WebSocket
  - Receives price ticks and coalesces them into 300ms batch windows
  - Uses a Set (not Queue) for coalescing: O(1) deduplication, bounded memory
  - Dispatches to ScreenerService.update_symbol_realtime (per-symbol async locked)
  - Smart watchdog: reconnects ONLY when market is open
  - Capped exponential backoff (max 30s)
  - Immediate reconnect on auth failure (token refresh + retry)

Safeguards:
  - Set swap is protected by asyncio.Lock (_pending_lock)
  - No tick-level processing: only batch-level (300ms window)
  - Health metrics updated per batch, not per tick
  - Watchdog dormant during market closed / holidays
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, InvalidStatusCode
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False
    print("WARNING: [FyersSocket] 'websockets' library not installed. Real-time streaming disabled.", flush=True)

from app.utils.market_calendar import MarketCalendar
from app.services.fyers_service import FyersService
from app.config import fyers_config


# Fyers V3 WebSocket endpoint
_WS_URL = "wss://api-t1.fyers.in/socket/v3/data"

# Batch window duration (ms → s)
_BATCH_INTERVAL_S = 0.300  # 300ms coalescing window

# Watchdog: reconnect if no ticks for this long during open market
_INACTIVITY_TIMEOUT_S = 60

# Reconnect backoff settings
_BACKOFF_BASE_S  = 1.0
_BACKOFF_MAX_S   = 30.0
_BACKOFF_FACTOR  = 2.0


class FyersSocketService:
    """
    Manages a persistent Fyers V3 Data WebSocket connection.
    Coalesces incoming ticks into 300ms batch windows before dispatching
    to ScreenerService for incremental signal recomputation.
    """

    # --- State ---
    _running: bool = False
    _ws = None               # Active websocket connection object

    # Tick coalescing
    _pending_updates: Set[str] = set()
    _pending_lock: asyncio.Lock = asyncio.Lock()

    # Latest price/volume per symbol (for dispatch to screener)
    _latest_ticks: Dict[str, Dict] = {}

    # Watchdog
    _last_tick_time: float = 0.0

    # Monitoring metrics
    _metrics: Dict = {
        "connected": False,
        "connect_time": None,
        "total_ticks": 0,
        "total_batches": 0,
        "symbols_updated_per_batch": 0,
        "reconnect_count": 0,
        "last_error": None,
    }

    # Symbols to subscribe (populated at startup from screener)
    _symbols: List[str] = []

    @classmethod
    def register_symbols(cls, symbols: List[str]):
        """Register which Fyers-format symbols to stream (e.g. NSE:SBIN-EQ)."""
        cls._symbols = list(symbols)

    @classmethod
    def get_metrics(cls) -> Dict:
        return dict(cls._metrics)

    # -----------------------------------------------------------------------
    # PUBLIC LIFECYCLE
    # -----------------------------------------------------------------------

    @classmethod
    async def start(cls, symbols: Optional[List[str]] = None):
        """
        Entry point: called from the FastAPI lifespan.
        Starts the connection loop and the 300ms batch dispatcher concurrently.
        """
        if not _WS_AVAILABLE:
            print("[FyersSocket] Disabled: 'websockets' package not available.", flush=True)
            return

        if symbols:
            cls._symbols = symbols

        cls._running = True
        print(f"[FyersSocket] Starting with {len(cls._symbols)} symbols.", flush=True)

        # Run connection loop and batch dispatcher concurrently
        await asyncio.gather(
            cls._connection_loop(),
            cls._batch_loop(),
        )

    @classmethod
    async def stop(cls):
        """Graceful shutdown."""
        cls._running = False
        if cls._ws:
            try:
                await cls._ws.close()
            except Exception:
                pass
        print("[FyersSocket] Stopped.", flush=True)

    # -----------------------------------------------------------------------
    # CONNECTION LOOP (Reconnect with backoff)
    # -----------------------------------------------------------------------

    @classmethod
    async def _connection_loop(cls):
        """
        Outer reconnection loop with capped exponential backoff.
        Handles token expiry as a special fast-path (immediate retry).
        """
        backoff = _BACKOFF_BASE_S
        auth_failure = False

        while cls._running:
            # --- Market Check: Don't reconnect when all markets are closed ---
            if not auth_failure and not MarketCalendar.is_market_open():
                print("[FyersSocket] Market closed. Watchdog sleeping for 60s.", flush=True)
                await asyncio.sleep(60)
                continue

            try:
                await cls._connect_and_stream()
                # Successful session ended cleanly
                backoff = _BACKOFF_BASE_S
                auth_failure = False

            except _AuthFailure:
                # Token expired: reload from disk and retry immediately
                print("[FyersSocket] Auth failure. Reloading token and retrying...", flush=True)
                cls._metrics["reconnect_count"] += 1
                FyersService.load_token()
                auth_failure = True
                await asyncio.sleep(1)  # Brief pause before retry

            except Exception as e:
                cls._metrics["last_error"] = str(e)
                cls._metrics["reconnect_count"] += 1
                print(f"[FyersSocket] Connection error: {e}. Retrying in {backoff:.0f}s.", flush=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_MAX_S)
                auth_failure = False

    # -----------------------------------------------------------------------
    # CONNECT AND STREAM TICKS
    # -----------------------------------------------------------------------

    @classmethod
    async def _connect_and_stream(cls):
        """
        Opens a WebSocket, authenticates, subscribes, and streams ticks.
        Raises _AuthFailure on 401. Raises other exceptions for backoff.
        """
        token = FyersService._access_token
        if not token:
            raise Exception("No access token available.")

        app_id = fyers_config.app_id
        auth_header = f"{app_id}:{token}"

        connect_kwargs = {
            "additional_headers": {"Authorization": auth_header},
            "ping_interval": 20,
            "ping_timeout": 10,
        }

        print(f"[FyersSocket] Connecting to {_WS_URL}...", flush=True)
        async with websockets.connect(_WS_URL, **connect_kwargs) as ws:
            cls._ws = ws
            cls._metrics["connected"] = True
            cls._metrics["connect_time"] = datetime.now().isoformat()
            cls._last_tick_time = time.time()

            print("[FyersSocket] Connected. Subscribing to symbols...", flush=True)
            await cls._subscribe(ws)

            # Watchdog task for this session
            watchdog_task = asyncio.create_task(cls._watchdog())

            try:
                async for raw_msg in ws:
                    if not cls._running:
                        break
                    cls._on_message(raw_msg)
            except ConnectionClosed as e:
                code = getattr(e, 'code', None) or getattr(getattr(e, 'rcvd', None), 'code', None)
                if code in (401, 403):
                    raise _AuthFailure()
                raise
            finally:
                watchdog_task.cancel()
                cls._ws = None
                cls._metrics["connected"] = False

    # -----------------------------------------------------------------------
    # AUTH & SUBSCRIPTION
    # -----------------------------------------------------------------------

    @classmethod
    async def _subscribe(cls, ws):
        """Send Fyers V3 symbol subscription payload."""
        if not cls._symbols:
            print("[FyersSocket] No symbols registered. Skipping subscription.", flush=True)
            return

        payload = {
            "T": "SUB_L2",
            "L2List": cls._symbols,
            "SUB_T": 1  # 1 = subscribe, 0 = unsubscribe
        }
        await ws.send(json.dumps(payload))
        print(f"[FyersSocket] Subscribed to {len(cls._symbols)} symbols.", flush=True)

    # -----------------------------------------------------------------------
    # TICK HANDLER: Set-based coalescing
    # -----------------------------------------------------------------------

    @classmethod
    def _on_message(cls, raw_msg: str):
        """
        Handles incoming tick. Adds symbol to the pending Set (not Queue).
        This is synchronous and very fast — no computation here.
        """
        try:
            msg = json.loads(raw_msg)
        except Exception:
            return

        # Fyers V3 sends a list of tick dicts
        ticks = msg if isinstance(msg, list) else [msg]
        for tick in ticks:
            symbol = tick.get("symbol") or tick.get("n")
            ltp    = tick.get("ltp") or tick.get("v", {}).get("ltp")
            vol    = tick.get("vol_traded_today") or tick.get("v", {}).get("volume", 0)

            if not symbol or ltp is None:
                continue

            cls._metrics["total_ticks"] += 1
            cls._last_tick_time = time.time()

            # Store latest price/volume (overwrites older tick for same symbol)
            cls._latest_ticks[symbol] = {"price": float(ltp), "volume": float(vol)}

            # Add to pending set (thread-safe set.add is atomic in CPython)
            # The batch loop will drain this set with a lock
            cls._pending_updates.add(symbol)

    # -----------------------------------------------------------------------
    # BATCH LOOP: 300ms window dispatcher
    # -----------------------------------------------------------------------

    @classmethod
    async def _batch_loop(cls):
        """
        Runs every 300ms. Atomically swaps the pending Set, then dispatches
        ScreenerService.update_symbol_realtime for each unique symbol.
        Updates metrics once per batch.
        """
        from app.services.screener_service import ScreenerService

        while cls._running:
            await asyncio.sleep(_BATCH_INTERVAL_S)

            # Atomically take a snapshot of the pending set and clear it
            async with cls._pending_lock:
                if not cls._pending_updates:
                    continue
                batch = cls._pending_updates.copy()
                cls._pending_updates.clear()

            if not batch:
                continue

            cls._metrics["total_batches"] += 1
            cls._metrics["symbols_updated_per_batch"] = len(batch)

            # Update the screener's symbols_updated_per_batch metric
            from app.services.screener_service import ScreenerService as _SS
            _SS._last_metrics["symbols_updated_per_batch"] = len(batch)

            # Dispatch recomputations concurrently (each symbol is independently locked inside)
            tasks = []
            for symbol in batch:
                tick = cls._latest_ticks.get(symbol)
                if tick:
                    tasks.append(
                        ScreenerService.update_symbol_realtime(
                            symbol, tick["price"], tick["volume"]
                        )
                    )

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    # -----------------------------------------------------------------------
    # WATCHDOG
    # -----------------------------------------------------------------------

    @classmethod
    async def _watchdog(cls):
        """
        Monitors for inactivity. Closes the socket if no ticks received
        for 60s while at least one market is open.
        Sleeping harmlessly during market-closed periods.
        """
        while cls._running and cls._ws:
            await asyncio.sleep(15)  # Check every 15s
            elapsed = time.time() - cls._last_tick_time

            # Only alert/reconnect if market is currently open
            if MarketCalendar.is_market_open() and elapsed > _INACTIVITY_TIMEOUT_S:
                print(
                    f"[FyersSocket] WATCHDOG: No ticks for {elapsed:.0f}s during open market. "
                    "Forcing reconnect.",
                    flush=True
                )
                if cls._ws:
                    await cls._ws.close()
                return


class _AuthFailure(Exception):
    """Raised when Fyers WebSocket returns a 401/403."""
    pass
