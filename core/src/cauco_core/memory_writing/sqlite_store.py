from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from cauco_core.memory_writing.models import (
    MemoryWriteProposal,
    MemoryWriteProposalState,
    StoredMemoryWriteProposal,
)
from cauco_core.memory_writing.store import (
    MemoryWriteProposalStore,
    _ProposalRecord,
)
from cauco_core.persistence import SQLiteDatabase


class SQLiteMemoryWriteProposalStore(MemoryWriteProposalStore):
    """Persistent memory-write proposal store backed by local SQLite.

    The original in-memory store remains responsible for lifecycle and
    idempotency behavior. This subclass restores proposals at startup and
    persists every accepted state transition.

    Restart policy:
    - pending, unexpired proposals remain pending;
    - pending, expired proposals become expired;
    - applied proposals remain applied;
    - expired proposals remain expired.
    """

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        ttl: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.database.initialize()
        super().__init__(ttl=ttl, clock=clock)
        self._restore()

    def put(self, proposal: MemoryWriteProposal) -> StoredMemoryWriteProposal:
        with self._lock:
            previous = self._records.get(proposal.proposal_id)
            previous_state = previous.state if previous is not None else None

            stored = super().put(proposal)
            current = self._records[proposal.proposal_id]

            if previous is None or current is not previous or current.state is not previous_state:
                self._persist_record(current)

            return stored

    def get(self, proposal_id: str) -> StoredMemoryWriteProposal:
        with self._lock:
            record = self._records.get(proposal_id)
            previous_state = record.state if record is not None else None

            stored = super().get(proposal_id)
            current = self._records[proposal_id]

            if previous_state is not None and current.state is not previous_state:
                self._persist_record(current)

            return stored

    def get_pending(self, proposal_id: str) -> StoredMemoryWriteProposal:
        with self._lock:
            record = self._records.get(proposal_id)
            previous_state = record.state if record is not None else None

            try:
                return super().get_pending(proposal_id)
            finally:
                current = self._records.get(proposal_id)
                if (
                    current is not None
                    and previous_state is not None
                    and current.state is not previous_state
                ):
                    self._persist_record(current)

    def mark_applied(
        self,
        proposal_id: str,
        applied_at: datetime,
    ) -> StoredMemoryWriteProposal:
        with self._lock:
            stored = super().mark_applied(proposal_id, applied_at)
            self._persist_record(self._records[proposal_id])
            return stored

    def _restore(self) -> None:
        now = self.clock()
        changed: list[_ProposalRecord] = []

        with self._lock, self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM memory_write_proposals
                ORDER BY created_at ASC, proposal_id ASC
                """
            ).fetchall()

            records: dict[str, _ProposalRecord] = {}

            for row in rows:
                proposal = MemoryWriteProposal.model_validate_json(str(row["proposal_json"]))
                stored_state = MemoryWriteProposalState(str(row["state"]))
                state = stored_state
                expires_at = _datetime(str(row["expires_at"]))

                if stored_state is MemoryWriteProposalState.PENDING and now >= expires_at:
                    state = MemoryWriteProposalState.EXPIRED

                record = _ProposalRecord(
                    proposal=proposal,
                    state=state,
                    created_at=_datetime(str(row["created_at"])),
                    expires_at=expires_at,
                    applied_at=_optional_datetime(row["applied_at"]),
                )
                records[proposal.proposal_id] = record

                if state is not stored_state:
                    changed.append(record)

            self._records = records

        for record in changed:
            self._persist_record(record)

    def _persist_record(self, record: _ProposalRecord) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO memory_write_proposals (
                    proposal_id,
                    proposal_json,
                    state,
                    created_at,
                    expires_at,
                    applied_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    proposal_json = excluded.proposal_json,
                    state = excluded.state,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    applied_at = excluded.applied_at
                """,
                (
                    record.proposal.proposal_id,
                    record.proposal.model_dump_json(),
                    record.state.value,
                    _timestamp(record.created_at),
                    _timestamp(record.expires_at),
                    _optional_timestamp(record.applied_at),
                ),
            )


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Memory proposal timestamps must include a timezone.")
    return value.astimezone(UTC).isoformat()


def _optional_timestamp(value: datetime | None) -> str | None:
    return _timestamp(value) if value is not None else None


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise ValueError("Stored memory proposal timestamp must include a timezone.")

    return parsed.astimezone(UTC)


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return _datetime(str(value))
