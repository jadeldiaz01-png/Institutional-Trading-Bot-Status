from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EvidenceEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str
    event_type: str
    subject_ref: str
    payload: dict
    previous_hash: str | None = None
    event_hash: str | None = None

    def seal(self) -> "EvidenceEvent":
        canonical = json.dumps(
            {
                "event_id": str(self.event_id),
                "occurred_at": self.occurred_at.isoformat(),
                "actor": self.actor,
                "event_type": self.event_type,
                "subject_ref": self.subject_ref,
                "payload": self.payload,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return self.model_copy(update={"event_hash": sha256(canonical.encode()).hexdigest()})

    def verify(self) -> bool:
        if not self.event_hash:
            return False
        expected = self.model_copy(update={"event_hash": None}).seal().event_hash
        return expected == self.event_hash
