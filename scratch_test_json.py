import json
from enum import Enum
import sys
sys.path.insert(0, "backend")

from app.services.screener_service import ScreenerService
from app.trade_engine.models import ActionType, SetupType, RiskLevel
from app.trade_engine.trade_decision_service import V5TradeEngine
from app.trade_engine.models import MarketContext

def test_dump():
    context = MarketContext(
        symbol="TCS",
        price=100.0,
        open=100.0,
        high=105.0,
        low=95.0,
        close=100.0,
        prev_close=99.0,
        supports=[],
        resistances=[],
        atr=2.0,
        adx=25.0,
        volume_ratio=1.5,
        daily_volume_ratio=1.2,
        trend="UP",
        higher_tf_trend="UP"
    )
    decision = V5TradeEngine.generate_trade(context, "15m")
    
    data = [{
        "symbol": "TCS",
        "decision": decision.dict()
    }]
    
    class _EnumEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Enum):
                return obj.value
            return super().default(obj)
            
    try:
        s = json.dumps(data, cls=_EnumEncoder)
        print("Success!")
    except Exception as e:
        print(f"Failed: {e}")

test_dump()
