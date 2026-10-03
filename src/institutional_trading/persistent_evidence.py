from __future__ import annotations

from .evidence import EvidenceEvent
from .repository import PostgresStore


class PersistentEvidenceLedger:
    def __init__(self, store: PostgresStore) -> None:
        self._store = store

    def append(self, *, actor: str, event_type: str, subject_ref: str, payload: dict) -> EvidenceEvent:
        previous = self._store.latest_evidence_hash()
        event = EvidenceEvent(
            actor=actor,
            event_type=event_type,
            subject_ref=subject_ref,
            payload=payload,
            previous_hash=previous,
        ).seal()
        if event.event_hash is None:
            raise RuntimeError("failed to seal evidence event")
        self._store.append_evidence(
            event.event_id,
            event.actor,
            event.event_type,
            event.subject_ref,
            event.payload,
            event.previous_hash,
            event.event_hash,
        )
        return event
