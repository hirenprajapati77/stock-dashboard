import numpy as np
import pandas as pd

class ZoneEngine:
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        return true_range.rolling(window=period).mean()

    @staticmethod
    def cluster_swings(swings: list, atr: float, factor: float = 0.5):
        """
        Clusters nearby swing prices into zones based on ATR.
        """
        if not swings:
            return []
            
        # Sort swings by price
        sorted_swings = sorted(swings, key=lambda x: x['price'])
        zones = []
        
        if not sorted_swings:
            return []
            
        current_zone = [sorted_swings[0]]
        
        for i in range(1, len(sorted_swings)):
            price_diff = sorted_swings[i]['price'] - current_zone[-1]['price']
            
            # If price difference is within ATR-based threshold, add to current zone
            if price_diff <= (atr * factor):
                current_zone.append(sorted_swings[i])
            else:
                # Calculate zone properties
                zone_prices = [s['price'] for s in current_zone]
                zones.append({
                    'price': float(np.mean(zone_prices)),
                    'price_low': float(min(zone_prices)),
                    'price_high': float(max(zone_prices)),
                    'touches': len(current_zone),
                    'last_touched': str(max([s['time'] for s in current_zone])),
                    'avg_volume': float(np.mean([s['volume'] for s in current_zone if 'volume' in s]))
                })
                current_zone = [sorted_swings[i]]
                
        # Handle last zone
        zone_prices = [s['price'] for s in current_zone]
        zones.append({
            'price': float(np.mean(zone_prices)),
            'price_low': float(min(zone_prices)),
            'price_high': float(max(zone_prices)),
            'touches': len(current_zone),
            'last_touched': str(max([s['time'] for s in current_zone])),
            'avg_volume': float(np.mean([s['volume'] for s in current_zone if 'volume' in s]))
        })
        
        return zones
