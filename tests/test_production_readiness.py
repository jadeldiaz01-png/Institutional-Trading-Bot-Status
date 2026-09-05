from ar_tf.production_readiness import REQUIRED_DOMAINS, canonical_sha256, evaluate_readiness


def frozen_dataset():
    return {
        "decision": "FROZEN_DATASET",
        "frozen": True,
        "unresolved_count": 0,
        "unresolved_anomaly_count": 0,
        "unresolved_gap_count": 0,
        "invalid_checksum_evidence_count": 0,
        "holdout_evaluated": False,
        "dataset_sha256": "a" * 64,
    }


def pass_domain(name: str, commit: str):
    return {
        "status": "PASS",
        "items": [{
            "status": "PASS",
            "artifact": f"{name}.json",
            "sha256": "c" * 64,
            "source_commit_sha": commit,
            "issuer": f"{name}-certifier",
            "verification": "VERIFIED",
            "provenance": {
                "required": True,
                "verified": True,
                "attestation_subject_digest": "sha256:" + "c" * 64,
            },
        }],
    }


def test_missing_evidence_is_no_go():
    r = evaluate_readiness(source_commit_sha="b" * 40)
    assert r.manifest["decision"] == "NO_GO"
    assert not any(r.manifest["authorizations"].values())


def test_dataset_requires_zero_unresolved():
    cert = frozen_dataset()
    cert["unresolved_count"] = 1
    r = evaluate_readiness(source_commit_sha="b" * 40, dataset_certificate=cert)
    assert r.manifest["evidence"]["dataset"]["status"] == "FAIL"
    assert r.manifest["decision"] == "NO_GO"


def test_self_declared_pass_without_immutable_evidence_fails():
    commit = "b" * 40
    ev = {d: {"status": "PASS", "items": []} for d in REQUIRED_DOMAINS}
    r = evaluate_readiness(source_commit_sha=commit, dataset_certificate=frozen_dataset(), evidence=ev)
    assert r.manifest["evidence"]["execution"]["status"] == "FAIL"
    assert "no_evidence_items" in r.manifest["evidence"]["execution"]["validation_reasons"]
    assert r.manifest["decision"] == "NO_GO"


def test_all_verified_domains_still_cannot_skip_holdout():
    commit = "b" * 40
    ev = {d: pass_domain(d, commit) for d in REQUIRED_DOMAINS}
    r = evaluate_readiness(
        source_commit_sha=commit,
        dataset_certificate=frozen_dataset(),
        evidence=ev,
        gates=[{"id": "institutional-evidence", "status": "PASS", "blocking": True, "reason": "verified"}],
    )
    assert r.manifest["decision"] == "FROZEN_HOLDOUT_CANDIDATE"
    assert r.manifest["stage"] == "RESEARCH"
    assert not any(r.manifest["authorizations"].values())


def test_commit_mismatch_invalidates_domain():
    commit = "b" * 40
    ev = {d: pass_domain(d, commit) for d in REQUIRED_DOMAINS}
    ev["execution"]["items"][0]["source_commit_sha"] = "d" * 40
    r = evaluate_readiness(source_commit_sha=commit, dataset_certificate=frozen_dataset(), evidence=ev)
    assert r.manifest["evidence"]["execution"]["status"] == "FAIL"
    assert "item_0:source_commit_mismatch" in r.manifest["evidence"]["execution"]["validation_reasons"]


def test_hash_is_canonical():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}
    assert canonical_sha256(a) == canonical_sha256(b)
