import pandas as pd

from ar_tf.semantic_integrity import semantic_anomalies


def test_semantic_anomalies_detect_high_invariant_and_negative_activity():
    frame=pd.DataFrame([
        {'timestamp':'2020-01-01T00:00:00Z','open':1.0,'high':1.1,'low':0.9,'close':1.05,'volume':10,'quote_volume':10,'trade_count':5},
        {'timestamp':'2020-01-02T00:00:00Z','open':1.0,'high':1.01,'low':0.9,'close':1.05,'volume':10,'quote_volume':10,'trade_count':5},
        {'timestamp':'2020-01-03T00:00:00Z','open':1.0,'high':1.1,'low':0.9,'close':1.05,'volume':-1,'quote_volume':10,'trade_count':5},
    ])
    kinds=[x['type'] for x in semantic_anomalies(frame)]
    assert 'HIGH_INVARIANT' in kinds
    assert 'NEGATIVE_ACTIVITY' in kinds


def test_valid_ohlcv_has_no_semantic_anomalies():
    frame=pd.DataFrame([
        {'timestamp':'2020-01-01T00:00:00Z','open':1.0,'high':1.1,'low':0.9,'close':1.05,'volume':10,'quote_volume':10,'trade_count':5},
    ])
    assert semantic_anomalies(frame)==[]
