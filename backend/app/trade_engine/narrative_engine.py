from .models import MarketContext, SetupType, MarketCondition, MarketRegime, MarketRegimeType

class NarrativeEngine:
    """
    Generates human-readable trade narratives like a professional trader.
    """
    
    @staticmethod
    def generate(
        context: MarketContext,
        m_condition: MarketCondition,
        m_regime: MarketRegime,
        setup: SetupType,
        confluence_score: float
    ) -> str:
        parts = []
        
        # 1. Market Context
        parts.append(f"Market is {m_condition.market_bias.lower()} with {m_condition.strength.lower()} momentum ({m_regime.regime.value}).")
        
        # 2. Price Action
        nearest_res = min([r for r in context.resistances if r > context.price], default=None)
        nearest_sup = max([s for s in context.supports if s < context.price], default=None)
        
        if setup in [SetupType.BREAKOUT, SetupType.RETEST] and nearest_res:
            parts.append(f"{context.symbol} is approaching resistance at {nearest_res:.2f} with {context.volume_ratio:.1f}x volume expansion.")
            parts.append("Breakout setup forming → momentum trade likely.")
            
        elif setup == SetupType.BREAKDOWN and nearest_sup:
            parts.append(f"{context.symbol} is testing support at {nearest_sup:.2f} with selling pressure.")
            parts.append("Breakdown risk increasing → bearish continuation expected.")
            
        else:
            parts.append(f"{context.symbol} is in a consolidation phase near current levels.")
        
        # 3. Confluence Signal
        if confluence_score > 75:
            parts.append(f"Strong multi-factor alignment (Confluence: {int(confluence_score)}/100) supports a high-conviction trade.")
        elif confluence_score > 50:
            parts.append(f"Moderate confluence ({int(confluence_score)}/100). Proceed with standard sizing.")
        else:
            parts.append(f"Low confluence ({int(confluence_score)}/100). Wait for stronger confirmation.")
            
        return " ".join(parts)
