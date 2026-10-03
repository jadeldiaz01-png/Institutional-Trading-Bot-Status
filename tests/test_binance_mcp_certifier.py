from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "certify_binance_mcp",
    ROOT / "scripts/certify_binance_mcp.py",
)
assert SPEC is not None and SPEC.loader is not None
CERT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CERT)

SHA = "a" * 40


class BinanceMCPCertifierTests(unittest.TestCase):
    def files(self, root: Path, *, complete_risk=True):
        risk = {
            "schema_version": "1.0",
            "max_order_notional": "100" if complete_risk else None,
            "max_spread_bps": "20" if complete_risk else None,
            "max_slippage_bps": "25" if complete_risk else None,
            "max_concentration_pct": "20" if complete_risk else None,
            "max_daily_loss": "50" if complete_risk else None,
            "max_strategy_drawdown_pct": "10" if complete_risk else None,
            "max_simultaneous_positions": 2 if complete_risk else None,
            "min_cash_reserve": "100" if complete_risk else None,
        }
        model = {
            "schema_version": "1.0",
            "provider": "nvidia",
            "model": "nvidia/nemotron-3-ultra-550b-a55b",
            "authority": "ADVISORY_ONLY",
        }
        runtime = {
            "schema_version": "1.0",
            "execution_enabled_by_default": False,
            "withdrawals_supported": False,
            "transfers_supported": False,
        }
        paths = {}
        for name, payload in (("risk", risk), ("model", model), ("runtime", runtime)):
            path = root / f"{name}.json"
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            paths[name] = path
        return paths

    def base_inputs(self, paths):
        return dict(
            source_sha=SHA,
            tests="PASS",
            security="PASS",
            forbidden_capabilities="PASS",
            permission_policy="PASS",
            reconciliation="PASS",
            risk_policy_path=paths["risk"],
            model_config_path=paths["model"],
            runtime_policy_path=paths["runtime"],
            sbom_ref="artifact:binance-mcp-sbom.cdx.json",
            provenance_ref="github-actions:run:123",
        )

    def test_all_required_evidence_passes_and_exact_hashes_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.files(Path(tmp), complete_risk=True)
            evidence = CERT.build_evidence(**self.base_inputs(paths))
        self.assertEqual(evidence["decision"], "PASS")
        self.assertEqual(evidence["source_sha"], SHA)
        self.assertRegex(evidence["risk_policy_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(evidence["model_config_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(evidence["runtime_policy_sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(evidence["withdrawals_authorized"])
        self.assertFalse(evidence["transfers_authorized"])
        self.assertFalse(evidence["live_authorized"])

    def test_any_missing_or_failed_gate_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.files(Path(tmp), complete_risk=True)
            base = self.base_inputs(paths)
            for field in (
                "tests",
                "security",
                "forbidden_capabilities",
                "permission_policy",
                "reconciliation",
            ):
                with self.subTest(field=field):
                    values = dict(base)
                    values[field] = "FAIL"
                    evidence = CERT.build_evidence(**values)
                    self.assertEqual(evidence["decision"], "BLOCKED")
                    self.assertIn(field, evidence["blocking_gates"])

    def test_incomplete_risk_policy_is_blocked_not_defaulted(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.files(Path(tmp), complete_risk=False)
            evidence = CERT.build_evidence(**self.base_inputs(paths))
        self.assertEqual(evidence["decision"], "BLOCKED")
        self.assertIn("risk_policy_complete", evidence["blocking_gates"])

    def test_invalid_source_sha_or_missing_supply_chain_refs_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.files(Path(tmp), complete_risk=True)
            values = self.base_inputs(paths)
            values["source_sha"] = "bad"
            with self.assertRaises(ValueError):
                CERT.build_evidence(**values)

            values = self.base_inputs(paths)
            values["sbom_ref"] = ""
            with self.assertRaises(ValueError):
                CERT.build_evidence(**values)

    def test_forbidden_capability_scan_detects_withdrawal_or_transfer_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "safe.py").write_text('TOOL = "binance.market.ticker"\n', encoding="utf-8")
            self.assertEqual(CERT.scan_forbidden_capabilities(root), [])
            (root / "bad.py").write_text('TOOL = "binance.withdraw.create"\n', encoding="utf-8")
            findings = CERT.scan_forbidden_capabilities(root)
            self.assertTrue(findings)
            self.assertIn("withdraw", findings[0]["marker"])


if __name__ == "__main__":
    unittest.main()
