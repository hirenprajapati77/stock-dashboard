import pandas as pd
import numpy as np

class FeatureEngineer:
    @staticmethod
    def calculate_features(df: pd.DataFrame):
        """
        Extracts features for AI models from OHLCV data.
        """
        if len(df) < 50:
            return {}

        # 1. Volume Ratio (Current Vol / 20-period Avg)
        avg_vol = df['volume'].iloc[-21:-1].mean()
        curr_vol = df['volume'].iloc[-1]
        vol_ratio = round(curr_vol / avg_vol, 2) if avg_vol > 0 else 1.0

        # 2. ATR Expansion (Current Range / 14-period ATR)
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        atr = df['tr'].rolling(window=14).mean().iloc[-1]
        curr_range = df['high'].iloc[-1] - df['low'].iloc[-1]
        atr_expansion = round(curr_range / atr, 2) if atr > 0 else 1.0
        
        # 3. EMA Slope (Price relative to EMA-50)
        ema_50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        close = df['close'].iloc[-1]
        dist_from_ema = round((close - ema_50) / ema_50 * 100, 2)

        # 4. RSI (Relative Strength Index) - 14 period
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        curr_rsi = round(rsi.iloc[-1], 2) if not np.isnan(rsi.iloc[-1]) else 50.0

        # 5. ADX (Average Directional Index) - 14 period
        # Simplified ADX implementation
        plus_dm = (df['high'] - df['high'].shift(1)).where(lambda x: (x > 0) & (x > (df['low'].shift(1) - df['low'])), 0)
        minus_dm = (df['low'].shift(1) - df['low']).where(lambda x: (x > 0) & (x > (df['high'] - df['high'].shift(1))), 0)
        
        tr_smooth = df['tr'].rolling(window=14).mean()
        plus_di = 100 * (plus_dm.rolling(window=14).mean() / tr_smooth)
        minus_di = 100 * (minus_dm.rolling(window=14).mean() / tr_smooth)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=14).mean()
        curr_adx = round(adx.iloc[-1], 2) if not np.isnan(adx.iloc[-1]) else 20.0

        return {
            "vol_ratio": vol_ratio,
            "atr_expansion": atr_expansion,
            "dist_from_ema": dist_from_ema,
            "rsi": curr_rsi,
            "adx": curr_adx,
            "close": close
        }
