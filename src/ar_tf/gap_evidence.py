from __future__ import annotations

import json
from pathlib import Path

from .evidence_acquisition import canonical_sha256


def load_registry(path: str | Path) -> dict:
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    if registry.get("schema_version") != "1.0.0":
        raise ValueError("unsupported market event registry schema")
    if registry.get("policy", {}).get("imputation_allowed") is not False:
        raise ValueError("market event registry must forbid imputation")
    return registry


def classify_gap_report(gap_report: dict, registry: dict) -> dict:
    """Classify observed calendar gaps against explicit authoritative evidence.

    Only exact market_id/previous/current matches are eligible. A same-identity
    trading halt can be resolved as an expected no-trading interval. Any token
    swap, redenomination, fork, ticker reuse or unknown event remains blocking.
    """
    index = {
        (e["market_id"], e["previous"], e["current"]): e
        for e in registry.get("events", [])
    }
    classified: list[dict] = []
    for gap in gap_report.get("events", []):
        key = (gap.get("market_id"), gap.get("previous"), gap.get("current"))
        evidence = index.get(key)
        if evidence is None:
            classified.append({
                **gap,
                "state": "UNRESOLVED",
                "classification": "UNKNOWN_EVENT",
                "resolution": "FAIL_CLOSED",
                "requires_episode_split": False,
            })
            continue
        if evidence.get("source_authority") != "BINANCE_OFFICIAL":
            classified.append({
                **gap,
                "state": "UNRESOLVED",
                "classification": "NON_AUTHORITATIVE_EVIDENCE",
                "resolution": "FAIL_CLOSED",
                "requires_episode_split": bool(evidence.get("requires_episode_split")),
                "source": evidence.get("source"),
            })
            continue
        if evidence.get("requires_episode_split"):
            classified.append({
                **gap,
                "state": "UNRESOLVED",
                "classification": evidence["classification"],
                "resolution": "SPLIT_LIFECYCLE_EPISODE",
                "requires_episode_split": True,
                "source": evidence["source"],
                "source_authority": evidence["source_authority"],
                "evidence": evidence["evidence"],
            })
            continue
        if evidence.get("classification") == "SAME_IDENTITY_TRADING_HALT":
            classified.append({
                **gap,
                "state": "RESOLVED",
                "classification": evidence["classification"],
                "resolution": "EXPECTED_NO_TRADING_INTERVAL",
                "requires_episode_split": False,
                "source": evidence["source"],
                "source_authority": evidence["source_authority"],
                "evidence": evidence["evidence"],
            })
            continue
        classified.append({
            **gap,
            "state": "UNRESOLVED",
            "classification": evidence.get("classification", "UNSUPPORTED_CLASSIFICATION"),
            "resolution": "FAIL_CLOSED",
            "requires_episode_split": bool(evidence.get("requires_episode_split")),
            "source": evidence.get("source"),
        })

    unresolved = [x for x in classified if x["state"] != "RESOLVED"]
    identity_breaks = [x for x in unresolved if x.get("requires_episode_split")]
    resolved = [x for x in classified if x["state"] == "RESOLVED"]
    report = {
        "schema_version": "1.0.0",
        "policy": registry["policy"],
        "registry_sha256": canonical_sha256(registry),
        "observed_gap_count": len(classified),
        "resolved_gap_count": len(resolved),
        "unresolved_gap_count": len(unresolved),
        "identity_break_count": len(identity_breaks),
        "all_gaps_resolved": len(unresolved) == 0,
        "events": classified,
    }
    report["report_sha256"] = canonical_sha256({k: v for k, v in report.items() if k != "report_sha256"})
    return report
