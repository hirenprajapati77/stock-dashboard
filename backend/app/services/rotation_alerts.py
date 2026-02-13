import time
from typing import Dict, List, Optional, Literal

SectorState = Literal["LEADING", "WEAKENING", "LAGGING", "IMPROVING", "NEUTRAL"]


class RotationAlertService:
    """Alert engine for sector state transitions.

    Alerts are emitted only when the state changes and only for the
    non-negotiable event set required by business rules.
    """

    ENTER_LEADING = "ENTER_LEADING"
    EXIT_LEADING = "EXIT_LEADING"
    ENTER_LAGGING = "ENTER_LAGGING"
    EXIT_LAGGING = "EXIT_LAGGING"

    # In-memory persistence (for simple session handling)
    _state_cache: Dict[str, Dict] = {}
    _alert_history: List[Dict] = []

    @staticmethod
    def get_quadrant(rs: float, rm: float, sr: float = 0.0) -> SectorState:
        # Trader-safe state mapping: relative strength must agree with
        # absolute sector direction to avoid false "LEADING" on red sectors.
        if sr > 0 and rs > 1 and rm > 0:
            return "LEADING"
        if sr > 0 and rs > 1 and rm < 0:
            return "WEAKENING"
        if sr < 0 and rs > 1 and rm > 0:
            return "IMPROVING"
        if sr < 0 and rs < 1 and rm < 0:
            return "LAGGING"
        return "NEUTRAL"


    @classmethod
    def check_alert(cls, prev_q: str, curr_q: str, curr_rs: float, curr_rm: float, symbol: str, entity_type: str, timestamp: float) -> Optional[Dict]:
        if prev_q == curr_q:
            return None

        if curr_q == "LEADING":
            alert_type, priority = cls.ENTER_LEADING, "HIGH"
        elif prev_q == "LEADING":
            alert_type, priority = cls.EXIT_LEADING, "MEDIUM"
        elif curr_q == "LAGGING":
            alert_type, priority = cls.ENTER_LAGGING, "HIGH"
        elif prev_q == "LAGGING":
            alert_type, priority = cls.EXIT_LAGGING, "MEDIUM"
        else:
            return None

        return {
            "symbol": symbol,
            "entity_type": entity_type,
            "type": alert_type,
            "from_q": prev_q,
            "to_q": curr_q,
            "rs": round(curr_rs, 4),
            "rm": round(curr_rm, 6),
            "priority": priority,
            "timestamp": timestamp,
        }

    @classmethod
    def detect_alerts(cls, symbol: str, curr_rs: float, curr_rm: float, curr_sr: float = 0.0, entity_type: str = "sector"):
        curr_state = cls.get_quadrant(curr_rs, curr_rm, curr_sr)
        now = time.time()
        prev_state_obj = cls._state_cache.get(symbol)

        # Initialize cache; no alert on first seen state.
        if not prev_state_obj:
            cls._state_cache[symbol] = {
                "id": symbol,
                "type": entity_type,
                "quadrant": curr_state,
                "rs": curr_rs,
                "rm": curr_rm,
                "updated_at": now,
            }
            return None

        prev_state = prev_state_obj["quadrant"]
        alert = None

        if prev_state != curr_state:
            if curr_state == "LEADING":
                alert_type, priority = cls.ENTER_LEADING, "HIGH"
            elif prev_state == "LEADING":
                alert_type, priority = cls.EXIT_LEADING, "MEDIUM"
            elif curr_state == "LAGGING":
                alert_type, priority = cls.ENTER_LAGGING, "HIGH"
            elif prev_state == "LAGGING":
                alert_type, priority = cls.EXIT_LAGGING, "MEDIUM"
            else:
                alert_type = None

            if alert_type:
                alert = {
                    "symbol": symbol,
                    "entity_type": entity_type,
                    "type": alert_type,
                    "from_q": prev_state,
                    "to_q": curr_state,
                    "rs": round(curr_rs, 4),
                    "rm": round(curr_rm, 6),
                    "priority": priority,
                    "timestamp": now,
                }
                cls._alert_history.append(alert)

        cls._state_cache[symbol] = {
            "id": symbol,
            "type": entity_type,
            "quadrant": curr_state,
            "rs": curr_rs,
            "rm": curr_rm,
            "updated_at": now,
        }

        if len(cls._alert_history) > 50:
            cls._alert_history = cls._alert_history[-50:]

        return [alert] if alert else None

    @classmethod
    def get_recent_alerts(cls, limit: int = 10):
        return sorted(cls._alert_history, key=lambda x: x["timestamp"], reverse=True)[:limit]
