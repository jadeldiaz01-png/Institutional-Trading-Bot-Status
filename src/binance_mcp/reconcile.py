"""Reconcile ambiguous Binance order submissions without blind retry."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from .contracts import OrderRecord, OrderState
from .oms import InvalidTransition, OMS


class Reconciler:
    def __init__(self, oms: OMS):
        self._oms = oms

    def reconcile_unknown(
        self,
        order: OrderRecord,
        *,
        exchange_lookup: Callable[[str], dict[str, Any] | None],
        confirmed_absent: bool,
    ) -> OrderRecord:
        current = self._oms.store.get(order.order_id)
        if current.state != OrderState.UNKNOWN:
            raise InvalidTransition("only UNKNOWN orders may use unknown reconciliation")

        result = exchange_lookup(current.client_order_id)
        if result is None and not confirmed_absent:
            return current

        if result is None:
            reconciliation_id = f"confirmed-absent:{current.client_order_id}"
        else:
            canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
            reconciliation_id = f"exchange:{current.client_order_id}:{digest}"

        return self._oms.transition(
            current.order_id,
            OrderState.RECONCILED,
            evidence={"reconciliation_id": reconciliation_id},
        )
