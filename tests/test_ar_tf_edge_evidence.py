from ar_tf.edge_evidence import EdgeEvidence, EvidenceClass, classify_public_result, pre_holdout_edge_decision


def _internal_oos() -> EdgeEvidence:
    return EdgeEvidence(
        evidence_id="trial-oos",
        evidence_class=EvidenceClass.INTERNAL_OOS,
        reproducible=True,
        point_in_time=True,
        net_of_costs=True,
        multiplicity_adjusted=True,
        holdout_untouched=True,
        execution_realism=True,
        positive_expectancy=True,
    )


def _decision(**overrides):
    kwargs = dict(
        dataset_frozen=True,
        dataset_sha256="d" * 64,
        lifecycle_sha256="e" * 64,
        unresolved_data_defects=0,
        all_trials_preregistered=True,
        common_oos_folds=True,
        dsr_probability=0.99,
        pbo=0.10,
        white_reality_check_passed=True,
        hansen_spa_passed=True,
        parameter_plateau_passed=True,
        regime_stability_passed=True,
        cost_stress_passed=True,
        benchmark_superiority_passed=True,
    )
    kwargs.update(overrides)
    return pre_holdout_edge_decision([_internal_oos()], **kwargs)


def test_public_research_never_counts_as_internal_edge_proof():
    item = classify_public_result(source_id="paper-2026")
    assert item.evidence_class == EvidenceClass.EXTERNAL_PRIOR
    assert item.positive_expectancy is False
    assert item.reproducible is False


def test_unresolved_data_defect_blocks_edge_even_if_metrics_pass():
    result = _decision(unresolved_data_defects=1)
    assert result["decision"] == "NO_EDGE_VERIFIED"
    assert "UNRESOLVED_DATA_DEFECTS" in result["reasons"]
    assert result["paper_authorized"] is False
    assert result["holdout_evaluated"] is False


def test_external_prior_alone_cannot_create_holdout_candidate():
    result = pre_holdout_edge_decision(
        [classify_public_result(source_id="external")],
        dataset_frozen=True,
        dataset_sha256="d" * 64,
        lifecycle_sha256="e" * 64,
        unresolved_data_defects=0,
        all_trials_preregistered=True,
        common_oos_folds=True,
        dsr_probability=0.99,
        pbo=0.10,
        white_reality_check_passed=True,
        hansen_spa_passed=True,
        parameter_plateau_passed=True,
        regime_stability_passed=True,
        cost_stress_passed=True,
        benchmark_superiority_passed=True,
    )
    assert result["decision"] == "NO_EDGE_VERIFIED"
    assert "NO_REPRODUCIBLE_NET_POSITIVE_INTERNAL_OOS_EVIDENCE" in result["reasons"]


def test_white_reality_check_and_spa_are_separate_mandatory_gates():
    white_fail = _decision(white_reality_check_passed=False)
    spa_fail = _decision(hansen_spa_passed=False)
    assert "WHITE_REALITY_CHECK_GATE_FAILED" in white_fail["reasons"]
    assert "HANSEN_SPA_GATE_FAILED" in spa_fail["reasons"]
    assert white_fail["decision"] == "NO_EDGE_VERIFIED"
    assert spa_fail["decision"] == "NO_EDGE_VERIFIED"


def test_only_complete_internal_research_evidence_can_reach_frozen_candidate():
    result = _decision()
    assert result["decision"] == "FROZEN_HOLDOUT_CANDIDATE"
    assert result["required_next_gate"] == "SINGLE_UNTOUCHED_365D_HOLDOUT"
    assert result["paper_authorized"] is False
    assert result["live_authorized"] is False
