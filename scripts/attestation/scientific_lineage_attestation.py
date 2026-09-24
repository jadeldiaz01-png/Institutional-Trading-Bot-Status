#!/usr/bin/env python3
"""Build and validate the immutable subject for SCIENTIFIC-LINEAGE attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCIENTIFIC_SHA = "68ab70b0a531b86b1a02db0e404aa69a5a088b95"
SOURCE_RUN_ID = 34791917236
SOURCE_ARTIFACT_ID = 10329460355
SOURCE_ARTIFACT_DIGEST = "sha256:f2c0ddeecf21dd17b2bd71d162dfc1c5b497389a9a3ef46624775f41652e7f60"
SOURCE_CODE_SHA = "bcfe3fbbd9892424118e84a1743a5e71a94c092d"
DATASET_SHA256 = "d1686e5fba9524c78e8a0e9a90d0f38efc1c6b883ebf1389dd4b47bb2984aaae"
CP03_RUN_ID = 35752271068
REDUCER_JOB_ID = 106833215818
CP03_ARTIFACT_ID = 10706323289
CP03_ARTIFACT_DIGEST = "sha256:7315d1527381476c71f30913447cd8483db9dc984e7cb0cdc0a31e25ddeed844"

BINDING_PATH = Path("config/ar_tf_frozen_dataset_binding_2026.json")
FOLDS_PATH = Path("config/ar_tf_oos_folds_2026.yaml")
TOURNAMENT_PATH = Path("config/ar_tf_master_strategy_tournament_2026.yaml")
PROVENANCE_PATH = Path("src/ar_tf/slsa_provenance.py")

SHA40 = re.compile(r"^[0-9a-f]{40}$")


class AttestationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AttestationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AttestationError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AttestationError(f"invalid JSON in {path}: {exc}") from exc
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def validate_science_root(science_root: Path) -> dict[str, Any]:
    binding_file = science_root / BINDING_PATH
    folds_file = science_root / FOLDS_PATH
    tournament_file = science_root / TOURNAMENT_PATH
    provenance_file = science_root / PROVENANCE_PATH

    binding = load_json(binding_file)
    require(binding.get("binding_type") == "AR_TF_FROZEN_DATASET_BINDING", "unexpected binding_type")
    require(binding.get("source_run_id") == SOURCE_RUN_ID, "source_run_id mismatch")
    require(binding.get("source_artifact_id") == SOURCE_ARTIFACT_ID, "source_artifact_id mismatch")
    require(binding.get("source_artifact_digest") == SOURCE_ARTIFACT_DIGEST, "source_artifact_digest mismatch")
    require(binding.get("source_code_sha") == SOURCE_CODE_SHA, "source_code_sha mismatch")
    require(binding.get("dataset_sha256") == DATASET_SHA256, "dataset_sha256 mismatch")
    require(binding.get("decision") == "FROZEN_DATASET", "dataset is not FROZEN_DATASET")
    require(binding.get("frozen") is True, "dataset binding is not frozen")
    require(binding.get("unresolved_count") == 0, "binding unresolved_count is nonzero")
    require(binding.get("unresolved_anomaly_count") == 0, "binding unresolved_anomaly_count is nonzero")
    require(binding.get("unresolved_gap_count") == 0, "binding unresolved_gap_count is nonzero")
    require(binding.get("invalid_checksum_evidence_count") == 0, "binding checksum evidence is invalid")
    require(binding.get("holdout_evaluated") is False, "holdout_evaluated must remain false")
    require(binding.get("paper_authorized") is False, "paper_authorized must remain false")
    require(binding.get("testnet_authorized") is False, "testnet_authorized must remain false")
    require(binding.get("live_authorized") is False, "live_authorized must remain false")
    require(binding.get("tournament_use", {}).get("holdout_must_remain_closed") is True,
            "holdout_must_remain_closed must remain true")

    folds = folds_file.read_text(encoding="utf-8")
    for literal in (
        "state: FROZEN_PRE_HOLDOUT_FOLDS",
        "policy: SINGLE_UNTOUCHED_365D_HOLDOUT",
        "opened: false",
        "selection_access_forbidden: true",
        "feature_engineering_access_forbidden: true",
        "model_tuning_access_forbidden: true",
    ):
        require(literal in folds, f"missing frozen-fold invariant: {literal}")

    tournament = tournament_file.read_text(encoding="utf-8")
    require("null_hypothesis: NO_EDGE_VERIFIED" in tournament, "null hypothesis changed")

    provenance = provenance_file.read_text(encoding="utf-8")
    require('IN_TOTO_STATEMENT_V1="https://in-toto.io/Statement/v1"' in provenance,
            "in-toto statement contract changed")
    require('SLSA_PROVENANCE_V1="https://slsa.dev/provenance/v1"' in provenance,
            "SLSA provenance predicate changed")

    return {
        "binding_sha256": sha256_file(binding_file),
        "folds_sha256": sha256_file(folds_file),
        "tournament_sha256": sha256_file(tournament_file),
        "provenance_implementation_sha256": sha256_file(provenance_file),
    }


def build_subject(
    *,
    science_root: Path,
    source_repository: str,
    attestor_commit_sha: str,
    attestor_workflow_ref: str,
    attestor_run_id: str,
    attestor_run_attempt: str,
) -> dict[str, Any]:
    require(bool(source_repository), "source_repository required")
    require(SHA40.fullmatch(attestor_commit_sha) is not None, "attestor_commit_sha must be a 40-char lowercase SHA")
    require(bool(attestor_workflow_ref), "attestor_workflow_ref required")
    require(str(attestor_run_id).isdigit(), "attestor_run_id must be numeric")
    require(str(attestor_run_attempt).isdigit(), "attestor_run_attempt must be numeric")
    digests = validate_science_root(science_root)

    return {
        "schema_version": "1.0.0",
        "attestation_class": "SCIENTIFIC_LINEAGE",
        "source_repository": source_repository,
        "attestor": {
            "commit_sha": attestor_commit_sha,
            "workflow_ref": attestor_workflow_ref,
            "run_id": str(attestor_run_id),
            "run_attempt": str(attestor_run_attempt),
        },
        "scientific_sha": SCIENTIFIC_SHA,
        "frozen_binding": {
            "path": str(BINDING_PATH),
            "sha256": digests["binding_sha256"],
            "source_run_id": SOURCE_RUN_ID,
            "source_artifact_id": SOURCE_ARTIFACT_ID,
            "source_artifact_digest": SOURCE_ARTIFACT_DIGEST,
            "source_code_sha": SOURCE_CODE_SHA,
            "dataset_sha256": DATASET_SHA256,
            "decision": "FROZEN_DATASET",
            "frozen": True,
            "unresolved_count": 0,
            "holdout_evaluated": False,
        },
        "scientific_contract": {
            "folds_path": str(FOLDS_PATH),
            "folds_sha256": digests["folds_sha256"],
            "tournament_path": str(TOURNAMENT_PATH),
            "tournament_sha256": digests["tournament_sha256"],
            "provenance_implementation_path": str(PROVENANCE_PATH),
            "provenance_implementation_sha256": digests["provenance_implementation_sha256"],
        },
        "evidence_chain": {
            "cp03_run_id": CP03_RUN_ID,
            "reducer_job_id": REDUCER_JOB_ID,
            "verified_folds": 324,
            "verified_trials": 27,
            "trial_count_total": 149,
            "cp03_artifact_id": CP03_ARTIFACT_ID,
            "cp03_artifact_digest": CP03_ARTIFACT_DIGEST,
            "scientific_decision": "NO_EDGE_VERIFIED",
        },
        "safety": {
            "holdout_opened": False,
            "holdout_evaluated": False,
            "paper_authorized": False,
            "testnet_authorized": False,
            "live_authorized": False,
        },
    }


def verify_subject(subject: dict[str, Any], *, science_root: Path) -> None:
    expected = build_subject(
        science_root=science_root,
        source_repository=subject.get("source_repository", ""),
        attestor_commit_sha=subject.get("attestor", {}).get("commit_sha", ""),
        attestor_workflow_ref=subject.get("attestor", {}).get("workflow_ref", ""),
        attestor_run_id=subject.get("attestor", {}).get("run_id", ""),
        attestor_run_attempt=subject.get("attestor", {}).get("run_attempt", ""),
    )
    require(subject == expected, "subject does not exactly match the frozen SCIENTIFIC-LINEAGE contract")


def emit_verification(
    *,
    subject_path: Path,
    bundle_path: Path,
    output_path: Path,
    certificate_identity: str,
    oidc_issuer: str,
) -> None:
    subject = load_json(subject_path)
    require(subject.get("attestation_class") == "SCIENTIFIC_LINEAGE", "wrong attestation_class")
    bundle = load_json(bundle_path)
    require(bool(bundle), "Sigstore bundle is empty")
    require(bool(certificate_identity), "certificate identity required")
    require(oidc_issuer == "https://token.actions.githubusercontent.com", "unexpected OIDC issuer")

    result = {
        "schema_version": "1.0.0",
        "gate_id": "SCIENTIFIC_LINEAGE_ATTESTATION",
        "passed": True,
        "subject_sha256": sha256_file(subject_path),
        "sigstore_bundle_sha256": sha256_file(bundle_path),
        "attestor_commit_sha": subject["attestor"]["commit_sha"],
        "attestor_workflow_ref": subject["attestor"]["workflow_ref"],
        "attestor_run_id": subject["attestor"]["run_id"],
        "attestor_run_attempt": subject["attestor"]["run_attempt"],
        "scientific_sha": subject["scientific_sha"],
        "certificate_identity": certificate_identity,
        "oidc_issuer": oidc_issuer,
        "source_artifact_digest": subject["frozen_binding"]["source_artifact_digest"],
        "dataset_sha256": subject["frozen_binding"]["dataset_sha256"],
        "cp03_artifact_digest": subject["evidence_chain"]["cp03_artifact_digest"],
        "holdout_opened": False,
        "holdout_evaluated": False,
        "paper_authorized": False,
        "testnet_authorized": False,
        "live_authorized": False,
    }
    output_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def command_build(args: argparse.Namespace) -> None:
    subject = build_subject(
        science_root=Path(args.science_root),
        source_repository=args.source_repository,
        attestor_commit_sha=args.attestor_commit_sha,
        attestor_workflow_ref=args.attestor_workflow_ref,
        attestor_run_id=args.attestor_run_id,
        attestor_run_attempt=args.attestor_run_attempt,
    )
    Path(args.output).write_bytes(canonical_bytes(subject))
    print(f"SUBJECT_SHA256={sha256_file(Path(args.output))}")


def command_verify(args: argparse.Namespace) -> None:
    subject = load_json(Path(args.subject))
    verify_subject(subject, science_root=Path(args.science_root))
    print("SCIENTIFIC_LINEAGE_SUBJECT_VALID=true")


def command_emit(args: argparse.Namespace) -> None:
    emit_verification(
        subject_path=Path(args.subject),
        bundle_path=Path(args.bundle),
        output_path=Path(args.output),
        certificate_identity=args.certificate_identity,
        oidc_issuer=args.oidc_issuer,
    )
    print(f"VERIFICATION_SHA256={sha256_file(Path(args.output))}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--science-root", required=True)
    build.add_argument("--source-repository", required=True)
    build.add_argument("--attestor-commit-sha", required=True)
    build.add_argument("--attestor-workflow-ref", required=True)
    build.add_argument("--attestor-run-id", required=True)
    build.add_argument("--attestor-run-attempt", required=True)
    build.add_argument("--output", required=True)
    build.set_defaults(func=command_build)

    verify = sub.add_parser("verify-subject")
    verify.add_argument("--science-root", required=True)
    verify.add_argument("--subject", required=True)
    verify.set_defaults(func=command_verify)

    emit = sub.add_parser("emit-verification")
    emit.add_argument("--subject", required=True)
    emit.add_argument("--bundle", required=True)
    emit.add_argument("--output", required=True)
    emit.add_argument("--certificate-identity", required=True)
    emit.add_argument("--oidc-issuer", required=True)
    emit.set_defaults(func=command_emit)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        args.func(args)
    except AttestationError as exc:
        print(f"scientific-lineage-attestation: FAIL: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
