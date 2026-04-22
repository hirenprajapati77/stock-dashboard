from .models import TradeIntent, MarketContext

class IntentEngine:
    """
    Determines the intended horizon for the trade (Scalp, Intraday, Swing).
    """
    
    @staticmethod
    def determine(tf: str, vol: str) -> TradeIntent:
        # 1. Based on timeframe
        if tf in ["1m", "5m"]:
            return TradeIntent.SCALP
        elif tf in ["1D", "1W", "1M"]:
            return TradeIntent.SWING
        else:
            # 15m, 1H, etc usually intraday unless volatility is extreme
            if vol == "HIGH": return TradeIntent.SCALP # Faster moves
            return TradeIntent.INTRADAY
