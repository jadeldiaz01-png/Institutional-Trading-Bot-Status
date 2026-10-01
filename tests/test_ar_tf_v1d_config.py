from pathlib import Path

import yaml


def test_v1d_config_is_research_only_and_holdout_locked():
    cfg = yaml.safe_load(Path("config/ar_tf_v1d_tournament.yaml").read_text(encoding="utf-8"))
    assert cfg["stage"] == "RESEARCH"
    assert cfg["paper_automatic_promotion"] is False
    assert cfg["holdout"]["evaluate_during_tournament"] is False
    assert cfg["selection"]["forbid_holdout_tuning"] is True
    assert cfg["selection"]["maximum_automated_state"] == "FROZEN_HOLDOUT_CANDIDATE"
