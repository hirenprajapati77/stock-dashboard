from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class ObservabilityService:
    LOG_FILE = Path(__file__).parent.parent / "data" / "system_observability.json"
    MAX_EVENTS = 500

    @classmethod
    def _load(cls) -> list[dict[str, Any]]:
        try:
            if cls.LOG_FILE.exists():
                return json.loads(cls.LOG_FILE.read_text(encoding="utf-8")) or []
        except Exception:
            pass
        return []

    @classmethod
    def _save(cls, rows: list[dict[str, Any]]) -> None:
        cls.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.LOG_FILE.write_text(json.dumps(rows[: cls.MAX_EVENTS], indent=2), encoding="utf-8")

    @classmethod
    def record_api_failure(cls, endpoint: str, message: str, details: dict[str, Any] | None = None) -> None:
        rows = cls._load()
        rows.insert(0, {
            "kind": "API_FAILURE",
            "endpoint": endpoint,
            "message": str(message),
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
        })
        cls._save(rows)

    @classmethod
    def record_fail_safe(cls, endpoint: str, explanation: str, details: dict[str, Any] | None = None) -> None:
        rows = cls._load()
        rows.insert(0, {
            "kind": "FAIL_SAFE",
            "endpoint": endpoint,
            "message": "Fail-safe triggered",
            "details": {"explanation": explanation, **(details or {})},
            "timestamp": datetime.utcnow().isoformat(),
        })
        cls._save(rows)

    @classmethod
    def summarize_last_24h(cls) -> dict[str, Any]:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        rows = []
        for row in cls._load():
            try:
                ts = datetime.fromisoformat(str(row.get("timestamp")))
            except Exception:
                continue
            if ts >= cutoff:
                rows.append(row)

        by_kind: dict[str, int] = {}
        by_endpoint: dict[str, int] = {}
        for row in rows:
            by_kind[row.get("kind", "UNKNOWN")] = by_kind.get(row.get("kind", "UNKNOWN"), 0) + 1
            by_endpoint[row.get("endpoint", "UNKNOWN")] = by_endpoint.get(row.get("endpoint", "UNKNOWN"), 0) + 1

        alerts = []
        if by_kind.get("API_FAILURE", 0) >= 3:
            alerts.append("Repeated API failures detected in the last 24h.")
        if by_kind.get("FAIL_SAFE", 0) >= 3:
            alerts.append("Execution fail-safes were triggered multiple times in the last 24h.")

        return {
            "events24h": len(rows),
            "byKind": by_kind,
            "byEndpoint": by_endpoint,
            "alerts": alerts,
            "recent": rows[:10],
        }
