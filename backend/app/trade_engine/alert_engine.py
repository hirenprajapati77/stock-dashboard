from .models import TradeDecision, TradeState

class AlertEngine:
    """
    Generates smart alerts for triggers and level hits.
    """
    
    @staticmethod
    def generate_alert(decision: TradeDecision) -> str:
        symbol = decision.symbol
        state = decision.state
        
        if state == TradeState.TRIGGERED:
            return f"🔔 {symbol} breakout above {decision.entry} – Trade triggered"
            
        if state == TradeState.TARGET1_HIT:
            return f"✅ {symbol} TARGET 1 HIT! Booking partial profits."
            
        if state == TradeState.SL_HIT:
            return f"❌ {symbol} STOP LOSS HIT. Trade closed for protection."
            
        if decision.setup_state.value == "READY":
             return f"⚠️ {symbol} is READY for {decision.setup.value} near {decision.entry}"
             
        return ""
