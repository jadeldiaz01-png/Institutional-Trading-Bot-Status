from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

S3_LIST_URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
VISION_BASE = "https://data.binance.vision"
MONTHLY_PREFIX = "data/spot/monthly/klines/"
KEY_RE = re.compile(
    r"^data/spot/monthly/klines/(?P<symbol>[A-Z0-9]+)/1d/(?P=symbol)-1d-(?P<year>\d{4})-(?P<month>\d{2})\.zip$"
)


@dataclass(frozen=True)
class ArchiveObservation:
    symbol: str
    month: str
    key: str
    source_url: str


@dataclass(frozen=True)
class LifecycleCandidate:
    symbol: str
    first_archive_month: str
    last_archive_month: str
    observation_count: int
    evidence_class: str = "BINANCE_VISION_ARCHIVE_PRESENCE"
    verification_status: str = "BOUNDARY_CANDIDATE_ONLY"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_sha256(obj: object) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _sha256_bytes(raw)


def list_binance_vision_keys(prefix: str = MONTHLY_PREFIX, *, max_pages: int | None = None, timeout: int = 60) -> list[str]:
    """List Binance Vision objects using the public S3 ListObjectsV2 API.

    The result is evidence discovery only. Presence/absence of an archive must not
    be treated by itself as an exact listing or delisting timestamp.
    """
    token: str | None = None
    keys: list[str] = []
    page = 0
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        url = f"{S3_LIST_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "AR-TF-evidence/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read()
        root = ET.fromstring(payload)
        ns = {"s3": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
        key_path = "s3:Contents/s3:Key" if ns else "Contents/Key"
        for node in root.findall(key_path, ns):
            if node.text:
                keys.append(node.text)
        page += 1
        truncated_path = "s3:IsTruncated" if ns else "IsTruncated"
        truncated = root.findtext(truncated_path, default="false", namespaces=ns).lower() == "true"
        if not truncated or (max_pages is not None and page >= max_pages):
            break
        token_path = "s3:NextContinuationToken" if ns else "NextContinuationToken"
        token = root.findtext(token_path, namespaces=ns)
        if not token:
            raise RuntimeError("Binance Vision pagination truncated without continuation token")
    return keys


def extract_usdt_daily_observations(keys: list[str]) -> list[ArchiveObservation]:
    observations: list[ArchiveObservation] = []
    for key in keys:
        match = KEY_RE.match(key)
        if not match:
            continue
        symbol = match.group("symbol")
        if not symbol.endswith("USDT"):
            continue
        month = f"{match.group('year')}-{match.group('month')}"
        observations.append(
            ArchiveObservation(
                symbol=symbol,
                month=month,
                key=key,
                source_url=f"{VISION_BASE}/{key}",
            )
        )
    observations.sort(key=lambda x: (x.symbol, x.month, x.key))
    return observations


def lifecycle_candidates(observations: list[ArchiveObservation]) -> list[LifecycleCandidate]:
    by_symbol: dict[str, list[ArchiveObservation]] = {}
    for obs in observations:
        by_symbol.setdefault(obs.symbol, []).append(obs)
    result: list[LifecycleCandidate] = []
    for symbol, rows in sorted(by_symbol.items()):
        months = sorted({r.month for r in rows})
        result.append(
            LifecycleCandidate(
                symbol=symbol,
                first_archive_month=months[0],
                last_archive_month=months[-1],
                observation_count=len(months),
            )
        )
    return result


def build_provenance(observations: list[ArchiveObservation], candidates: list[LifecycleCandidate]) -> dict:
    obs_payload = [asdict(x) for x in observations]
    candidate_payload = [asdict(x) for x in candidates]
    return {
        "schema_version": "1.0.0",
        "dataset_id": "binance-spot-usdt-lifecycle-evidence-v1",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source": VISION_BASE,
        "source_method": "public_s3_listobjects_v2",
        "interval": "1d",
        "quote_asset": "USDT",
        "observation_count": len(obs_payload),
        "symbol_count": len(candidate_payload),
        "observations_sha256": canonical_sha256(obs_payload),
        "candidates_sha256": canonical_sha256(candidate_payload),
        "verification_policy": {
            "archive_presence_is_exact_listing_time": False,
            "archive_absence_is_exact_delisting_time": False,
            "requires_boundary_kline_verification": True,
            "requires_gap_check": True,
            "requires_official_announcement_when_available": True,
            "unresolved_boundary_blocks_certification": True,
        },
        "certification_state": "EVIDENCE_DISCOVERY_ONLY",
    }


def validate_verified_lifecycle(rows: pd.DataFrame) -> list[str]:
    required = {
        "symbol", "listed_at", "delisted_at", "listing_evidence_url",
        "delisting_evidence_url", "listing_status", "delisting_status",
    }
    missing = required - set(rows.columns)
    if missing:
        return [f"MISSING_COLUMNS:{','.join(sorted(missing))}"]
    reasons: list[str] = []
    for i, row in rows.iterrows():
        symbol = str(row["symbol"])
        if row["listing_status"] != "VERIFIED":
            reasons.append(f"{symbol}:LISTING_BOUNDARY_UNVERIFIED")
        if pd.notna(row["delisted_at"]) and row["delisting_status"] != "VERIFIED":
            reasons.append(f"{symbol}:DELISTING_BOUNDARY_UNVERIFIED")
        if not str(row["listing_evidence_url"]).startswith("https://"):
            reasons.append(f"{symbol}:INVALID_LISTING_EVIDENCE_URL")
        if pd.notna(row["delisted_at"]) and not str(row["delisting_evidence_url"]).startswith("https://"):
            reasons.append(f"{symbol}:INVALID_DELISTING_EVIDENCE_URL")
        try:
            listed = pd.Timestamp(row["listed_at"])
            delisted = pd.Timestamp(row["delisted_at"]) if pd.notna(row["delisted_at"]) else None
            if delisted is not None and delisted <= listed:
                reasons.append(f"{symbol}:INVALID_LIFECYCLE_ORDER")
        except Exception:
            reasons.append(f"{symbol}:INVALID_TIMESTAMP")
    return sorted(set(reasons))


def write_discovery_bundle(output_dir: str | Path, keys: list[str]) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    observations = extract_usdt_daily_observations(keys)
    candidates = lifecycle_candidates(observations)
    provenance = build_provenance(observations, candidates)
    (out / "archive-observations.json").write_text(
        json.dumps([asdict(x) for x in observations], indent=2, sort_keys=True), encoding="utf-8"
    )
    (out / "lifecycle-candidates.json").write_text(
        json.dumps([asdict(x) for x in candidates], indent=2, sort_keys=True), encoding="utf-8"
    )
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8")
    return provenance
