from __future__ import annotations

import re
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_PASS_FIELDS = ("artifact", "sha256", "source_commit_sha", "issuer", "verification")


def validate_evidence_item(item: dict[str, Any], *, expected_commit_sha: str) -> tuple[bool, list[str]]:
    """Validate immutable production evidence without trusting self-declared PASS."""
    reasons: list[str] = []
    if item.get("status") != "PASS":
        return False, ["status_not_pass"]
    for field in REQUIRED_PASS_FIELDS:
        if not item.get(field):
            reasons.append(f"missing_{field}")

    digest = str(item.get("sha256", ""))
    if digest and not SHA256_RE.fullmatch(digest):
        reasons.append("invalid_sha256")

    commit = str(item.get("source_commit_sha", ""))
    if commit and not COMMIT_RE.fullmatch(commit):
        reasons.append("invalid_source_commit_sha")
    if commit != expected_commit_sha:
        reasons.append("source_commit_mismatch")

    if item.get("verification") != "VERIFIED":
        reasons.append("verification_not_verified")

    provenance = item.get("provenance", {})
    if provenance.get("required") is True:
        if provenance.get("verified") is not True:
            reasons.append("provenance_unverified")
        subject = str(provenance.get("attestation_subject_digest", ""))
        if not subject:
            reasons.append("missing_attestation_subject_digest")
        elif digest and subject != f"sha256:{digest}":
            reasons.append("attestation_subject_digest_mismatch")
        if not provenance.get("issuer"):
            reasons.append("missing_provenance_issuer")
        if not provenance.get("identity"):
            reasons.append("missing_provenance_identity")

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
            reasons.extend(f"item_{idx}:{reason}" for reason in item_reasons)
    return not reasons, reasons
