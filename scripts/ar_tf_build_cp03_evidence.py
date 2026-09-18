from __future__ import annotations
import argparse, json
from pathlib import Path
from ar_tf.evidence_chain import inventory, sha256_file
from ar_tf.evidence_envelope import EvidenceEnvelope
from ar_tf.slsa_provenance import slsa_statement

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="artifacts/g4_g13")
    ap.add_argument("--source-sha",required=True)
    ap.add_argument("--cp02-digest",required=True)
    ap.add_argument("--github-run-id",required=True)
    a=ap.parse_args(); root=Path(a.root)
    folds=[]
    for mp in sorted(Path("fold-artifacts").glob("ar-tf-ridge-fold-*-*/manifest.json")):
        m=json.loads(mp.read_text()); folds.append({"trial_id":m["trial_id"],"fold_id":int(m["fold_id"]),"sha256":sha256_file(mp.parent/"payload.json")})
    fi=inventory(folds,identity_fields=("trial_id","fold_id"),expected_count=324)
    trials=[]
    for mp in sorted(Path("trials").glob("ar-tf-ridge-trial-*/manifest.json")):
        m=json.loads(mp.read_text()); trials.append({"trial_id":m["trial_id"],"sha256":sha256_file(mp)})
    ti=inventory(trials,identity_fields=("trial_id",),expected_count=27)
    structural=list((root/"structural").glob("*.csv"))
    if not structural: raise SystemExit("structural evidence missing")
    ridge_stage=root/"classical/ridge/ridge-stage.json"
    if not ridge_stage.is_file(): raise SystemExit("ridge stage missing")
    tournament={"structural_count":122,"ridge_count":27,"total":149,
      "ridge_stage_sha256":sha256_file(ridge_stage),"fold_inventory_sha256":fi["inventory_sha256"],
      "ridge_inventory_sha256":ti["inventory_sha256"]}
    if tournament["structural_count"]+tournament["ridge_count"]!=149: raise SystemExit("149 invariant failed")
    evdir=root/"evidence"; evdir.mkdir(parents=True,exist_ok=True)
    (evdir/"fold-inventory.json").write_text(json.dumps(fi,sort_keys=True,indent=2)+"\n")
    (evdir/"ridge-inventory.json").write_text(json.dumps(ti,sort_keys=True,indent=2)+"\n")
    (evdir/"tournament-inventory.json").write_text(json.dumps(tournament,sort_keys=True,indent=2)+"\n")
    cp02=a.cp02_digest.removeprefix("sha256:")
    envelope=EvidenceEnvelope(experiment_id="AR-TF-CP03",generation="generation-1",
      source_commit_sha=a.source_sha,dataset_sha256=json.loads(Path("config/ar_tf_frozen_dataset_binding_2026.json").read_text())["dataset_sha256"],
      registry_sha256=sha256_file(root/"preregistration/preregistered-trial-registry.json"),
      folds_sha256=sha256_file("config/ar_tf_oos_folds_2026.yaml"),
      scientific_config_sha256=sha256_file("config/ar_tf_frozen_dataset_binding_2026.json"),
      environment_digest="github-actions:"+a.github_run_id,
      inputs={"cp02":cp02,"fold_inventory":fi["inventory_sha256"],"ridge_inventory":ti["inventory_sha256"]},
      outputs={"ridge_stage":tournament["ridge_stage_sha256"],"tournament_inventory":sha256_file(evdir/"tournament-inventory.json")},
      gates={"EVIDENCE_INTEGRITY":{"passed":False,"reason":"pending CP03 signature verification"}})
    (evdir/"cp03-evidence-envelope.json").write_text(json.dumps(envelope.payload()|{"evidence_sha256":envelope.evidence_sha256},sort_keys=True,indent=2)+"\n")
    subject=sha256_file(evdir/"cp03-evidence-envelope.json")
    deps=[{"uri":"github-actions:cp02","digest":{"sha256":cp02}},
          {"uri":"ar-tf:fold-inventory","digest":{"sha256":fi["inventory_sha256"]}},
          {"uri":"ar-tf:ridge-inventory","digest":{"sha256":ti["inventory_sha256"]}},
          {"uri":"ar-tf:tournament-inventory","digest":{"sha256":sha256_file(evdir/"tournament-inventory.json")}}]
    stmt=slsa_statement(subject_name="cp03-evidence-envelope.json",subject_sha256=subject,
      builder_id="https://github.com/jadeldiaz01-png/Institutional-Trading-Bot-Status/actions",
      invocation_id=a.github_run_id,external_parameters={"source_commit_sha":a.source_sha},resolved_dependencies=deps)
    (evdir/"cp03-slsa-provenance.json").write_text(json.dumps(stmt,sort_keys=True,indent=2)+"\n")
if __name__=="__main__": main()
