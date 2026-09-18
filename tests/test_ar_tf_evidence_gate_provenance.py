import hashlib
import pytest
from ar_tf.evidence_envelope import EvidenceEnvelope
from ar_tf.gate_engine import GateResult, MANDATORY_GATES, adjudicate
from ar_tf.slsa_provenance import slsa_statement, IN_TOTO_STATEMENT_V1, SLSA_PROVENANCE_V1

D="a"*64
def env():
    return EvidenceEnvelope("exp-1","generation-2","deadbeef",D,D,D,D,"sha256:"+D,
        {"dataset":D},{"predictions":D},{"DATA_INTEGRITY":{"passed":True}})

def test_envelope_is_deterministic_and_fail_closed():
    a=env(); b=env()
    assert a.evidence_sha256==b.evidence_sha256
    with pytest.raises(ValueError):
        EvidenceEnvelope("e","g","s",D,D,D,D,"x",{"d":D},{"o":D},{},holdout_opened=True)

def test_gate_engine_is_conjunctive_not_scored():
    rows=[GateResult(g,True,D,{}) for g in MANDATORY_GATES]
    assert adjudicate(rows)["decision"]=="FROZEN_HOLDOUT_CANDIDATE"
    rows[-1]=GateResult(MANDATORY_GATES[-1],False,D,{"reason":"fail"})
    out=adjudicate(rows)
    assert out["decision"]=="NO_EDGE_VERIFIED" and out["failed_gates"]==[MANDATORY_GATES[-1]]
    assert out["holdout_opened"] is False and out["live_authorized"] is False

def test_gate_engine_rejects_missing_and_duplicate_gates():
    rows=[GateResult(g,True,D,{}) for g in MANDATORY_GATES[:-1]]
    with pytest.raises(ValueError): adjudicate(rows)
    rows=[GateResult(g,True,D,{}) for g in MANDATORY_GATES]+[GateResult(MANDATORY_GATES[0],True,D,{})]
    with pytest.raises(ValueError): adjudicate(rows)

def test_slsa_statement_uses_in_toto_and_slsa_v1():
    s=slsa_statement(subject_name="cp03.json",subject_sha256=D,builder_id="github-actions",
      invocation_id="run-1",external_parameters={"source_commit_sha":"abc"},
      resolved_dependencies=[{"name":"dataset","digest":{"sha256":D}}])
    assert s["_type"]==IN_TOTO_STATEMENT_V1
    assert s["predicateType"]==SLSA_PROVENANCE_V1
    assert s["subject"][0]["digest"]["sha256"]==D
    assert s["predicate"]["buildDefinition"]["resolvedDependencies"][0]["digest"]["sha256"]==D
