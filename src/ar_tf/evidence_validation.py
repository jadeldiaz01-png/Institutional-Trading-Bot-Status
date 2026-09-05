from __future__ import annotations

import re
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_PASS_FIELDS = (
    "artifact",
    "sha256",
    "source_commit_sha",
    "issuer",
    "verification",
)


def validate_evidence_item(item: dict[str, Any], *, expected_commit_sha: str) -> tuple[bool, list[str]]:
    """Validate one production evidence item without trusting self-declared PASS.

    PASS evidence must name an immutable artifact, bind a SHA-256 digest to the
    source commit, identify the issuer/workflow, and record an explicit verified
    result. This is intentionally deterministic: no LLM/agent judgment can turn
    missing evidence into PASS.
    """
    reasons: list[str] = []
    if item.get("status") != "PASS":
        reasons.append("status_not_pass")
        return False, reasons
    for field in REQUIRED_PASS_FIELDS:
        if not item.get(field):
            reasons.append(f"missing_{field}")
    digest = str(item.get("sha256", ""))
    if digest and not SHA256_RE.fullmatch(digest):
        reasons.append("invalid_sha256")
    if item.get("source_commit_sha") != expected_commit_sha:
        reasons.append("source_commit_mismatch")
    if item.get("verification") != "VERIFIED":
        reasons.append("verification_not_verified")
    provenance = item.get("provenance", {})
    if provenance.get("required") is True:
        if provenance.get("verified") is not True:
            reasons.append("provenance_unverified")
        if not provenance.get("attestation_subject_digest"):
            reasons.append("missing_attestation_subject_digest")
    return not reasons, reasons


def validate_domain_evidence(domain: dict[str, Any], *, expected_commit_sha: str) -> tuple[bool, list[str]]:
    if domain.get("status") == "NOT_APPLICABLE":
        return True, []
    items = domain.get("items") or []
    if not items:
        return False, ["no_evidence_items"]
    reasons: list[str] = []
    for idx, item in enumerate(items):
        ok, item_reasons = validate_evidence_item(item, expected_commit_sha=expected_commit_sha)
        if not ok:
            reasons.extend(f"item_{idx}:{r}" for r in item_reasons)
    return not reasons, reasons
