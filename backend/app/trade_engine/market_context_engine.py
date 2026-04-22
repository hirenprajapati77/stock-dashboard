from .models import MarketContext, MarketCondition

class MarketContextEngine:
    """
    Analyzes overall market conditions (Trend, Volatility, Strength).
    """
    
    @staticmethod
    def analyze(context: MarketContext) -> MarketCondition:
        # 1. Trend Logic (EMA 50 fallback via Trend string)
        trend = "SIDEWAYS"
        bias = "NEUTRAL"
        conf_adj = 0.0
        
        if context.trend == "BULLISH":
            trend = "UP"
            bias = "BULLISH"
            conf_adj += 10
        elif context.trend == "BEARISH":
            trend = "DOWN"
            bias = "BEARISH"
            conf_adj -= 10
            
        # 2. Volatility Logic
        vol = "NORMAL"
        if context.atr > (context.price * 0.03):
            vol = "HIGH"
            conf_adj -= 5
        elif context.atr < (context.price * 0.01):
            vol = "LOW"
            
        # 3. Strength Logic
        strength = "WEAK"
        if context.adx > 25:
            strength = "STRONG"
            conf_adj += 5
            
        return MarketCondition(
            market_trend=trend,
            market_bias=bias,
            volatility=vol,
            strength=strength,
            confidence_adjustment=conf_adj
        )
