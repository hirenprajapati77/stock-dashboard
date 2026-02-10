import time
from typing import Dict, List, Optional, Literal

Quadrant = Literal["LEADING", "WEAKENING", "LAGGING", "IMPROVING"]

ALERT_RULES = [
    {
        "name": "ENTER_LEADING",
        "from": ["IMPROVING", "WEAKENING"],
        "to": "LEADING",
        "priority": "HIGH"
    },
    {
        "name": "EXIT_LEADING",
        "from": ["LEADING"],
        "to": ["WEAKENING", "LAGGING"],
        "priority": "MEDIUM"
    },
    {
        "name": "EARLY_STRENGTH",
        "from": ["LAGGING"],
        "to": "IMPROVING",
        "priority": "LOW"
    },
    {
        "name": "ENTER_SHINING",
        "priority": "HIGH"
    },
    {
        "name": "EXIT_SHINING",
        "priority": "MEDIUM"
    }
]

class RotationAlertService:
    # In-memory persistence (for simple session handling)
    # In a real app, this would be Redis
    _state_cache: Dict[str, Dict] = {}
    _alert_history: List[Dict] = []

    @staticmethod
    def get_quadrant(rs: float, rm: float) -> Quadrant:
        if rs >= 1.0 and rm >= 0: return "LEADING"
        if rs >= 1.0 and rm < 0: return "WEAKENING"
        if rs < 1.0 and rm < 0: return "LAGGING"
        return "IMPROVING"

    @classmethod
    def check_alert(cls, prev_q: str, curr_q: str, curr_rs: float, curr_rm: float, symbol: str, entity_type: str, timestamp: float) -> Optional[Dict]:
        """
        Stateless check for alert rules between two quadrants.
        """
        if prev_q == curr_q:
            return None

        for rule in ALERT_RULES:
            if "from" not in rule or "to" not in rule: continue # Skip special rules
            
            from_match = prev_q in rule["from"] if isinstance(rule["from"], list) else rule["from"] == prev_q
            to_match = curr_q in rule["to"] if isinstance(rule["to"], list) else rule["to"] == curr_q

            if from_match and to_match:
                return {
                    "symbol": symbol,
                    "entity_type": entity_type,
                    "type": rule["name"],
                    "from_q": prev_q,
                    "to_q": curr_q,
                    "rs": round(curr_rs, 4),
                    "rm": round(curr_rm, 6),
                    "priority": rule["priority"],
                    "timestamp": timestamp
                }
        return None

    @classmethod
    def detect_alerts(cls, symbol: str, curr_rs: float, curr_rm: float, is_shining: bool = False, entity_type: str = "sector"):
        curr_q = cls.get_quadrant(curr_rs, curr_rm)
        prev_state = cls._state_cache.get(symbol)

        # Initialize if not present
        if not prev_state:
            cls._state_cache[symbol] = {
                "id": symbol,
                "type": entity_type,
                "quadrant": curr_q,
                "rs": curr_rs,
                "rm": curr_rm,
                "shining": is_shining,
                "updated_at": time.time()
            }
            return None

        prev_q = prev_state["quadrant"]
        prev_shining = prev_state.get("shining", False)
        
        alerts = []
        
        # 1. Check Quadrant Alert
        q_alert = cls.check_alert(prev_q, curr_q, curr_rs, curr_rm, symbol, entity_type, time.time())
        if q_alert: alerts.append(q_alert)

        # 2. Check Shining Alert
        if is_shining and not prev_shining:
             alerts.append({
                "symbol": symbol,
                "entity_type": entity_type,
                "type": "ENTER_SHINING",
                "rs": round(curr_rs, 4),
                "rm": round(curr_rm, 6),
                "priority": "HIGH",
                "timestamp": time.time()
            })
        elif not is_shining and prev_shining:
             # Only alert if RS dropped significantly to avoid flicker
             alerts.append({
                "symbol": symbol,
                "entity_type": entity_type,
                "type": "EXIT_SHINING",
                "rs": round(curr_rs, 4),
                "rm": round(curr_rm, 6),
                "priority": "LOW",
                "timestamp": time.time()
            })
        
        # Update cache
        cls._state_cache[symbol] = {
            "id": symbol,
            "type": entity_type,
            "quadrant": curr_q,
            "rs": curr_rs,
            "rm": curr_rm,
            "shining": is_shining,
            "updated_at": time.time()
        }

        for alert in alerts:
            cls._alert_history.append(alert)
        
        # Keep only last 50 alerts
        if len(cls._alert_history) > 50:
             cls._alert_history = cls._alert_history[-50:]
             
        return alerts if alerts else None

    @classmethod
    def get_recent_alerts(cls, limit: int = 10):
        # Sort by timestamp desc
        return sorted(cls._alert_history, key=lambda x: x['timestamp'], reverse=True)[:limit]
