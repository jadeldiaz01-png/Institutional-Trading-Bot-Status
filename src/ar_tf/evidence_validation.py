from __future__ import annotations

import re
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA256_PREFIX_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_PASS_FIELDS = ("artifact", "sha256", "source_commit_sha", "issuer", "verification")


def validate_evidence_item(item: dict[str, Any], *, expected_commit_sha: str) -> tuple[bool, list[str]]:
    """Validate immutable evidence metadata without trusting a bare self-declared PASS.

    Same-commit evidence must be produced by the evaluated commit. Immutable evidence
    produced by a different commit is allowed only when an explicit cross-commit binding
    identifies the evaluated consumer commit and the verified source artifact/run digest.
    The caller/CI must independently verify those bytes against the external source.
    """
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

    evidence_class = str(item.get("evidence_class", "SAME_COMMIT"))
    if commit != expected_commit_sha:
        if evidence_class != "EXTERNAL_IMMUTABLE":
            reasons.append("source_commit_mismatch")
        else:
            binding = item.get("cross_commit_binding") or {}
            consumer = str(binding.get("consumer_commit_sha", ""))
            if consumer != expected_commit_sha:
                reasons.append("consumer_commit_mismatch")
            if binding.get("verified") is not True:
                reasons.append("cross_commit_binding_unverified")
            source_artifact_digest = str(binding.get("source_artifact_digest", ""))
            if not SHA256_PREFIX_RE.fullmatch(source_artifact_digest):
                reasons.append("invalid_source_artifact_digest")
            if not binding.get("source_artifact_id"):
                reasons.append("missing_source_artifact_id")
            if not binding.get("source_run_id"):
                reasons.append("missing_source_run_id")
            if binding.get("verification_method") != "GITHUB_ACTIONS_ARTIFACT_DIGEST_AND_CONTENT_HASH":
                reasons.append("invalid_cross_commit_verification_method")

    if item.get("verification") != "VERIFIED":
        reasons.append("verification_not_verified")

    scope_sha = str(item.get("scope_sha256", ""))
    if not SHA256_RE.fullmatch(scope_sha):
        reasons.append("invalid_scope_sha256")

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


def validate_domain_evidence(
    domain: dict[str, Any], *, expected_commit_sha: str, expected_scope_sha256: str | None = None
) -> tuple[bool, list[str]]:
    if domain.get("status") == "NOT_APPLICABLE":
        return True, []
    items = domain.get("items") or []
    if not items:
        return False, ["no_evidence_items"]
    reasons: list[str] = []
    for idx, item in enumerate(items):
        ok, item_reasons = validate_evidence_item(item, expected_commit_sha=expected_commit_sha)
        if expected_scope_sha256 and item.get("scope_sha256") != expected_scope_sha256:
            ok = False
            item_reasons = [*item_reasons, "scope_mismatch"]
        if not ok:
            reasons.extend(f"item_{idx}:{reason}" for reason in item_reasons)
    return not reasons, reasons
