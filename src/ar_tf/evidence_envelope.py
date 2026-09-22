from __future__ import annotations
import hashlib, json
from dataclasses import dataclass, field
from typing import Any, Mapping

SCHEMA_VERSION = "1.0.0"

def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()

@dataclass(frozen=True)
class EvidenceEnvelope:
    experiment_id: str
    generation: str
    source_commit_sha: str
    dataset_sha256: str
    registry_sha256: str
    folds_sha256: str
    scientific_config_sha256: str
    environment_digest: str
    inputs: Mapping[str, str]
    outputs: Mapping[str, str]
    gates: Mapping[str, Any]
    parent_evidence_sha256: str | None = None
    holdout_opened: bool = False
    paper_authorized: bool = False
    testnet_authorized: bool = False
    live_authorized: bool = False
    schema_version: str = field(default=SCHEMA_VERSION)

    def __post_init__(self) -> None:
        required = [self.experiment_id,self.generation,self.source_commit_sha,self.dataset_sha256,
                    self.registry_sha256,self.folds_sha256,self.scientific_config_sha256,self.environment_digest]
        if any(not x for x in required): raise ValueError("required evidence identity missing")
        if self.holdout_opened or self.paper_authorized or self.testnet_authorized or self.live_authorized:
            raise ValueError("selection-stage evidence cannot authorize holdout/paper/testnet/live")
        for group in (self.inputs,self.outputs):
            for name,digest in group.items():
                if not name or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                    raise ValueError(f"invalid sha256 digest for {name}")

    def payload(self) -> dict[str, Any]:
        return {k:v for k,v in self.__dict__.items()}

    @property
    def evidence_sha256(self) -> str:
        return sha256_json(self.payload())
