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
    "infra/openbao/policies/trading-runtime.hcl",
    "schemas/order-intent.schema.json",
    "tests/test_p0_controls.py",
    ".github/workflows/p0-gates.yml",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def runtime_evidence(name: str) -> bool:
    return os.getenv(name, "false").lower() == "true"


def main() -> int:
    files = {}
    missing = []
    for rel in REQUIRED:
        path = ROOT / rel
        if not path.is_file():
            missing.append(rel)
        else:
            files[rel] = sha256_file(path)

    runtime = {
        "openbao_workload_identity_verified": runtime_evidence("EVIDENCE_OPENBAO_IDENTITY_VERIFIED"),
        "policy_engine_integration_verified": runtime_evidence("EVIDENCE_POLICY_ENGINE_VERIFIED"),
        "postgres_migration_applied_in_testnet": runtime_evidence("EVIDENCE_DB_MIGRATION_TESTNET"),
        "reconciliation_against_broker_testnet_verified": runtime_evidence("EVIDENCE_RECONCILIATION_TESTNET"),
        "kill_switch_testnet_verified": runtime_evidence("EVIDENCE_KILL_SWITCH_TESTNET"),
        "evidence_ledger_persistence_verified": runtime_evidence("EVIDENCE_LEDGER_TESTNET"),
    }

    all_runtime = all(runtime.values())
    verdict = "GO_TESTNET_CANDIDATE" if not missing and all_runtime else "NO_GO"
    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live_trading_enabled": False,
        "verdict": verdict,
        "missing_required_files": missing,
        "file_sha256": files,
        "runtime_evidence": runtime,
        "limitations": [
            "File presence alone never proves a gate.",
            "This manifest does not authorize LIVE_PILOT or LIMITED_LIVE.",
            "Cryptographic signing must be performed by CI workload identity using an external key; no signing key belongs in Git."
        ],
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if verdict != "NO_GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
