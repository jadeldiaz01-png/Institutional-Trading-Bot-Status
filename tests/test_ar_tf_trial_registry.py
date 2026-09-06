from ar_tf.trial_registry import build_registry


def _spec():
    return {
        "families": [
            {
                "family": "trend",
                "tier": "BASELINE",
                "data_track": "spot_daily_ohlcv",
                "seeds": [7, 19],
                "parameters": {"lookback": [30, 60], "vol_target": [False, True]},
            },
            {
                "family": "ridge",
                "tier": "CLASSICAL_ML",
                "seeds": [7],
                "parameters": {"alpha": [0.1, 1.0]},
            },
        ]
    }


def test_registry_counts_every_parameter_seed_attempt():
    r = build_registry(_spec(), dataset_sha256="a" * 64, lifecycle_sha256="b" * 64, source_commit_sha="c" * 40)
    assert r["trial_count"] == 10
    assert r["state"] == "PREREGISTERED_NOT_EXECUTED"
    assert r["holdout_evaluated"] is False
    assert len({x["trial_id"] for x in r["trials"]}) == 10


def test_registry_hash_is_deterministic():
    kwargs = dict(dataset_sha256="a" * 64, lifecycle_sha256="b" * 64, source_commit_sha="c" * 40)
    a = build_registry(_spec(), **kwargs)
    b = build_registry(_spec(), **kwargs)
    assert a["registry_sha256"] == b["registry_sha256"]
    assert [x["trial_sha256"] for x in a["trials"]] == [x["trial_sha256"] for x in b["trials"]]


def test_registry_is_bound_to_dataset_identity():
    a = build_registry(_spec(), dataset_sha256="a" * 64, lifecycle_sha256="b" * 64, source_commit_sha="c" * 40)
    b = build_registry(_spec(), dataset_sha256="d" * 64, lifecycle_sha256="b" * 64, source_commit_sha="c" * 40)
    assert a["registry_sha256"] != b["registry_sha256"]
    assert a["trials"][0]["trial_sha256"] != b["trials"][0]["trial_sha256"]


def test_registry_rejects_unknown_dataset_hash():
    try:
        build_registry(_spec(), dataset_sha256="UNKNOWN", lifecycle_sha256="b" * 64, source_commit_sha="c" * 40)
    except ValueError as exc:
        assert "dataset_sha256" in str(exc)
    else:
        raise AssertionError("unfrozen dataset identity must fail closed")
