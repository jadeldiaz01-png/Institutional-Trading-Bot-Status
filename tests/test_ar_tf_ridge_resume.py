import copy
import pandas as pd
import pytest
from ar_tf.ridge_resume import RIDGE_TRIAL_COUNT, trial_at, validate_trials


def _registry():
    return {'trials':[{'trial_id':f'ridge-{i:02d}','family':'ridge','params':{},'seed':i} for i in range(27)]}


def _fold_inventory(tid):
    return [
        {
            'trial_id':tid,
            'fold_id':fid,
            'manifest_sha256':f'{fid + 1:064x}',
            'payload_sha256':f'{fid + 101:064x}',
        }
        for fid in range(12)
    ]


def _results(reg):
    idx=pd.date_range('2026-01-01',periods=3,tz='UTC'); out=[]
    for i in range(27):
        t=trial_at(reg,i); f=pd.DataFrame({t['trial_id']:[0.0,0.01,0.0]},index=idx)
        inventory=_fold_inventory(t['trial_id'])
        out.append({'manifest':{
            'schema_version':'2.2.0','stage':'RIDGE_SINGLE_TRIAL','execution_status':'COMPLETED',
            'index':i,'trial_id':t['trial_id'],'seed':t['seed'],'failure':None,
            'parent_checkpoint_sha256':'a'*64,'dataset_sha256':'b'*64,'registry_sha256':'c'*64,
            'folds_sha256':'d'*64,'config_sha256':'e'*64,'source_commit_sha':'1'*40,
            'runtime_fingerprint_sha256':'f'*64,'fold_checkpoint_count':12,'fold_inventory':inventory,
            'holdout_opened':False,'holdout_evaluated':False,
        },'base':f,'stressed':f.copy(),'severe':f.copy()})
    return out


def test_registry_exactly_27():
    r=_registry(); assert RIDGE_TRIAL_COUNT==27
    assert [trial_at(r,i)['trial_id'] for i in range(27)]==[f'ridge-{i:02d}' for i in range(27)]


def test_partition_is_9_9_9():
    assert [len(range(a,b)) for a,b in ((0,9),(9,18),(18,27))]==[9,9,9]


def test_reducer_order_invariant_exactly_once_and_324_folds():
    r=_registry(); a=validate_trials(r,_results(r)); b=validate_trials(r,list(reversed(_results(r))))
    for x,y in zip(a[:3],b[:3]):
        pd.testing.assert_frame_equal(x,y)


def test_rejects_duplicate_missing_unknown_lineage():
    r=_registry()
    bad=copy.deepcopy(_results(r)); bad[1]['manifest']['trial_id']=bad[0]['manifest']['trial_id']; pytest.raises(ValueError,validate_trials,r,bad)
    bad=copy.deepcopy(_results(r)); bad.pop(); pytest.raises(ValueError,validate_trials,r,bad)
    bad=copy.deepcopy(_results(r)); bad[2]['manifest']['trial_id']='x'; pytest.raises(ValueError,validate_trials,r,bad)
    bad=copy.deepcopy(_results(r)); bad[2]['manifest']['dataset_sha256']='9'*64; pytest.raises(ValueError,validate_trials,r,bad)
    bad=copy.deepcopy(_results(r)); bad[2]['manifest']['runtime_fingerprint_sha256']='9'*64; pytest.raises(ValueError,validate_trials,r,bad)


def test_rejects_seed_index_config_holdout_incomplete_or_fold_gap():
    r=_registry()
    for field,value in [('seed',999),('index',4),('config_sha256','9'*64),('holdout_evaluated',True),('execution_status','INTERRUPTED_INFRASTRUCTURE')]:
        bad=copy.deepcopy(_results(r)); bad[3]['manifest'][field]=value; pytest.raises(ValueError,validate_trials,r,bad)
    bad=copy.deepcopy(_results(r)); bad[3]['manifest']['fold_inventory'].pop(); bad[3]['manifest']['fold_checkpoint_count']=11
    with pytest.raises(ValueError,match='12-fold'):
        validate_trials(r,bad)
    bad=copy.deepcopy(_results(r)); bad[3]['manifest']['fold_inventory'][1]['fold_id']=0
    with pytest.raises(ValueError,match='duplicate'):
        validate_trials(r,bad)


def test_exception_zero_failure_is_retained_by_reducer_contract():
    r=_registry(); x=_results(r); x[4]['manifest']['failure']={'trial_id':'ridge-04','error':'RuntimeError','message':'x'}
    b,s,v,failures=validate_trials(r,x)
    assert len(failures)==1 and failures[0]['trial_id']=='ridge-04'
    assert b.shape[1]==s.shape[1]==v.shape[1]==27
