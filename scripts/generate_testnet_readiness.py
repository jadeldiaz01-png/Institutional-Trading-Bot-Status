#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "migrations/0001_p0_core.sql",
    "policy/order_intent.rego",
    "infra/openbao/config/openbao.hcl",
    "infra/openbao/bootstrap-testnet.sh",
    "src/institutional_trading/repository.py",
    "src/institutional_trading/order_service.py",
    "src/institutional_trading/reconciler_worker.py",
    "src/institutional_trading/binance_testnet.py",
    "src/institutional_trading/persistent_evidence.py",
    "tests/test_p0_b_failure_modes.py",
    "tests/test_p0_b_integration.py",
    ".github/workflows/p0b-testnet-integration.yml",
]


def truth(name: str) -> bool:
    return os.getenv(name, "false").lower() == "true"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    files = {}
    missing = []
    for rel in REQUIRED:
        path = ROOT / rel
        if path.is_file():
            files[rel] = digest(path)
        else:
            missing.append(rel)

    evidence = {
        "postgres_schema_testnet_verified": truth("EVIDENCE_POSTGRES_TESTNET"),
        "opa_runtime_policy_verified": truth("EVIDENCE_OPA_TESTNET"),
        "openbao_health_verified": truth("EVIDENCE_OPENBAO_HEALTH"),
        "openbao_workload_identity_verified": truth("EVIDENCE_OPENBAO_WORKLOAD_IDENTITY"),
        "adapter_authenticated_spot_testnet_verified": truth("EVIDENCE_ADAPTER_AUTH_TESTNET"),
        "unknown_reconciliation_verified": truth("EVIDENCE_RECONCILIATION_TESTNET"),
        "kill_switch_e2e_verified": truth("EVIDENCE_KILL_SWITCH_TESTNET"),
        "evidence_ledger_persistence_verified": truth("EVIDENCE_LEDGER_TESTNET"),
        "crash_timeout_duplication_suite_verified": truth("EVIDENCE_FAILURE_SUITE_TESTNET"),
        "human_gate_approved": truth("EVIDENCE_HUMAN_TESTNET_APPROVAL"),
    }
    ready = not missing and all(evidence.values())
    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stage": "TESTNET_READY",
        "decision": "GO" if ready else "NO_GO",
        "live_trading_enabled": False,
        "required_files": files,
        "missing_files": missing,
        "evidence": evidence,
        "blocking_evidence": [k for k, v in evidence.items() if not v],
    }
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
