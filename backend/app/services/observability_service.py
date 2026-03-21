from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class ObservabilityService:
    LOG_FILE = Path(__file__).parent.parent / "data" / "system_observability.json"
    MAX_EVENTS = 1000

    @classmethod
    def record_api_failure(cls, endpoint: str, message: str, details: dict[str, Any] | None = None) -> None:
        cls._record("API_FAILURE", endpoint=endpoint, message=message, details=details or {})

    @classmethod
    def record_missing_data(cls, context: str, details: dict[str, Any] | None = None) -> None:
        cls._record("MISSING_DATA", endpoint=context, message="Missing data encountered", details=details or {})

    @classmethod
    def record_fail_safe(cls, component: str, details: dict[str, Any] | None = None) -> None:
        cls._record("FAIL_SAFE", endpoint=component, message="Fail-safe triggered", details=details or {})

    @classmethod
    def record_data_inconsistency(cls, context: str, details: dict[str, Any] | None = None) -> None:
        cls._record("DATA_INCONSISTENCY", endpoint=context, message="Data inconsistency detected", details=details or {})

    @classmethod
    def get_summary(cls) -> dict[str, Any]:
        rows = cls._load()
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = [row for row in rows if cls._parse_ts(row.get("timestamp")) >= recent_cutoff]
        baseline = recent if recent else rows

        def count(kind: str, items: list[dict[str, Any]]) -> int:
            return sum(1 for row in items if row.get("kind") == kind)

        alerts: list[dict[str, Any]] = []
        api_failures = count("API_FAILURE", baseline)
        missing_data = count("MISSING_DATA", baseline)
        fail_safes = count("FAIL_SAFE", baseline)
        inconsistencies = count("DATA_INCONSISTENCY", baseline)

        if api_failures >= 3:
            alerts.append({"severity": "critical", "type": "API_FAILURE_SPIKE", "message": f"{api_failures} API failures recorded in the last 24h."})
        if missing_data >= 5:
            alerts.append({"severity": "warning", "type": "MISSING_DATA_CLUSTER", "message": f"{missing_data} missing-data events recorded in the last 24h."})
        if fail_safes >= 3:
            alerts.append({"severity": "warning", "type": "FAIL_SAFE_CLUSTER", "message": f"{fail_safes} fail-safe triggers recorded in the last 24h."})
        if inconsistencies >= 1:
            alerts.append({"severity": "warning", "type": "DATA_INCONSISTENCY", "message": f"{inconsistencies} data inconsistency events detected in the last 24h."})

        return {
            "apiFailures": api_failures,
            "missingDataCases": missing_data,
            "failSafeTriggers": fail_safes,
            "dataInconsistencies": inconsistencies,
            "recentEvents": baseline[:10],
            "alerts": alerts,
        }

    @classmethod
    def _record(cls, kind: str, *, endpoint: str, message: str, details: dict[str, Any]) -> None:
        rows = cls._load()
        rows.insert(0, {
            "kind": kind,
            "endpoint": endpoint,
            "message": message,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        cls._save(rows)

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

    @staticmethod
    def _parse_ts(value: Any) -> datetime:
        try:
            text = str(value)
            if text.endswith("Z"):
                text = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return datetime.fromtimestamp(0, tz=timezone.utc)
