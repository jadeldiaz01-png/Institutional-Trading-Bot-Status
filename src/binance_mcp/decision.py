"""Deterministic advisory ensemble for ChatGPT + Nemotron decisions."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from .canonical import sha256_json
from .contracts import DecisionAction, ModelDecision

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EnsembleStatus = Literal[
    "CANDIDATE",
    "HUMAN_REVIEW",
    "BLOCKED",
    "STALE",
    "PROVENANCE_MISMATCH",
]


@dataclass(frozen=True)
class DecisionBundle:
    chatgpt: ModelDecision
    nemotron: ModelDecision
    market_sha256: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if SHA256_RE.fullmatch(self.market_sha256) is None:
            raise ValueError("market_sha256 must be lowercase SHA-256")
        if SHA256_RE.fullmatch(self.evidence_sha256) is None:
            raise ValueError("evidence_sha256 must be lowercase SHA-256")

    def bundle_sha256(self) -> str:
        return sha256_json(self)


@dataclass(frozen=True)
class EnsembleDecision:
    action: DecisionAction
    status: EnsembleStatus
    reasons: tuple[str, ...]
    agreement: bool
    execution_authorized: bool
    bundle_sha256: str


def _no_trade(bundle: DecisionBundle, status: EnsembleStatus, *reasons: str) -> EnsembleDecision:
    return EnsembleDecision(
        action="NO_TRADE",
        status=status,
        reasons=tuple(reasons),
        agreement=False,
        execution_authorized=False,
        bundle_sha256=bundle.bundle_sha256(),
    )


def adjudicate(
    bundle: DecisionBundle,
    *,
    now_ms: int,
    max_age_ms: int,
) -> EnsembleDecision:
    if now_ms < 0:
        raise ValueError("now_ms must be nonnegative")
    if max_age_ms <= 0:
        raise ValueError("max_age_ms must be positive")

    decisions = (bundle.chatgpt, bundle.nemotron)

    for decision in decisions:
        if decision.symbol != bundle.chatgpt.symbol or decision.horizon != bundle.chatgpt.horizon:
            return _no_trade(bundle, "PROVENANCE_MISMATCH", "model_scope_mismatch")
        if decision.input_snapshot_sha256 != bundle.market_sha256:
            return _no_trade(bundle, "PROVENANCE_MISMATCH", "market_snapshot_mismatch")
        if decision.timestamp_ms > now_ms:
            return _no_trade(bundle, "STALE", "model_timestamp_in_future")
        if now_ms - decision.timestamp_ms > max_age_ms:
            return _no_trade(bundle, "STALE", "model_decision_expired")
        if decision.data_freshness_ms > max_age_ms:
            return _no_trade(bundle, "STALE", "model_input_stale")

    if bundle.chatgpt.input_snapshot_sha256 != bundle.nemotron.input_snapshot_sha256:
        return _no_trade(bundle, "PROVENANCE_MISMATCH", "model_snapshot_mismatch")

    if any(decision.action == "NO_TRADE" for decision in decisions):
        return _no_trade(bundle, "BLOCKED", "model_no_trade")

    if bundle.chatgpt.action != bundle.nemotron.action:
        return _no_trade(bundle, "HUMAN_REVIEW", "model_disagreement")

    if bundle.chatgpt.action == "HOLD":
        return _no_trade(bundle, "BLOCKED", "models_hold")

    return EnsembleDecision(
        action=bundle.chatgpt.action,
        status="CANDIDATE",
        reasons=("models_agree_advisory_only",),
        agreement=True,
        execution_authorized=False,
        bundle_sha256=bundle.bundle_sha256(),
    )
