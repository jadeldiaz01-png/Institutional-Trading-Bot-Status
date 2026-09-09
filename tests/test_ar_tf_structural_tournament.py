import numpy as np
import pandas as pd

from ar_tf.g4_g13_contract import evaluate_g4_g13
from ar_tf.research_panel import ResearchPanel
from ar_tf.structural_trials import build_structural_weights


def _panel(n=400):
    idx=pd.date_range('2023-01-01',periods=n,freq='D',tz='UTC')
    cols=['AAAUSDT__E01','BBBUSDT__E01','CCCUSDT__E01']
    base=np.arange(n,dtype=float)[:,None]
    close=pd.DataFrame(100.0+base*np.array([[0.10,0.05,0.02]])+np.sin(base/11.0),index=idx,columns=cols)
    high=close*1.01; low=close*0.99
    qv=pd.DataFrame(20_000_000.0,index=idx,columns=cols)
    trades=pd.DataFrame(10_000.0,index=idx,columns=cols)
    return ResearchPanel(close=close,high=high,low=low,quote_volume=qv,trade_count=trades,research_end=idx[-1],holdout_start=idx[-1]+pd.Timedelta(days=1))


def test_structural_engines_are_long_cash_and_bounded():
    p=_panel()
    cases=[
        ('time_series_momentum',{'lookback_days':30,'rebalance_days':7,'volatility_targeting':True}),
        ('donchian_breakout',{'lookback_days':20,'rebalance_days':7}),
        ('cross_sectional_momentum',{'formation_days':30,'top_fraction':0.2,'universe_size':3}),
        ('lagged_dispersion_momentum',{'momentum_days':30,'dispersion_window':14,'risk_off_z':1.5}),
        ('price_path_continuity',{'formation_days':14,'continuity_quantile':0.7}),
        ('volatility_conditioned_reversal',{'formation_days':28,'volatility_quantile':0.7,'skip_days':0}),
    ]
    for family,params in cases:
        w=build_structural_weights(p,family,params)
        assert (w>=-1e-12).all(axis=None)
        assert (w.sum(axis=1)<=1.000001).all()
        assert (w.max(axis=1)<=0.150001).all()


def test_contract_uses_explicit_gate_results_not_placeholder_evidence():
    g4={'decision':'PASS','holdout_values_evaluated':False,'holdout_opened':False}
    g5={'decision':'PASS','state':'PREREGISTERED_NOT_EXECUTED','trial_count':407,'holdout_evaluated':False,
        'source_commit_sha':'c'*40,'dataset_sha256':'a'*64,'lifecycle_sha256':'b'*64,
        'strategy_config_sha256':'d'*64,'fold_definition_sha256':'e'*64,'trial_registry_sha256':'f'*64}
    tournament={'holdout_evaluated':False,'holdout_opened':False,'evidence':{'G8':'PENDING'},
                'gate_results':{g:{'status':'BLOCKED','reasons':['NOT_YET_CERTIFIED']} for g in ('G6','G7','G8','G9','G10','G11','G12','G13')}}
    c=evaluate_g4_g13(bias_audit=g4,preregistration=g5,tournament=tournament)
    assert c['gates']['G8']['status']=='BLOCKED'
    assert c['decision']=='NO_EDGE_VERIFIED'
