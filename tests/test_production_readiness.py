import json
from pathlib import Path

from jsonschema import Draft202012Validator

from ar_tf.production_readiness import GATE_IDS, REQUIRED_DOMAINS, canonical_sha256, evaluate_readiness


def frozen_dataset():
    return {
        "decision": "FROZEN_DATASET",
        "frozen": True,
        "unresolved_count": 0,
        "unresolved_anomaly_count": 0,
        "unresolved_gap_count": 0,
        "invalid_checksum_evidence_count": 0,
        "lifecycle_binding_verified": True,
        "source_plan_binding_verified": True,
        "holdout_evaluated": False,
        "dataset_sha256": "a" * 64,
        "verified_lifecycle_sha256": "d" * 64,
        "dataset_manifest_sha256": "e" * 64,
    }


def pass_domain(name: str, commit: str):
    digest = "c" * 64
    return {
        "status": "PASS",
        "items": [{
            "status": "PASS",
            "artifact": f"{name}.json",
            "sha256": digest,
            "source_commit_sha": commit,
            "issuer": f"{name}-certifier",
            "verification": "VERIFIED",
            "provenance": {
                "required": True,
                "verified": True,
                "attestation_subject_digest": "sha256:" + digest,
                "issuer": "https://token.actions.githubusercontent.com",
                "identity": f"repo:jadeldiaz01-png/Institutional-Trading-Bot-Status:{name}",
            },
        }],
    }


def pass_gates():
    return [{"id": gid, "status": "PASS", "blocking": True, "evidence": [f"{gid}.json"], "blocker": None} for gid in GATE_IDS]


def test_missing_evidence_is_no_go_and_all_gates_blocked():
    r = evaluate_readiness(source_commit_sha="b" * 40)
    assert r.manifest["decision"] == "NO_GO"
    assert len(r.manifest["gates"]) == 33
    assert all(g["status"] == "BLOCKED" for g in r.manifest["gates"])
    assert not any(r.manifest["authorizations"].values())
    assert r.manifest["live_ready"] is False


def test_dataset_requires_all_freeze_bindings_and_zero_unresolved():
    cert = frozen_dataset(); cert["source_plan_binding_verified"] = False
    r = evaluate_readiness(source_commit_sha="b" * 40, dataset_certificate=cert)
    gates = {g["id"]: g for g in r.manifest["gates"]}
    assert r.manifest["evidence"]["dataset"]["status"] == "FAIL"
    assert gates["G1"]["status"] == "FAIL"
    assert gates["G3"]["status"] == "FAIL"
    assert r.manifest["certifications"]["DATA_VERIFIED"] is False


def test_frozen_dataset_passes_only_g1_g3_not_full_data_certification():
    r = evaluate_readiness(source_commit_sha="b" * 40, dataset_certificate=frozen_dataset())
    gates = {g["id"]: g for g in r.manifest["gates"]}
    assert gates["G1"]["status"] == "PASS"
    assert gates["G3"]["status"] == "PASS"
    assert gates["G2"]["status"] == "BLOCKED"
    assert gates["G4"]["status"] == "BLOCKED"
    assert r.manifest["certifications"]["DATA_VERIFIED"] is False


def test_self_declared_pass_without_immutable_evidence_fails():
    commit = "b" * 40
    ev = {d: {"status": "PASS", "items": []} for d in REQUIRED_DOMAINS}
    r = evaluate_readiness(source_commit_sha=commit, dataset_certificate=frozen_dataset(), evidence=ev)
    assert r.manifest["evidence"]["execution"]["status"] == "FAIL"
    assert "no_evidence_items" in r.manifest["evidence"]["execution"]["validation_reasons"]


def test_commit_mismatch_invalidates_domain():
    commit = "b" * 40
    ev = {d: pass_domain(d, commit) for d in REQUIRED_DOMAINS}
    ev["execution"]["items"][0]["source_commit_sha"] = "d" * 40
    r = evaluate_readiness(source_commit_sha=commit, dataset_certificate=frozen_dataset(), evidence=ev)
    assert r.manifest["evidence"]["execution"]["status"] == "FAIL"
    assert "item_0:source_commit_mismatch" in r.manifest["evidence"]["execution"]["validation_reasons"]


def test_provenance_digest_mismatch_invalidates_domain():
    commit = "b" * 40
    ev = {d: pass_domain(d, commit) for d in REQUIRED_DOMAINS}
    ev["supply_chain"]["items"][0]["provenance"]["attestation_subject_digest"] = "sha256:" + "f" * 64
    r = evaluate_readiness(source_commit_sha=commit, dataset_certificate=frozen_dataset(), evidence=ev)
    assert r.manifest["evidence"]["supply_chain"]["status"] == "FAIL"
    assert "item_0:attestation_subject_digest_mismatch" in r.manifest["evidence"]["supply_chain"]["validation_reasons"]


def test_all_pass_gates_without_domains_still_no_go():
    r = evaluate_readiness(source_commit_sha="b" * 40, gates=pass_gates())
    assert r.manifest["certifications"]["LIVE_PRODUCTION_READY_VERIFIED"] is False
    assert r.manifest["decision"] == "NO_GO"
    assert r.manifest["live_ready"] is False
    assert not any(r.manifest["authorizations"].values())


def test_full_verified_domains_and_gates_can_certify_but_never_authorize_capital():
    commit = "b" * 40
    ev = {d: pass_domain(d, commit) for d in REQUIRED_DOMAINS}
    r = evaluate_readiness(source_commit_sha=commit, dataset_certificate=frozen_dataset(), evidence=ev, gates=pass_gates())
    assert r.manifest["certifications"]["LIVE_PRODUCTION_READY_VERIFIED"] is True
    assert r.manifest["decision"] == "LIVE_PRODUCTION_READY_VERIFIED"
    assert r.manifest["live_ready"] is True
    assert not any(r.manifest["authorizations"].values())


def test_holdout_closed_by_default_and_identities_explicit():
    r = evaluate_readiness(source_commit_sha="b" * 40, dataset_certificate=frozen_dataset())
    assert r.manifest["metrics"]["holdout"]["opened"] is False
    assert r.manifest["identities"]["dataset_sha256"] == "a" * 64
    assert r.manifest["identities"]["lifecycle_sha256"] == "d" * 64
    assert "strategy_config_sha256" in r.manifest["identities"]


def test_generated_manifest_matches_schema():
    schema = json.loads(Path("schemas/production-readiness-manifest.schema.json").read_text(encoding="utf-8"))
    manifest = evaluate_readiness(source_commit_sha="b" * 40).manifest
    errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: list(e.path))
    assert errors == [], [e.message for e in errors]


def test_hash_is_canonical():
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})
