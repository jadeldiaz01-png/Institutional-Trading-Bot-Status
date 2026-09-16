from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
from pathlib import Path
from typing import Any

from .ml_trials import walk_forward_predictions
from .research_panel import load_research_panel
from .ridge_fold_resume import checkpoint_manifest_path, checkpoint_trial_key, load_committed_fold
from .ridge_resume import (
    MAX_TRAINING_ROWS_PER_FOLD,
    execute_trial_checkpointed,
    runtime_fingerprint,
    runtime_fingerprint_sha256,
    trial_at,
    write_trial,
)

ROOT=Path('artifacts/g4_g13')
RUNTIME=Path('.ridge-runtime')
CHECKPOINTS=Path('ridge-checkpoints')
REGISTRY=ROOT/'preregistration/preregistered-trial-registry.json'
FOLDS=Path('config/ar_tf_oos_folds_2026.yaml')
BINDING=Path('config/ar_tf_frozen_dataset_binding_2026.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding='utf-8'))


def _context() -> dict[str, Any]:
    return json.loads((RUNTIME/'context.json').read_text(encoding='utf-8'))


def prepare(index: int, github_env: str | None) -> None:
    RUNTIME.mkdir(parents=True,exist_ok=True)
    registry=_load_registry(); trial=trial_at(registry,index)
    binding=json.loads(BINDING.read_text(encoding='utf-8'))
    cp02=os.environ['CP02_ARTIFACT_DIGEST']
    source_sha=os.environ['SOURCE_SHA']
    trial_key=checkpoint_trial_key(trial['trial_id'])
    lineage={
        'parent_checkpoint_sha256':cp02.split(':',1)[1],
        'source_commit_sha':source_sha,
        'dataset_sha256':binding['dataset_sha256'],
        'registry_sha256':_sha(REGISTRY),
        'folds_sha256':_sha(FOLDS),
        'config_sha256':_sha(BINDING),
        'runtime_fingerprint_sha256':runtime_fingerprint_sha256(),
        'seed':int(trial['seed']),
        'max_training_rows_per_fold':MAX_TRAINING_ROWS_PER_FOLD,
        'holdout_opened':False,
        'holdout_evaluated':False,
    }
    context={'index':index,'trial_id':trial['trial_id'],'trial_key':trial_key,'lineage':lineage,'runtime_fingerprint':runtime_fingerprint()}
    (RUNTIME/'context.json').write_text(json.dumps(context,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    panel=load_research_panel(ROOT/'frozen_dataset',FOLDS)
    with (RUNTIME/'panel.pkl').open('wb') as fh:
        pickle.dump(panel,fh,protocol=pickle.HIGHEST_PROTOCOL)
    if github_env:
        with Path(github_env).open('a',encoding='utf-8') as fh:
            fh.write(f"TRIAL_ID={trial['trial_id']}\n")
            fh.write(f"TRIAL_KEY={trial_key}\n")
    print(json.dumps(context,sort_keys=True))


def _panel():
    with (RUNTIME/'panel.pkl').open('rb') as fh:
        return pickle.load(fh)


def verify_fold(fold_id: int) -> None:
    ctx=_context(); tid=ctx['trial_id']
    mp=checkpoint_manifest_path(CHECKPOINTS,tid,fold_id)
    load_committed_fold(mp,expected_trial_id=tid,expected_fold_id=fold_id,expected_lineage=ctx['lineage'])
    print(f'VERIFIED {tid} key={ctx["trial_key"]} fold={fold_id:02d}')


def commit_through_fold(fold_id: int) -> None:
    ctx=_context(); registry=_load_registry(); trial=trial_at(registry,int(ctx['index']))
    walk_forward_predictions(
        _panel(),FOLDS,family='ridge',params=trial['params'],seed=int(trial['seed']),
        max_training_rows_per_fold=MAX_TRAINING_ROWS_PER_FOLD,
        checkpoint_root=CHECKPOINTS,checkpoint_trial_id=ctx['trial_id'],checkpoint_lineage=ctx['lineage'],
        stop_after_fold=fold_id,
    )
    verify_fold(fold_id)


def finalize() -> None:
    ctx=_context(); registry=_load_registry()
    result=execute_trial_checkpointed(
        panel=_panel(),registry=registry,folds_path=FOLDS,index=int(ctx['index']),
        checkpoint_root=CHECKPOINTS,lineage=ctx['lineage'],stop_after_fold=11,
    )
    write_trial(result,Path('ridge-trial'),ctx['lineage'])
    print(json.dumps({'trial_id':ctx['trial_id'],'trial_key':ctx['trial_key'],'fold_checkpoint_count':len(result['fold_inventory']),'status':'COMPLETED'},sort_keys=True))


def main() -> None:
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare'); p.add_argument('--index',type=int,required=True); p.add_argument('--github-env')
    p=sub.add_parser('verify-fold'); p.add_argument('--fold',type=int,required=True)
    p=sub.add_parser('commit-fold'); p.add_argument('--fold',type=int,required=True)
    sub.add_parser('finalize')
    args=parser.parse_args()
    if args.command=='prepare': prepare(args.index,args.github_env)
    elif args.command=='verify-fold': verify_fold(args.fold)
    elif args.command=='commit-fold': commit_through_fold(args.fold)
    elif args.command=='finalize': finalize()


if __name__=='__main__':
    main()
