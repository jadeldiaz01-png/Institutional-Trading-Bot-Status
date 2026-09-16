from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    created_at: str
    dataset_sha256: str
    code_ref: str
    parameters: dict[str, Any]
    split: dict[str, Any]
    metrics: dict[str, Any]
    status: str


def stable_experiment_id(dataset_sha256: str, code_ref: str, parameters: dict, split: dict) -> str:
    payload = json.dumps(
        {"dataset_sha256": dataset_sha256, "code_ref": code_ref, "parameters": parameters, "split": split},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:24]


def make_record(dataset_sha256: str, code_ref: str, parameters: dict, split: dict, metrics: dict, status: str) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=stable_experiment_id(dataset_sha256, code_ref, parameters, split),
        created_at=datetime.now(timezone.utc).isoformat(),
        dataset_sha256=dataset_sha256,
        code_ref=code_ref,
        parameters=parameters,
        split=split,
        metrics=metrics,
        status=status,
    )


class JsonlExperimentRegistry:
    """Append-only experiment ledger. Existing experiment ids cannot be silently replaced."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        ids = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(json.loads(line)["experiment_id"])
        return ids

    def append(self, record: ExperimentRecord) -> None:
        if record.experiment_id in self._ids():
            raise ValueError(f"experiment already registered: {record.experiment_id}")
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), sort_keys=True) + "\n")
