#!/usr/bin/env python3
"""Non-materializing index/cardinality diagnostics for CP03 training join."""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pandas as pd


def _scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def _index_summary(index: pd.Index) -> dict[str, Any]:
    counts = Counter(index.tolist())
    duplicate_rows = sum(n - 1 for n in counts.values())
    return {
        "type": type(index).__name__,
        "names": list(index.names),
        "nlevels": index.nlevels,
        "rows": len(index),
        "unique_keys": len(counts),
        "is_unique": index.is_unique,
        "duplicate_rows": duplicate_rows,
        "max_multiplicity": max(counts.values(), default=0),
    }


def _expected_inner_rows(left: pd.Index, right: pd.Index) -> dict[str, Any]:
    """Exact inner-join cardinality from key multiplicities; never materializes a join."""
    lc = Counter(left.tolist())
    rc = Counter(right.tolist())
    common = lc.keys() & rc.keys()
    expected = sum(lc[key] * rc[key] for key in common)
    contributors = sorted(
        ((lc[key] * rc[key], lc[key], rc[key], key) for key in common),
        reverse=True,
        key=lambda row: row[0],
    )[:10]
    return {
        "common_keys": len(common),
        "expected_inner_rows": expected,
        "top_multiplicity_products": [
            {
                "rows": product,
                "left_multiplicity": lmult,
                "right_multiplicity": rmult,
                "key": [_scalar(v) for v in key] if isinstance(key, tuple) else _scalar(key),
            }
            for product, lmult, rmult, key in contributors
        ],
    }


def emit_join_cardinality(left: pd.Index, right: pd.Index) -> None:
    payload = {
        "left": _index_summary(left),
        "right": _index_summary(right),
        "alignment": {
            "same_nlevels": left.nlevels == right.nlevels,
            "same_names": list(left.names) == list(right.names),
        },
        "cardinality": _expected_inner_rows(left, right),
    }
    print("JOIN_CARDINALITY " + json.dumps(payload, separators=(",", ":")), flush=True)
