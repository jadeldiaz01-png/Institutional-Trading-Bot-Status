#!/usr/bin/env python3
"""Deterministic evidence builder for Binance MCP promotion gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_SURFACE_RE = re.compile(
    r"binance\.(withdraw|transfer|margin|futures|options)(?:\.|\b)",
    re.IGNORECASE,
)
RISK_FIELDS = (
    "max_order_notional",
    "max_spread_bps",
    "max_slippage_bps",
    "max_concentration_pct",
    "max_daily_loss",
    "max_strategy_drawdown_pct",
    "max_simultaneous_positions",
    "min_cash_reserve",
)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_forbidden_capabilities(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    if not root.exists():
        raise ValueError(f"scan root missing: {root}")
    paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise ValueError(f"non-UTF8 Python source: {path}") from exc
        for lineno, line in enumerate(text.splitlines(), 1):
            match = FORBIDDEN_SURFACE_RE.search(line)
            if match:
                findings.append(
                    {
                        "path": str(path.relative_to(root) if root.is_dir() else path.name),
                        "line": lineno,
                        "marker": match.group(1).lower(),
                    }
                )
    return findings


def _risk_policy_complete(payload: dict[str, Any]) -> bool:
    return all(payload.get(field) is not None for field in RISK_FIELDS)


def build_evidence(
    *,
    source_sha: str,
    tests: str,
    security: str,
    forbidden_capabilities: str,
    permission_policy: str,
    reconciliation: str,
    risk_policy_path: Path,
    model_config_path: Path,
    runtime_policy_path: Path,
    sbom_ref: str,
    provenance_ref: str,
) -> dict[str, Any]:
    if SHA40_RE.fullmatch(source_sha) is None:
        raise ValueError("source_sha must be exact lowercase 40-hex")
    if not sbom_ref.strip() or not provenance_ref.strip():
        raise ValueError("supply-chain references are required")

    risk = _json(risk_policy_path)
    model = _json(model_config_path)
    runtime = _json(runtime_policy_path)

    blocking: list[str] = []
    gates = {
        "tests": tests,
        "security": security,
        "forbidden_capabilities": forbidden_capabilities,
        "permission_policy": permission_policy,
        "reconciliation": reconciliation,
    }
    for name, value in gates.items():
        if value != "PASS":
            blocking.append(name)

    if not _risk_policy_complete(risk):
        blocking.append("risk_policy_complete")
    if model.get("authority") != "ADVISORY_ONLY":
        blocking.append("model_authority")
    if runtime.get("execution_enabled_by_default") is not False:
        blocking.append("execution_default")
    if runtime.get("withdrawals_supported") is not False:
        blocking.append("withdrawals_forbidden")
    if runtime.get("transfers_supported") is not False:
        blocking.append("transfers_forbidden")

    blocking = list(dict.fromkeys(blocking))
    return {
        "schema_version": "1.0",
        "gate_id": "BINANCE_MCP_TESTNET_CERTIFICATION",
        "source_sha": source_sha,
        "decision": "BLOCKED" if blocking else "PASS",
        "blocking_gates": blocking,
        "gates": gates,
        "risk_policy_sha256": _sha256(risk_policy_path),
        "model_config_sha256": _sha256(model_config_path),
        "runtime_policy_sha256": _sha256(runtime_policy_path),
        "sbom_ref": sbom_ref,
        "provenance_ref": provenance_ref,
        "withdrawals_authorized": False,
        "transfers_authorized": False,
        "live_authorized": False,
    }


def emit_source_sbom(root: Path, output: Path) -> None:
    root = root.resolve()
    include_roots = [
        root / "src" / "binance_mcp",
        root / "config",
    ]
    extra = [root / "scripts" / "binance_mcp_cli.py", root / "scripts" / "certify_binance_mcp.py"]
    files: list[Path] = []
    for base in include_roots:
        if base.is_dir():
            files.extend(path for path in base.rglob("*") if path.is_file())
    files.extend(path for path in extra if path.is_file())
    unique = sorted(set(path.resolve() for path in files))
    components = []
    for path in unique:
        components.append(
            {
                "type": "file",
                "name": str(path.relative_to(root)),
                "hashes": [{"alg": "SHA-256", "content": _sha256(path)}],
            }
        )
    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "binance-mcp"}},
        "components": components,
    }
    output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan-forbidden")
    scan.add_argument("--root", type=Path, required=True)
    scan.add_argument("--output", type=Path, required=True)

    sbom = sub.add_parser("emit-sbom")
    sbom.add_argument("--root", type=Path, required=True)
    sbom.add_argument("--output", type=Path, required=True)

    certify = sub.add_parser("certify")
    certify.add_argument("--source-sha", required=True)
    certify.add_argument("--tests", required=True)
    certify.add_argument("--security", required=True)
    certify.add_argument("--forbidden-capabilities", required=True)
    certify.add_argument("--permission-policy", required=True)
    certify.add_argument("--reconciliation", required=True)
    certify.add_argument("--risk-policy", type=Path, required=True)
    certify.add_argument("--model-config", type=Path, required=True)
    certify.add_argument("--runtime-policy", type=Path, required=True)
    certify.add_argument("--sbom-ref", required=True)
    certify.add_argument("--provenance-ref", required=True)
    certify.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "scan-forbidden":
        findings = scan_forbidden_capabilities(args.root)
        args.output.write_text(
            json.dumps({"findings": findings}, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return 1 if findings else 0
    if args.command == "emit-sbom":
        emit_source_sbom(args.root, args.output)
        return 0

    evidence = build_evidence(
        source_sha=args.source_sha,
        tests=args.tests,
        security=args.security,
        forbidden_capabilities=args.forbidden_capabilities,
        permission_policy=args.permission_policy,
        reconciliation=args.reconciliation,
        risk_policy_path=args.risk_policy,
        model_config_path=args.model_config,
        runtime_policy_path=args.runtime_policy,
        sbom_ref=args.sbom_ref,
        provenance_ref=args.provenance_ref,
    )
    args.output.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0 if evidence["decision"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
