"""NVIDIA Nemotron 3 Ultra advisory provider.

This module is deliberately side-effect free with respect to trading. It only
turns a bounded DecisionContext into a validated ModelDecision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .contracts import ModelDecision
from .model_prompt import DecisionContext, build_nemotron_messages


NEMOTRON_BASE_URL = "https://integrate.api.nvidia.com/v1"
NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
ALLOWED_HOST = "integrate.api.nvidia.com"


class NemotronProviderError(RuntimeError):
    pass


def _read_single_line(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"credential file missing: {path}")
    raw = path.read_text(encoding="utf-8")
    value = raw.rstrip("\r\n")
    if not value or "\n" in value or "\r" in value:
        raise ValueError("credential must contain exactly one nonempty line")
    return value


def _string_list(payload: dict[str, Any], name: str) -> tuple[str, ...]:
    value = payload.get(name)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise NemotronProviderError(f"{name} must be a JSON string array")
    return tuple(value)


@dataclass(frozen=True)
class NemotronClient:
    _api_key: str = field(repr=False)
    base_url: str = NEMOTRON_BASE_URL
    model: str = NEMOTRON_MODEL
    timeout: float = 30.0
    temperature: float = 0.1
    top_p: float = 0.95
    max_tokens: int = 2048

    @classmethod
    def from_api_key_file(
        cls,
        api_key_file: Path,
        *,
        timeout: float = 30.0,
    ) -> "NemotronClient":
        return cls(_api_key=_read_single_line(api_key_file), timeout=timeout)

    def _request_payload(self, context: DecisionContext) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": build_nemotron_messages(context),
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }

    def _post(self, context: DecisionContext) -> dict[str, Any]:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            raise NemotronProviderError("Nemotron base URL is not allowlisted")
        if self.model != NEMOTRON_MODEL:
            raise NemotronProviderError("unexpected Nemotron model configuration")

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        body = json.dumps(
            self._request_payload(context),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "institutional-trading-bot-status-binance-mcp/1.0",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise NemotronProviderError(f"Nemotron HTTP {response.status}")
                raw = response.read().decode("utf-8")
        except NemotronProviderError:
            raise
        except HTTPError as exc:
            raise NemotronProviderError(f"Nemotron HTTP {exc.code}") from exc
        except (URLError, OSError, TimeoutError) as exc:
            raise NemotronProviderError("Nemotron request failed") from exc

        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise NemotronProviderError("Nemotron response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise NemotronProviderError("unexpected Nemotron response schema")
        return payload

    def assess(self, context: DecisionContext) -> ModelDecision:
        response = self._post(context)

        choices = response.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise NemotronProviderError("Nemotron response must contain exactly one choice")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise NemotronProviderError("Nemotron response is missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise NemotronProviderError("Nemotron message content must be text")

        try:
            decision_payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise NemotronProviderError("Nemotron decision is not strict JSON") from exc
        if not isinstance(decision_payload, dict):
            raise NemotronProviderError("Nemotron decision must be a JSON object")

        expected_keys = {
            "symbol",
            "horizon",
            "action",
            "confidence",
            "rationale_summary",
            "evidence_refs",
            "assumptions",
            "invalidation_conditions",
            "risk_factors",
            "uncertainty",
            "data_freshness_ms",
            "input_snapshot_sha256",
        }
        if set(decision_payload) != expected_keys:
            raise NemotronProviderError("Nemotron decision keys do not match contract")
        if decision_payload["symbol"] != context.symbol:
            raise NemotronProviderError("Nemotron symbol binding mismatch")
        if decision_payload["horizon"] != context.horizon:
            raise NemotronProviderError("Nemotron horizon binding mismatch")
        if decision_payload["input_snapshot_sha256"] != context.input_snapshot_sha256:
            raise NemotronProviderError("Nemotron input snapshot binding mismatch")

        evidence_refs = _string_list(decision_payload, "evidence_refs")
        available_refs = {item.source_id for item in context.evidence}
        if not evidence_refs or any(ref not in available_refs for ref in evidence_refs):
            raise NemotronProviderError("Nemotron evidence reference is not bound to context")

        response_model = response.get("model")
        response_id = response.get("id")
        created = response.get("created")
        if not isinstance(response_model, str) or response_model != self.model:
            raise NemotronProviderError("Nemotron response model mismatch")
        if not isinstance(response_id, str) or not response_id.strip():
            raise NemotronProviderError("Nemotron response id missing")
        if not isinstance(created, int) or created < 0:
            raise NemotronProviderError("Nemotron response created timestamp invalid")

        try:
            return ModelDecision(
                model_provider="nvidia",
                model_id=self.model,
                model_version=response_model,
                request_id=response_id,
                timestamp_ms=created * 1000,
                symbol=decision_payload["symbol"],
                horizon=decision_payload["horizon"],
                action=decision_payload["action"],
                confidence=decision_payload["confidence"],
                rationale_summary=decision_payload["rationale_summary"],
                evidence_refs=evidence_refs,
                assumptions=_string_list(decision_payload, "assumptions"),
                invalidation_conditions=_string_list(
                    decision_payload, "invalidation_conditions"
                ),
                risk_factors=_string_list(decision_payload, "risk_factors"),
                uncertainty=decision_payload["uncertainty"],
                data_freshness_ms=decision_payload["data_freshness_ms"],
                input_snapshot_sha256=decision_payload["input_snapshot_sha256"],
            )
        except (TypeError, ValueError) as exc:
            raise NemotronProviderError("Nemotron decision failed validation") from exc
