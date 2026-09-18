import pytest
from ar_tf.evidence_chain import inventory,merkle_root_hex,GateEvidence
D=lambda c:c*64

def test_inventory_is_order_independent_and_exact():
    a=[{"trial_id":"b","fold_id":0,"sha256":D("b")},{"trial_id":"a","fold_id":0,"sha256":D("a")}]
    x=inventory(a,identity_fields=("trial_id","fold_id"),expected_count=2)
    y=inventory(list(reversed(a)),identity_fields=("trial_id","fold_id"),expected_count=2)
    assert x["inventory_sha256"]==y["inventory_sha256"] and x["merkle_root"]==y["merkle_root"]
    with pytest.raises(ValueError): inventory(a,identity_fields=("trial_id","fold_id"),expected_count=3)

def test_duplicate_identity_fails_closed():
    with pytest.raises(ValueError):
        inventory([{"trial_id":"a","fold_id":0,"sha256":D("a")},{"trial_id":"a","fold_id":0,"sha256":D("b")}],
                  identity_fields=("trial_id","fold_id"),expected_count=2)

def test_gate_evidence_binds_inputs_and_implementation():
    g=GateEvidence("DATA_INTEGRITY",True,D("a"),(D("b"),),{"unresolved":0},{"max_unresolved":0},{"dataset":D("c")})
    assert len(g.evidence_sha256)==64
