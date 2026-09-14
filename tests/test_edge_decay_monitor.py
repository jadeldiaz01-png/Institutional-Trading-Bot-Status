import pandas as pd
from ar_tf.edge_decay import edge_health


def test_monitor_is_fail_closed_with_short_history():
    idx = pd.date_range('2026-01-01', periods=20, freq='D', tz='UTC')
    r = pd.Series([0.001] * 20, index=idx)
    c = pd.Series([0.0001] * 20, index=idx)
    t = pd.Series([0.1] * 20, index=idx)
    result = edge_health(r, c, t)
    assert result['state'] == 'INSUFFICIENT_FORWARD_EVIDENCE'
    assert result['automatic_promotion'] is False
