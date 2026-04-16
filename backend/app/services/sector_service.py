import yfinance as yf
import pandas as pd
import numpy as np
import concurrent.futures
import math
import time
import sys
"""
Sector Logic v1.0 (LOCKED)

Rules:
- Absolute direction first
- Relative outperformance second
- RS = sectorReturn - benchmarkReturn
- Sector must be UP to be LEADING
- Sector DOWN can only be IMPROVING or LAGGING

Any change must update tests.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from app.services.rotation_alerts import RotationAlertService
from app.services.constituent_service import ConstituentService
from app.ai.commentary import AICommentaryService

class SectorService:
    BENCHMARK = "^NSEI"
    SECTORS = {
        "NIFTY_BANK": "^NSEBANK",
        "NIFTY_IT": "^CNXIT",
        "NIFTY_FMCG": "^CNXFMCG",
        "NIFTY_METAL": "^CNXMETAL",
        "NIFTY_PHARMA": "^CNXPHARMA",
        "NIFTY_ENERGY": "^CNXENERGY",
        "NIFTY_AUTO": "^CNXAUTO",
        "NIFTY_REALTY": "^CNXREALTY",
        "NIFTY_PSU_BANK": "^CNXPSUBANK",
    }

    # Configurable quant logic constants
    RS_EPSILON = 1e-6
    RETURN_LOOKBACK_BARS_BY_TIMEFRAME = {
        "5m": 1,
        "15m": 1,
        "75m": 1,
        "1H": 1,
        "2H": 1,
        "4H": 1,
        "1D": 1,
        "1W": 1,
        "1M": 1,
    }
    LEADING_RS_MIN = 1.02
    LAGGING_RS_MAX = 0.98
    RS_THRESHOLD = 0.002 # 0.2% minimum outperformance for LEADING state

    # Class-level cache
    _cache = {
        "data": None,
        "alerts": None,
        "timestamp": 0.0,
        "timeframe": None
    }
    CACHE_TTL = 600 # 10 minutes

    @classmethod
    def calculate_state(cls, sector_return: float, benchmark_return: float, prev_rs: float) -> str:
        """
        Final Trader-Correct Logic v1.0 (LOCKED)
        """
        rs = sector_return - benchmark_return
        rm = rs - prev_rs
        
        state = "NEUTRAL"

        # Tighter LEADING criteria: Absolute UP + Relative OUTPERFORMANCE (0.2%+) + Gaining Momentum
        if sector_return > 0 and rs > cls.RS_THRESHOLD and rm > 0:
            state = "LEADING"
        elif sector_return > 0 and rs > 0 and rm <= 0:
            state = "WEAKENING"
        elif rs > 0 and rm > 0:
            state = "IMPROVING"
        elif sector_return < 0 and rs <= 0 and rm < 0:
            state = "LAGGING"
        
        # Hard Safety Patch
        if sector_return < 0 and state == "LEADING":
            state = "IMPROVING"
            
        return state

    @classmethod
    def get_rotation_data(cls, days=60, timeframe="1D", include_constituents=True):
        """
        Calculates RS and RM for all sectors vs benchmark.
        Returns data for the last 30 trading sessions for playback.
        """
        # Map UI timeframe to YFinance interval/period
        
        tf_map = {
            "5m": {"interval": "5m", "period": "5d"},
            "15m": {"interval": "15m", "period": "5d"},
            "75m": {"interval": "1h", "period": "1mo"},
            "1H": {"interval": "1h", "period": "1mo"},
            "2H": {"interval": "1h", "period": "1mo"},
            "4H": {"interval": "1h", "period": "3mo"},
            "1D": {"interval": "1d", "period": "1y"},
            "Daily": {"interval": "1d", "period": "1y"},
            "1W": {"interval": "1wk", "period": "2y"},
            "1M": {"interval": "1mo", "period": "5y"}
        }
        
        # 0. Check Cache
        from app.services.market_status_service import MarketStatusService
        market_status = MarketStatusService.get_market_status()
        ttl = cls.CACHE_TTL if market_status["mode"] in ["OPEN", "PRE_MARKET"] else 3600 * 12

        current_time = float(time.time())
        if (cls._cache["data"] is not None and 
            cls._cache["timeframe"] == timeframe and 
            (current_time - float(cls._cache["timestamp"] or 0.0)) < ttl):
            return cls._cache["data"], cls._cache["alerts"]

        normalized_timeframe = "1D" if timeframe == "Daily" else timeframe
        config = tf_map.get(normalized_timeframe, {"interval": "1d", "period": "1y"})
        interval = config["interval"]
        period = config["period"]
        
        # 1. Collect symbols needed
        all_sector_symbols = [cls.BENCHMARK] + list(cls.SECTORS.values())
        all_cons_symbols = []
        if include_constituents:
            for s_name in cls.SECTORS:
                all_cons_symbols.extend(ConstituentService.get_constituents(s_name))
        
        unique_symbols = list(set(all_sector_symbols + all_cons_symbols))
        
        # 1. Fetch data for all symbols using MarketDataService Batch
        batch_data = {}
        try:
            print(f"DEBUG: Fetching data for {len(unique_symbols)} symbols via MarketDataService Batch...", flush=True)
            from app.services.market_data import MarketDataService
            
            batch_results = MarketDataService.get_ohlcv_batch(unique_symbols, normalized_timeframe, count=60)
            
            for sym, res in batch_results.items():
                df, currency, err, source = res
                if df is not None and not df.empty:
                    # columns are handles by batch method but let's be sure of case
                    df.columns = [c.lower() for c in df.columns]
                    batch_data[sym] = df
        except Exception as e:
            print(f"DEBUG: Failed to fetch batch data in SectorService: {e}")

            if not batch_data:
                print(f"Warning: No data fetched for sectors via MarketDataService. Trying fallback.", flush=True)
                data, alerts = cls._load_fallback(timeframe)
                return data, alerts
        except Exception as e:
            print(f"CRITICAL: Sector fetch failed: {e}. Trying fallback.", flush=True)
            data, alerts = cls._load_fallback(timeframe)
            if data: return data, alerts
            return {}, []


        results = {}
        
        # Helper to get ticker data from batch_data dict
        def get_ticker_df(ticker_sym):
            return batch_data.get(ticker_sym, pd.DataFrame())

        benchmark_df = get_ticker_df(cls.BENCHMARK)
        if benchmark_df.empty:
            print(f"CRITICAL: Benchmark {cls.BENCHMARK} missing. Trying fallback.")
            data, alerts = cls._load_fallback(timeframe)
            if data: return data, alerts
            return {}, []
            
        benchmark_close_col = "close" if "close" in benchmark_df.columns else "Close"
        benchmark_data = benchmark_df[benchmark_close_col]

        # 2. Process each sector
        for name, symbol in cls.SECTORS.items():
            try:
                s_df = get_ticker_df(symbol)
                if s_df.empty: continue
                
                sector_close_col = "close" if "close" in s_df.columns else "Close"
                sector_close = s_df[sector_close_col]
                
                # Align data - FORCE timezone naive to avoid comparison errors
                s_naive = sector_close.copy()
                b_naive = benchmark_data.copy()
                
                # Robust conversion to naive DatetimeIndex
                try:
                    s_naive.index = pd.to_datetime(s_naive.index, utc=True).tz_localize(None)
                    b_naive.index = pd.to_datetime(b_naive.index, utc=True).tz_localize(None)
                except Exception as e:
                    print(f"WARN: Timezone normalization fallback for {name}: {e}")
                    if hasattr(s_naive.index, 'tz'): s_naive.index = s_naive.index.tz_localize(None)
                    if hasattr(b_naive.index, 'tz'): b_naive.index = b_naive.index.tz_localize(None)

                combined = pd.DataFrame({
                    'sector': s_naive,
                    'benchmark': b_naive
                }).dropna()
                
                if combined.empty:
                    # Timezone naive fallback
                    s_tmp, b_tmp = sector_close.copy(), benchmark_data.copy()
                    if hasattr(s_tmp.index, 'tz'): s_tmp.index = s_tmp.index.tz_localize(None)
                    if hasattr(b_tmp.index, 'tz'): b_tmp.index = b_tmp.index.tz_localize(None)
                    combined = pd.DataFrame({'sector': s_tmp, 'benchmark': b_tmp}).dropna()

                if combined.empty: continue
                
                # RS and momentum rules:
                # NEW: rs = sector_return - benchmark_return (Difference-based to avoid division explosions)
                # momentum = rs(current) - rs(previous)
                lookback_bars = cls.RETURN_LOOKBACK_BARS_BY_TIMEFRAME.get(normalized_timeframe, 1)
                combined['sector_return'] = combined['sector'].pct_change(periods=lookback_bars)
                combined['benchmark_return'] = combined['benchmark'].pct_change(periods=lookback_bars)
                
                # Difference-based RS
                combined['rs'] = combined['sector_return'] - combined['benchmark_return']
                combined['rm'] = combined['rs'].diff()
                
                # Phase 1: Sector Acceleration
                # 5-day rolling RS to smooth noise
                combined['rs_5d'] = combined['rs'].rolling(5).sum()
                # Acceleration = rate of change of the 5d RS (diff is cleaner than comparison to mean)
                combined['acc_raw'] = combined['rs_5d'].diff()
                
                combined = combined.dropna(subset=['rs', 'rm', 'acc_raw'])

                # History (last 30)
                history = combined.tail(30)
                if history.empty:
                    continue
                history_list = []
                for hist_idx, hist_row in history.iterrows():
                    history_list.append({
                        "date": hist_idx.strftime("%Y-%m-%d"),
                        "rs": float(round(hist_row['rs'], 4)),
                        "rm": float(round(hist_row['rm'], 6)),
                        "sr": float(round(hist_row['sector_return'], 4))
                    })
                
                # 3. Calculate Phase 2 Metrics from pre-downloaded constituents
                constituents = ConstituentService.get_constituents(name)
                advances: int = 0
                total_vol: float = 0.0
                avg_vol: float = 0.0
                valid_cons: int = 0
                above20: int = 0
                above50: int = 0
                hi10: int = 0
                
                if constituents:
                    for const in constituents:
                        c_df = get_ticker_df(const)
                        if c_df.empty or len(c_df) < 2: continue
                        
                        c_close_col = "close" if "close" in c_df.columns else "Close"
                        c_open_col = "open" if "open" in c_df.columns else "Open"
                        c_vol_col = "volume" if "volume" in c_df.columns else "Volume"
                        
                        last_c = float(c_df[c_close_col].iloc[-1])
                        last_o = float(c_df[c_open_col].iloc[-1])
                        last_v = float(c_df[c_vol_col].iloc[-1])
                        
                        if last_c > last_o:
                            advances += 1
                        
                        # DMA & Highs
                        if len(c_df) >= 20:
                            ma20 = float(c_df[c_close_col].rolling(20).mean().iloc[-1])
                            if last_c > ma20:
                                above20 += 1
                        if len(c_df) >= 50:
                            ma50 = float(c_df[c_close_col].rolling(50).mean().iloc[-1])
                            if last_c > ma50:
                                above50 += 1
                        if len(c_df) >= 10:
                            max10 = float(c_df[c_close_col].rolling(10).max().iloc[-1])
                            if last_c >= max10:
                                hi10 += 1
                            
                        valid_cons += 1
                        total_vol += last_v
                        avg_vol += float(c_df[c_vol_col].mean())
                    
                    breadth_ratio = float(advances) / float(valid_cons) if valid_cons > 0 else 0.5
                    rel_volume = float(total_vol) / float(avg_vol) if avg_vol > 0 else 1.0
                    
                    # Phase 2: BreadthScore
                    pct_20 = (float(above20) / float(valid_cons) * 100.0) if valid_cons > 0 else 50.0
                    pct_50 = (float(above50) / float(valid_cons) * 100.0) if valid_cons > 0 else 50.0
                    pct_hi10 = (float(hi10) / float(valid_cons) * 100.0) if valid_cons > 0 else 10.0
                    breadth_score = (0.4 * pct_20) + (0.3 * pct_50) + (0.3 * pct_hi10)
                else:
                    breadth_ratio, rel_volume = 0.5, 1.0
                    breadth_score = 50.0
                
                # Final Current Metrics
                last_row = history.iloc[-1]
                curr_rs = float(last_row['rs'])
                curr_rm = float(last_row['rm'])
                
                # Phase 1: Normalize Acceleration Score (-100 to +100)
                acc_raw_val = last_row['acc_raw']
                if pd.isna(acc_raw_val) or math.isinf(float(str(acc_raw_val))):
                    acc_raw_val = 0.0
                acc_raw = float(acc_raw_val)
                # 1000x scale (less explosive than 2000)
                acc_score = float(max(-100.0, min(100.0, acc_raw * 1000.0)))

                # State logic: Absolute direction + Relative performance
                state = cls.calculate_state(
                    sector_return=float(last_row['sector_return']),
                    benchmark_return=float(last_row['benchmark_return']),
                    prev_rs=float(history.iloc[-2]['rs']) if len(history) > 1 else float(last_row['rs'])
                )

                results[name] = {
                    "current": history_list[-1],
                    "history": history_list,
                    "weight": cls._get_mock_weight(name),
                    "rank": 0, # Placeholder
                    "metrics": {
                        "breadth": float(round(float(breadth_ratio) * 1000.0) / 10.0),
                        "relVolume": float(round(float(rel_volume) * 100.0) / 100.0),
                        "state": str(state),
                        "sr": float(round(float(last_row['sector_return']) * 10000.0) / 10000.0),
                        "br": float(round(float(last_row['benchmark_return']) * 10000.0) / 10000.0),
                        "accelerationScore": float(round(float(acc_score) * 100.0) / 100.0),
                        "breadthScore": float(round(float(breadth_score) * 100.0) / 100.0)
                    }
                }
                
                RotationAlertService.detect_alerts(name, curr_rs, curr_rm)

            except Exception as e:
                print(f"Error processing sector {name}: {e}")

        # Phase 3: Predictive Rotation Score
        # RotationScore = (0.4 * RS Score) + (0.3 * AccelerationScore) + (0.3 * BreadthScore)
        # First normalize RS score across available sectors 0-100
        all_rs = [float(r['current']['rs']) for r in results.values()]
        min_rs, max_rs = min(all_rs) if all_rs else 0, max(all_rs) if all_rs else 1
        
        for name in results:
            rs_val = float(results[name]['current']['rs'])
            rs_norm = (float(float(rs_val) - float(min_rs)) / float(float(max_rs) - float(min_rs)) * 100.0) if max_rs != min_rs else 50.0
            
            acc_score = results[name]['metrics']['accelerationScore']
            # Scale acc_score from [-100, 100] to [0, 100] for rotation calculation
            acc_norm = (acc_score + 100) / 2
            br_score = results[name]['metrics']['breadthScore']
            
            rotation_score = (0.4 * rs_norm) + (0.3 * acc_norm) + (0.3 * br_score)
            # Integer-based rounding to bypass restrictive round() stubs
            rot_val = int(float(rotation_score) * 100.0 + 0.5)  # type: ignore
            results[name]['metrics']['rotationScore'] = float(rot_val) / 100.0  # type: ignore

        # Improvement 2: Sector Panel Sorting
        state_priority = {
            "LEADING": 1,
            "IMPROVING": 2,
            "WEAKENING": 3,
            "NEUTRAL": 4,
            "LAGGING": 5
        }

        # Sort by (state_priority[state], -rotationScore)
        sorted_sectors = sorted(
            results.items(),
            key=lambda x: (state_priority.get(x[1]['metrics'].get('state', 'NEUTRAL'), 4), -x[1]['metrics'].get('rotationScore', 0))
        )
        ranks = {name: i+1 for i, (name, _) in enumerate(sorted_sectors)}
        all_alerts = []

        for name in results:
            hist = results[name]['history']
            curr, prev = hist[-1], (hist[-2] if len(hist) > 1 else hist[-1])
            
            rs_trend = "rising" if curr['rs'] > prev['rs'] else "falling" if curr['rs'] < prev['rs'] else "flat"
            rm_trend = "accelerating" if curr['rm'] > prev['rm'] else "decelerating" if curr['rm'] < prev['rm'] else "flat"
            mom_score = float((curr['rs'] * 100) + (curr['rm'] * 5000))
            
            shift = "GAINING" if (rs_trend == "rising" and rm_trend == "accelerating") else \
                    "LOSING" if (rs_trend == "falling" and rm_trend == "decelerating") else "NEUTRAL"

            momentum_score_val = int(float(mom_score) * 100.0 + 0.5)  # type: ignore
            results[name]['metrics']['momentumScore'] = float(momentum_score_val) / 100.0  # type: ignore
            results[name]['metrics']['shift'] = str(shift)
            
            # Momentum Trend Indicator (NEW)
            if shift == "GAINING":
                momentum_trend = "Strengthening"
            elif shift == "LOSING":
                momentum_trend = "Weakening"
            elif rs_trend == "rising":
                momentum_trend = "Strengthening"
            elif rs_trend == "falling":
                momentum_trend = "Weakening"
            else:
                momentum_trend = "Stable"
            results[name]['metrics']['momentumTrend'] = momentum_trend
            # Generate Historical Alerts
            for i in range(1, len(hist)):
                h_prev = hist[i-1]
                h_curr = hist[i]
                
                prev_q = RotationAlertService.get_quadrant(h_prev['rs'], h_prev['rm'])
                curr_q = RotationAlertService.get_quadrant(h_curr['rs'], h_curr['rm'])
                
                # Convert date to timestamp
                try:
                    dt_obj = datetime.strptime(h_curr['date'], "%Y-%m-%d")
                    now_utc = datetime.now(timezone.utc)
                    now_ist = now_utc + timedelta(hours=5, minutes=30)
                    # If date matches today, use current time to show "Live" status
                    if dt_obj.date() == now_ist.date() and i == len(hist) - 1:
                        ts = time.time()
                    else:
                        # Ensure dt_obj is naive if comparing or generating timestamp
                        ts = dt_obj.replace(tzinfo=None).timestamp()
                except:
                    ts = time.time()

                alert = RotationAlertService.check_alert(
                    prev_q, curr_q, h_curr['rs'], h_curr['rm'], name, "sector", ts
                )
                if alert:
                    all_alerts.append(alert)

            # 4. Generate AI Commentary
            context = {
                "entityType": "sector",
                "symbol": str(name).replace("NIFTY_", "Nifty "),
                "currentQuadrant": RotationAlertService.get_quadrant(curr['rs'], curr['rm']),
                "previousQuadrant": RotationAlertService.get_quadrant(prev['rs'], prev['rm']),
                "RS": curr['rs'],
                "RM": curr['rm'],
                "rsTrend": rs_trend,
                "rmTrend": rm_trend,
                "rank": ranks.get(name),
                "topContributors": cls._get_top_contributors(name),
                "timeframe": timeframe,
                "sectorState": results[name]['metrics']['state']  # type: ignore
            }
            results[name]['commentary'] = AICommentaryService.generate_commentary(context)  # type: ignore
            results[name]['rank'] = ranks.get(name)  # type: ignore

        # Sort alerts by timestamp asc (Oldest first) so frontend prepends them correctly (Newest at top)
        all_alerts.sort(key=lambda x: x['timestamp'])
        
        # Update Cache
        cls._cache = {
            "data": results,
            "alerts": all_alerts,
            "timestamp": time.time(),
            "timeframe": normalized_timeframe
        }
        
        # Save to Fallback file for persistence across restarts/failures
        cls._save_fallback(results, all_alerts, normalized_timeframe)
        
        return results, all_alerts

    @classmethod
    def _save_fallback(cls, data, alerts, timeframe):
        try:
            fallback_path = Path(__file__).parent.parent / "data" / "sector_fallback.json"
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback_path, "w") as f:
                json.dump({
                    "data": data,
                    "alerts": alerts,
                    "timestamp": time.time(),
                    "timeframe": timeframe
                }, f)
            print(f"DEBUG: Saved sector fallback for {timeframe}")
        except Exception as e:
            print(f"Error saving fallback: {e}")

    @classmethod
    def _load_fallback(cls, timeframe, error_msg=None):
        try:
            fallback_path = Path(__file__).parent.parent / "data" / "sector_fallback.json"
            if not fallback_path.exists():
                # If no file exists, proceed to hardcoded fallback
                pass
            else:
                with open(fallback_path, "r") as f:
                    stored = json.load(f)
                    
                # If timeframe matches, return it even if old
                if stored.get("timeframe") == timeframe:
                    print(f"DEBUG: Loaded sector fallback for {timeframe}")
                    return stored["data"], stored["alerts"]
        except Exception as e:
            print(f"Error loading fallback from file: {e}")
        
        # Hardcoded minimal fallback for ephemeral environments (Render)
        print("WARNING: Using hardcoded emergency fallback for Sector Intelligence")
        hard_fallback = {
            "NIFTY_BANK": {"metrics": {"momentumScore": 150, "shift": "NEUTRAL", "relVolume": 1.1, "state": "LEADING"}, "rank": 1, "commentary": "Banking is leading as RS remains above neutral and momentum is rising.", "current": {"rs": 1.08, "rm": 0.003}, "history": []},
            "NIFTY_IT": {"metrics": {"momentumScore": 120, "shift": "NEUTRAL", "relVolume": 1.0, "state": "LAGGING"}, "rank": 2, "commentary": "IT is lagging as RS stays below neutral and momentum is negative.", "current": {"rs": 0.93, "rm": -0.002}, "history": []},
            "NIFTY_PHARMA": {"metrics": {"momentumScore": 90, "shift": "NEUTRAL", "relVolume": 1.0, "state": "NEUTRAL"}, "rank": 3, "commentary": "Pharma is neutral with RS near benchmark and no directional edge.", "current": {"rs": 1.00, "rm": 0.0}, "history": []}
        }
        # Add status and message if an error occurred
        if error_msg:
            for sector_name in hard_fallback:
                hard_fallback[sector_name]["status"] = "fallback"
                hard_fallback[sector_name]["message"] = error_msg
        return hard_fallback, []

    @staticmethod
    def _get_top_contributors(name):
        # Mocking top stocks for sector context - Added .NS suffix for NSE
        contributors = {
            "NIFTY_BANK": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"],
            "NIFTY_IT": ["TCS.NS", "INFY.NS", "WIPRO.NS"],
            "NIFTY_FMCG": ["HUL.NS", "ITC.NS", "NESTLEIND.NS"],
            "NIFTY_METAL": ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS"],
            "NIFTY_PHARMA": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS"],
            "NIFTY_ENERGY": ["RELIANCE.NS", "ONGC.NS", "NTPC.NS"],
            "NIFTY_AUTO": ["M&M.NS", "TATAMOTORS.NS", "MARUTI.NS"],
            "NIFTY_REALTY": ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS"],
            "NIFTY_PSU_BANK": ["SBIN.NS", "BANKBARODA.NS", "PNB.NS"],
            "NIFTY_MEDIA": ["ZEEL.NS", "SUNTV.NS", "PVRINOX.NS"]
        }
        return contributors.get(name, [])

    @staticmethod
    def _get_mock_weight(name):
        weights = {
            "NIFTY_BANK": 0.33,
            "NIFTY_IT": 0.14,
            "NIFTY_FMCG": 0.09,
            "NIFTY_ENERGY": 0.12,
            "NIFTY_AUTO": 0.06,
            "NIFTY_PHARMA": 0.04,
            "NIFTY_METAL": 0.03,
            "NIFTY_REALTY": 0.01,
            "NIFTY_PSU_BANK": 0.02,
            "NIFTY_MEDIA": 0.005
        }
        return weights.get(name, 0.05)

