"""Sanitized, bounded trading audit evidence.

Audit events preserve structured provenance and outcomes, never credentials,
authorization headers, prompts, or private model reasoning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal


Outcome = Literal["ALLOW", "DENY", "ERROR", "UNKNOWN", "HUMAN_REQUIRED"]
_SENSITIVE_MARKERS = (
    "token",
    "secret",
    "password",
    "authorization",
    "bearer",
    "credential",
    "api_key",
    "apikey",
)
_PRIVATE_REASONING_KEYS = {
    "chain_of_thought",
    "private_reasoning",
    "reasoning",
    "raw_prompt",
    "hidden_reasoning",
}
MAX_EVENT_BYTES = 64 * 1024


def sanitize_telemetry(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 12:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            normalized = name.strip().lower()
            if normalized in _PRIVATE_REASONING_KEYS:
                continue
            if any(marker in normalized for marker in _SENSITIVE_MARKERS):
                result[name] = "[REDACTED]"
            else:
                result[name] = sanitize_telemetry(item, _depth=_depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_telemetry(item, _depth=_depth + 1) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass(frozen=True)
class TradingAuditEvent:
    schema_version: str
    event_type: str
    run_id: str
    request_id: str
    outcome: Outcome
    timestamp_ms: int
    details: dict[str, Any]

    @classmethod
    def build(
        cls,
        *,
        event_type: str,
        run_id: str,
        request_id: str,
        outcome: Outcome,
        timestamp_ms: int,
        details: dict[str, Any],
    ) -> "TradingAuditEvent":
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("event_type must be nonblank")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be nonblank")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be nonblank")
        if outcome not in {"ALLOW", "DENY", "ERROR", "UNKNOWN", "HUMAN_REQUIRED"}:
            raise ValueError("invalid audit outcome")
        if timestamp_ms < 0:
            raise ValueError("timestamp_ms must be nonnegative")
        if not isinstance(details, dict):
            raise ValueError("details must be an object")

        sanitized = sanitize_telemetry(details)
        event = cls(
            schema_version="1.0",
            event_type=event_type.strip(),
            run_id=run_id.strip(),
            request_id=request_id.strip(),
            outcome=outcome,
            timestamp_ms=timestamp_ms,
            details=sanitized,
        )
        if len(event.to_json().encode("utf-8")) > MAX_EVENT_BYTES:
            raise ValueError("audit event exceeds maximum size")
        return event

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "event_type": self.event_type,
                "run_id": self.run_id,
                "request_id": self.request_id,
                "outcome": self.outcome,
                "timestamp_ms": self.timestamp_ms,
                "details": self.details,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
