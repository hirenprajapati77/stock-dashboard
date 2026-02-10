import yfinance as yf
import pandas as pd
import numpy as np
import time
import sys
from datetime import datetime, timedelta
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
    
    # Class-level cache
    _cache = {
        "data": None,
        "alerts": None,
        "timestamp": 0,
        "timeframe": None
    }
    CACHE_TTL = 300 # 5 minutes

    @classmethod
    def get_rotation_data(cls, days=60, timeframe="1D"):
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
            "1D": {"interval": "1d", "period": "1y"}, # Reverted to 1y for better stability
            "1W": {"interval": "1wk", "period": "2y"},
            "1M": {"interval": "1mo", "period": "5y"}
        }
        
        # 0. Check Cache
        current_time = time.time()
        if (cls._cache["data"] is not None and 
            cls._cache["timeframe"] == timeframe and 
            (current_time - cls._cache["timestamp"]) < cls.CACHE_TTL):
            return cls._cache["data"], cls._cache["alerts"]

        config = tf_map.get(timeframe, {"interval": "1d", "period": "1y"})
        interval = config["interval"]
        period = config["period"]
        
        # 1. Collect ALL symbols needed (Benchmark + Sectors + ALL constituents)
        all_sector_symbols = [cls.BENCHMARK] + list(cls.SECTORS.values())
        all_cons_symbols = []
        for s_name in cls.SECTORS:
            all_cons_symbols.extend(ConstituentService.get_constituents(s_name))
        
        unique_symbols = list(set(all_sector_symbols + all_cons_symbols))
        
        try:
            print(f"DEBUG: Batch downloading {len(unique_symbols)} symbols: {', '.join(unique_symbols[:5])}...")
            # Let yfinance manage its own session (avoids curl_cffi vs requests.Session errors)
            batch_df = yf.download(
                " ".join(unique_symbols),
                period=period,
                interval=interval,
                progress=False,
                group_by='ticker'
            )
            
            print(f"DEBUG: Download finished. Shape: {batch_df.shape if not batch_df.empty else 'EMPTY'}")
            if batch_df.empty:
                print(f"Warning: Batch download empty. Trying fallback.")
                data, alerts = cls._load_fallback(timeframe)
                if data: return data, alerts
                return {}, []
        except Exception as e:
            print(f"CRITICAL: Batch download failed: {e}. Trying fallback.")
            data, alerts = cls._load_fallback(timeframe)
            if data: return data, alerts
            return {}, []

        results = {}
        
        # Helper to get ticker data from multi-index batch_df
        def get_ticker_df(ticker_sym):
            try:
                if len(unique_symbols) == 1: return batch_df
                return batch_df[ticker_sym].dropna()
            except:
                return pd.DataFrame()

        benchmark_df = get_ticker_df(cls.BENCHMARK)
        if benchmark_df.empty:
            print(f"CRITICAL: Benchmark {cls.BENCHMARK} missing. Trying fallback.")
            data, alerts = cls._load_fallback(timeframe)
            if data: return data, alerts
            return {}, []
            
        benchmark_data = benchmark_df['Close']

        # 2. Process each sector
        for name, symbol in cls.SECTORS.items():
            try:
                s_df = get_ticker_df(symbol)
                if s_df.empty: continue
                
                sector_close = s_df['Close']
                
                # Align data
                combined = pd.DataFrame({
                    'sector': sector_close,
                    'benchmark': benchmark_data
                }).dropna()
                
                if combined.empty:
                    # Timezone naive fallback
                    s_tmp, b_tmp = sector_close.copy(), benchmark_data.copy()
                    if hasattr(s_tmp.index, 'tz'): s_tmp.index = s_tmp.index.tz_localize(None)
                    if hasattr(b_tmp.index, 'tz'): b_tmp.index = b_tmp.index.tz_localize(None)
                    combined = pd.DataFrame({'sector': s_tmp, 'benchmark': b_tmp}).dropna()

                if combined.empty: continue
                
                # RS and RM
                combined['rs'] = combined['sector'] / combined['benchmark']
                combined['ema_fast'] = combined['rs'].ewm(span=14, adjust=False).mean()
                combined['ema_slow'] = combined['ema_fast'].ewm(span=21, adjust=False).mean()
                combined['rm'] = combined['ema_fast'] - combined['ema_slow']
                
                # History (last 30)
                history = combined.tail(30)
                history_list = []
                for hist_idx, hist_row in history.iterrows():
                    history_list.append({
                        "date": hist_idx.strftime("%Y-%m-%d"),
                        "rs": float(round(hist_row['ema_fast'], 4)),
                        "rm": float(round(hist_row['rm'], 6))
                    })
                
                # 3. Calculate Shining Metrics from pre-downloaded constituents
                constituents = ConstituentService.get_constituents(name)
                advances, total_vol, avg_vol, valid_cons = 0, 0, 0, 0
                
                if constituents:
                    for const in constituents:
                        c_df = get_ticker_df(const)
                        if c_df.empty or len(c_df) < 2: continue
                        
                        last_c = c_df['Close'].iloc[-1]
                        last_o = c_df['Open'].iloc[-1]
                        last_v = c_df['Volume'].iloc[-1]
                        
                        if last_c > last_o: advances += 1
                        valid_cons += 1
                        total_vol += last_v
                        avg_vol += c_df['Volume'].mean()
                    
                    breadth_ratio = advances / valid_cons if valid_cons > 0 else 0.5
                    rel_volume = total_vol / avg_vol if avg_vol > 0 else 1.0
                else:
                    breadth_ratio, rel_volume = 0.5, 1.0
                
                # Final Current Metrics
                last_row = history.iloc[-1]
                curr_rs = float(last_row['ema_fast'])
                curr_rm = float(last_row['rm'])

                # SHINING definition for intraday / tactical view:
                # - Strong relative strength vs NIFTY
                # - Positive momentum on selected timeframe
                # - Healthy breadth (advancers / total >= 60%)
                # - Elevated volume vs recent average
                rs_threshold = 1.2
                vol_threshold = 1.3
                is_shining = (
                    curr_rs >= rs_threshold
                    and curr_rm > 0
                    and breadth_ratio >= 0.60
                    and rel_volume >= vol_threshold
                )

                state = "SHINING" if is_shining else "WEAK" if (curr_rs < 0.98 and curr_rm < 0) else "NEUTRAL"

                results[name] = {
                    "current": history_list[-1],
                    "history": history_list,
                    "weight": cls._get_mock_weight(name),
                    "rank": 0, # Placeholder
                    "metrics": {
                        "breadth": round(breadth_ratio * 100, 1),
                        "relVolume": round(rel_volume, 2),
                        "state": state
                    }
                }
                
                RotationAlertService.detect_alerts(name, curr_rs, curr_rm, is_shining)

            except Exception as e:
                print(f"Error processing sector {name}: {e}")

        # 4. Calculate Ranks, Trends, and History
        if not results:
            print("WARNING: No sector results calculated!")
            return {}, []

        sorted_sectors = sorted(results.items(), key=lambda x: x[1]['current']['rs'], reverse=True)
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

            results[name]['metrics']['momentumScore'] = round(mom_score, 2)
            results[name]['metrics']['shift'] = shift
            # Generate Historical Alerts
            for i in range(1, len(hist)):
                h_prev = hist[i-1]
                h_curr = hist[i]
                
                prev_q = RotationAlertService.get_quadrant(h_prev['rs'], h_prev['rm'])
                curr_q = RotationAlertService.get_quadrant(h_curr['rs'], h_curr['rm'])
                
                # Convert date to timestamp
                try:
                    dt_obj = datetime.strptime(h_curr['date'], "%Y-%m-%d")
                    # If date matches today, use current time to show "Live" status
                    if dt_obj.date() == datetime.now().date() and i == len(hist) - 1:
                        ts = time.time()
                    else:
                        ts = dt_obj.timestamp()
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
                "symbol": name.replace("NIFTY_", "Nifty "),
                "currentQuadrant": RotationAlertService.get_quadrant(curr['rs'], curr['rm']),
                "previousQuadrant": RotationAlertService.get_quadrant(prev['rs'], prev['rm']),
                "RS": curr['rs'],
                "RM": curr['rm'],
                "rsTrend": rs_trend,
                "rmTrend": rm_trend,
                "rank": ranks.get(name),
                "topContributors": cls._get_top_contributors(name),
                "timeframe": timeframe,
                "shiningState": results[name]['metrics']['state']
            }
            results[name]['commentary'] = AICommentaryService.generate_commentary(context)
            results[name]['rank'] = ranks.get(name)

        # Sort alerts by timestamp asc (Oldest first) so frontend prepends them correctly (Newest at top)
        all_alerts.sort(key=lambda x: x['timestamp'])
        
        # Update Cache
        cls._cache = {
            "data": results,
            "alerts": all_alerts,
            "timestamp": time.time(),
            "timeframe": timeframe
        }
        
        # Save to Fallback file for persistence across restarts/failures
        cls._save_fallback(results, all_alerts, timeframe)
        
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
    def _load_fallback(cls, timeframe, error_msg=None): # Modified signature to accept error_msg
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
            "NIFTY_BANK": {"metrics": {"momentumScore": 150, "breadth": 40, "shift": "NEUTRAL", "relVolume": 1.1, "state": "NEUTRAL"}, "rank": 1, "commentary": "Nifty BANK historical fallback data.", "current": {"rs": 1.05, "rm": 0.001}, "history": []},
            "NIFTY_IT": {"metrics": {"momentumScore": 120, "breadth": 60, "shift": "GAINING", "relVolume": 0.9, "state": "NEUTRAL"}, "rank": 2, "commentary": "Nifty IT historical fallback data.", "current": {"rs": 1.02, "rm": 0.0005}, "history": []},
            "NIFTY_PHARMA": {"metrics": {"momentumScore": 90, "breadth": 80, "shift": "LOSING", "relVolume": 1.2, "state": "NEUTRAL"}, "rank": 3, "commentary": "Nifty PHARMA historical fallback data.", "current": {"rs": 0.98, "rm": -0.0002}, "history": []}
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
