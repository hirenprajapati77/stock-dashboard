from .models import TradeQuality

class NoiseFilter:
    """
    Prevents overtrading and filters low-confidence noise.
    """
    
    # Session state tracking
    _signals_today = 0
    
    @staticmethod
    def should_suppress(quality: TradeQuality, score: float) -> bool:
        """
        Suppresses low-quality trades if signal count is high.
        """
        if NoiseFilter._signals_today > 10:
            # High frequency session: Only allow HIGH quality
            return quality != TradeQuality.HIGH
            
        if score < 40:
            return True # Baseline noise floor
            
        return False
        
    @staticmethod
    def record_signal():
        NoiseFilter._signals_today += 1

    @staticmethod
    def reset():
        NoiseFilter._signals_today = 0
