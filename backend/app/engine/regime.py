class MarketRegimeEngine:

    @staticmethod
    def detect_regime(df):
        """
        Classifies current market into one of 5 regimes:
        STRONG_UPTREND | STRONG_DOWNTREND | TRENDING | WEAK_TREND | RANGE

        Uses ADX for trend strength and EMA20/50 crossover for direction.
        """
        from app.engine.insights import InsightEngine

        adx = InsightEngine.get_adx(df)
        ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        cmp = float(df['close'].iloc[-1])

        if adx >= 25:
            if cmp > ema20 > ema50:
                return "STRONG_UPTREND"
            elif cmp < ema20 < ema50:
                return "STRONG_DOWNTREND"
            else:
                return "TRENDING"
        elif adx >= 18:
            return "WEAK_TREND"
        else:
            return "RANGE"

    @staticmethod
    def get_grade(confidence: int) -> str:
        """
        Maps confidence score to an institutional-style trade grade.
        """
        if confidence >= 85:
            return "A+"
        elif confidence >= 75:
            return "A"
        elif confidence >= 65:
            return "B"
        elif confidence >= 55:
            return "C"
        else:
            return "D"
