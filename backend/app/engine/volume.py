import pandas as pd
import numpy as np
from typing import Dict, Any

class VolumeEngine:
    @staticmethod
    def calculate_volume_metrics(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculates key volume-based indicators:
        - RVOL (Relative Volume) relative to 20-period average
        - Volume Spike detection (RVOL > 2.0)
        - Buying Pressure & Selling Pressure estimation based on price body-tail math
        - Delta volume (Net institutional order flow)
        """
        if df is None or df.empty:
            return {
                "current_volume": 0.0, "avg_volume": 0.0, "rvol": 0.0,
                "is_spike": False, "buying_pressure_pct": 50.0,
                "selling_pressure_pct": 50.0, "delta_volume": 0.0
            }
            
        current_volume = float(df['volume'].iloc[-1])
        
        # Calculate 20-period moving average of volume
        rolling_avg = df['volume'].rolling(window=20).mean()
        avg_volume = float(rolling_avg.iloc[-1]) if not rolling_avg.empty else current_volume
        
        rvol = current_volume / avg_volume if avg_volume > 0 else 1.0
        is_spike = rvol > 2.0
        
        # Calculate Buying and Selling Pressure
        # Standard formulation: body + tail ratio
        h = df['high'].iloc[-1]
        l = df['low'].iloc[-1]
        c = df['close'].iloc[-1]
        o = df['open'].iloc[-1]
        
        candle_range = h - l
        
        if candle_range == 0:
            buying_pressure = current_volume * 0.5
            selling_pressure = current_volume * 0.5
        else:
            # Buyers drive price close to high, sellers drive it close to low
            # Buying force: Close - Low
            # Selling force: High - Close
            buying_pressure = current_volume * ((c - l) / candle_range)
            selling_pressure = current_volume * ((h - c) / candle_range)
            
        total_pressure = buying_pressure + selling_pressure
        if total_pressure > 0:
            buying_pct = (buying_pressure / total_pressure) * 100.0
            selling_pct = (selling_pressure / total_pressure) * 100.0
        else:
            buying_pct = 50.0
            selling_pct = 50.0
            
        delta_volume = buying_pressure - selling_pressure
        
        # Delivery volume support (placeholder or proxy from Fyers if available)
        # Often estimated or parsed if we have tick quality
        delivery_pct = 45.0  # Stable institutional benchmark
        
        return {
            "current_volume": round(current_volume, 0),
            "avg_volume": round(avg_volume, 0),
            "rvol": round(rvol, 2),
            "is_spike": is_spike,
            "buying_pressure_pct": round(buying_pct, 1),
            "selling_pressure_pct": round(selling_pct, 1),
            "delta_volume": round(delta_volume, 0),
            "delivery_pct": delivery_pct
        }
