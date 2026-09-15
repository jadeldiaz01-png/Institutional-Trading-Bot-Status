import copy

import pandas as pd
import pytest

from ar_tf.ridge_resume import RIDGE_SHARDS, shard_trial_ids, validate_shards


def _registry():
    return {'trials':[{'trial_id':f'ridge-{i:02d}','family':'ridge','params':{},'seed':i} for i in range(27)]}


def _shards(reg):
    idx=pd.date_range('2026-01-01',periods=3,tz='UTC')
    out=[]
    for shard in range(3):
        ids=shard_trial_ids(reg,shard); frame=pd.DataFrame({x:[0.0,0.01,0.0] for x in ids},index=idx)
        out.append({'manifest':{'shard':shard,'trial_ids':ids,'trial_count':9,'failures':[],'parent_checkpoint_sha256':'a'*64,'dataset_sha256':'b'*64,'registry_sha256':'c'*64,'folds_sha256':'d'*64,'holdout_opened':False,'holdout_evaluated':False},'base':frame,'stressed':frame.copy(),'severe':frame.copy()})
    return out


def test_ridge_partition_is_exact_9_9_9():
    reg=_registry(); assert RIDGE_SHARDS==((0,9),(9,18),(18,27)); ids=sum((shard_trial_ids(reg,i) for i in range(3)),[]); assert len(ids)==27 and len(set(ids))==27


def test_reducer_is_order_invariant_and_exactly_once():
    reg=_registry(); shards=_shards(reg); a=validate_shards(reg,shards); b=validate_shards(reg,[shards[2],shards[0],shards[1]])
    for x,y in zip(a,b): pd.testing.assert_frame_equal(x,y)


def test_reducer_rejects_duplicate_missing_and_lineage_mismatch():
    reg=_registry(); shards=_shards(reg); bad=copy.deepcopy(shards); bad[1]['manifest']['trial_ids'][0]=bad[0]['manifest']['trial_ids'][0]
    with pytest.raises(ValueError): validate_shards(reg,bad)
    bad=copy.deepcopy(shards); bad.pop()
    with pytest.raises(ValueError): validate_shards(reg,bad)
    bad=copy.deepcopy(shards); bad[2]['manifest']['dataset_sha256']='e'*64
    with pytest.raises(ValueError): validate_shards(reg,bad)


def test_reducer_rejects_holdout_or_wrong_partition():
    reg=_registry(); bad=_shards(reg); bad[0]['manifest']['holdout_evaluated']=True
    with pytest.raises(ValueError): validate_shards(reg,bad)
    bad=_shards(reg); bad[0]['manifest']['trial_ids']=list(reversed(bad[0]['manifest']['trial_ids']))
    with pytest.raises(ValueError): validate_shards(reg,bad)
