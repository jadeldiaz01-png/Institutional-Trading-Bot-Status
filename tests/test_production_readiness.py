from ar_tf.production_readiness import canonical_sha256, evaluate_readiness


def frozen_dataset():
    return {
        "decision": "FROZEN_DATASET", "unresolved_count": 0,
        "unresolved_gap_count": 0, "invalid_checksum_evidence_count": 0,
        "holdout_evaluated": False, "dataset_sha256": "a" * 64,
    }


def test_missing_evidence_is_no_go():
    r = evaluate_readiness(source_commit_sha="b" * 40)
    assert r.manifest["decision"] == "NO_GO"
    assert not any(r.manifest["authorizations"].values())


def test_dataset_requires_zero_unresolved():
    cert = frozen_dataset(); cert["unresolved_count"] = 1
    r = evaluate_readiness(source_commit_sha="b" * 40, dataset_certificate=cert)
    assert r.manifest["evidence"]["dataset"]["status"] == "FAIL"
    assert r.manifest["decision"] == "NO_GO"


def test_all_domains_cannot_skip_holdout():
    ev = {d: {"status":"PASS","artifacts":[f"{d}.json"],"sha256":None} for d in (
        "dataset","quantitative","execution","risk","security","supply_chain",
        "reliability","observability","governance","finops")}
    r = evaluate_readiness(source_commit_sha="b" * 40, dataset_certificate=frozen_dataset(), evidence=ev,
                           gates=[{"id":"institutional-evidence","status":"PASS","blocking":True,"reason":"verified"}])
    assert r.manifest["decision"] == "FROZEN_HOLDOUT_CANDIDATE"
    assert r.manifest["stage"] == "RESEARCH"
    assert not any(r.manifest["authorizations"].values())


def test_hash_is_canonical():
    a = {"b":2,"a":1}; b = {"a":1,"b":2}
    assert canonical_sha256(a) == canonical_sha256(b)
