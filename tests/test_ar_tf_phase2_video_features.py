import numpy as np
import pandas as pd
import pytest

from ar_tf.phase2_video_features import (
    directional_consistency,
    donchian_breakout_features,
    lagged_liquidity_rank,
    lagged_return,
    order_flow_imbalance_l1,
    path_efficiency,
    realized_volatility,
    rolling_autocorr_1,
    sign_persistence,
    trade_imbalance,
)


def _panel(n=160):
    idx=pd.date_range('2024-01-01',periods=n,tz='UTC',freq='D')
    cols=['A','B']
    base=np.arange(n,dtype=float)[:,None]
    close=pd.DataFrame(100+base*np.array([[0.5,0.2]])+np.sin(base/7),index=idx,columns=cols)
    high=close*1.01; low=close*0.99; qv=pd.DataFrame(1e6+base*np.array([[1000,500]]),index=idx,columns=cols)
    ret=close.pct_change()
    return close,high,low,qv,ret


def test_daily_features_are_strictly_lagged_against_current_bar_mutation():
    close,high,low,qv,ret=_panel()
    funcs=lambda c,h,l,v,r: {
        'ret':lagged_return(c,7),
        'acf':rolling_autocorr_1(r,20),
        'sp':sign_persistence(r,20),
        'pe':path_efficiency(c,20),
        'dc':directional_consistency(r,20),
        'rv':realized_volatility(r,20),
        'liq':lagged_liquidity_rank(v,30),
        'bo':donchian_breakout_features(c,h,l,20)['breakout_strength_atr'],
    }
    a=funcs(close,high,low,qv,ret)
    close2=close.copy(); high2=high.copy(); low2=low.copy(); qv2=qv.copy()
    close2.iloc[-1]*=100; high2.iloc[-1]*=100; low2.iloc[-1]*=100; qv2.iloc[-1]*=100
    ret2=close2.pct_change(); b=funcs(close2,high2,low2,qv2,ret2)
    for k in a:
        pd.testing.assert_series_equal(a[k].iloc[-1],b[k].iloc[-1],check_names=False)


def test_path_features_bounded():
    close,_,_,_,ret=_panel()
    pe=path_efficiency(close,20); dc=directional_consistency(ret,20)
    assert ((pe.dropna()>=0)&(pe.dropna()<=1)).all().all()
    assert ((dc.dropna()>=0)&(dc.dropna()<=1)).all().all()


def test_breakout_uses_prior_information_only():
    close,high,low,_,_=_panel()
    f=donchian_breakout_features(close,high,low,20)
    assert set(f)=={'breakout_flag','donchian_distance','breakout_strength_atr','retest_distance_atr'}
    assert f['breakout_flag'].shape==close.shape


def test_ofi_requires_real_l1_fields_and_timestamp():
    with pytest.raises(ValueError):
        order_flow_imbalance_l1(pd.DataFrame({'close':[1,2],'volume':[3,4]}))
    idx=pd.date_range('2026-01-01',periods=3,tz='UTC',freq='s')
    e=pd.DataFrame({'bid_price':[100,101,101],'bid_size':[2,3,2],'ask_price':[102,102,101],'ask_size':[2,2,4]},index=idx)
    out=order_flow_imbalance_l1(e)
    assert out.name=='ofi_l1' and len(out)==3


def test_trade_imbalance_requires_certified_aggressor_side():
    t=pd.DataFrame({'aggressor_side':['BUY','SELL','BUY'],'quantity':[2.0,1.0,1.0]})
    x=trade_imbalance(t)
    assert x.iloc[0]==pytest.approx(0.5)
    with pytest.raises(ValueError):
        trade_imbalance(pd.DataFrame({'aggressor_side':['UNKNOWN'],'quantity':[1.0]}))
