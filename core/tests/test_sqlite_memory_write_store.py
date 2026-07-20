from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory_writing.models import (
    MemoryWriteProposalState,
    MemoryWriteRequest,
)
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.sqlite_store import SQLiteMemoryWriteProposalStore
from cauco_core.memory_writing.store import (
    ProposalExpiredError,
    ProposalStateConflictError,
)
from cauco_core.persistence import SQLiteDatabase


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def build_proposal(tmp_path: Path, clock: MutableClock):
    brain = tmp_path / "brain"
    brain.mkdir(exist_ok=True)
    engine = MemoryEngine(brain)
    engine.refresh()
    builder = MemoryWriteProposalBuilder(engine, clock=clock)
    return builder.build(MemoryWriteRequest(instruction="Add a task to persist proposal state"))


def test_pending_proposal_is_restored_after_restart(tmp_path: Path) -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    database = SQLiteDatabase(tmp_path / "cauco.db")
    proposal = build_proposal(tmp_path, clock)

    first = SQLiteMemoryWriteProposalStore(database, clock=clock)
    created = first.put(proposal)

    second = SQLiteMemoryWriteProposalStore(database, clock=clock)
    restored = second.get(proposal.proposal_id)

    assert restored == created
    assert restored.state is MemoryWriteProposalState.PENDING
    assert restored.proposal.model_dump() == proposal.model_dump()


def test_applied_proposal_remains_applied_after_restart(tmp_path: Path) -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    database = SQLiteDatabase(tmp_path / "cauco.db")
    proposal = build_proposal(tmp_path, clock)

    first = SQLiteMemoryWriteProposalStore(database, clock=clock)
    first.put(proposal)
    applied_at = now + timedelta(minutes=1)
    first.mark_applied(proposal.proposal_id, applied_at)

    second = SQLiteMemoryWriteProposalStore(database, clock=clock)
    restored = second.get(proposal.proposal_id)

    assert restored.state is MemoryWriteProposalState.APPLIED
    assert restored.applied_at == applied_at

    with pytest.raises(ProposalStateConflictError):
        second.get_pending(proposal.proposal_id)


def test_expiration_triggered_by_get_is_persisted(tmp_path: Path) -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    database = SQLiteDatabase(tmp_path / "cauco.db")
    proposal = build_proposal(tmp_path, clock)

    first = SQLiteMemoryWriteProposalStore(
        database,
        ttl=timedelta(minutes=30),
        clock=clock,
    )
    first.put(proposal)

    clock.current = now + timedelta(minutes=30)
    assert first.get(proposal.proposal_id).state is MemoryWriteProposalState.EXPIRED

    second = SQLiteMemoryWriteProposalStore(database, clock=clock)
    assert second.get(proposal.proposal_id).state is MemoryWriteProposalState.EXPIRED


def test_pending_proposal_expires_during_restart(tmp_path: Path) -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    database = SQLiteDatabase(tmp_path / "cauco.db")
    proposal = build_proposal(tmp_path, clock)

    first = SQLiteMemoryWriteProposalStore(
        database,
        ttl=timedelta(minutes=30),
        clock=clock,
    )
    first.put(proposal)

    clock.current = now + timedelta(minutes=31)
    second = SQLiteMemoryWriteProposalStore(database, clock=clock)

    assert second.get(proposal.proposal_id).state is MemoryWriteProposalState.EXPIRED

    with pytest.raises(ProposalExpiredError):
        second.get_pending(proposal.proposal_id)

    with database.connection() as connection:
        state = connection.execute(
            """
            SELECT state
            FROM memory_write_proposals
            WHERE proposal_id = ?
            """,
            (proposal.proposal_id,),
        ).fetchone()["state"]

    assert state == MemoryWriteProposalState.EXPIRED.value


def test_repeated_pending_proposal_keeps_original_expiry(tmp_path: Path) -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    database = SQLiteDatabase(tmp_path / "cauco.db")
    proposal = build_proposal(tmp_path, clock)

    store = SQLiteMemoryWriteProposalStore(database, clock=clock)
    initial = store.put(proposal)

    clock.current = now + timedelta(minutes=1)
    repeated = store.put(proposal.model_copy(deep=True))

    assert repeated.state is MemoryWriteProposalState.PENDING
    assert repeated.created_at == initial.created_at
    assert repeated.expires_at == initial.expires_at

    restarted = SQLiteMemoryWriteProposalStore(database, clock=clock)
    restored = restarted.get(proposal.proposal_id)

    assert restored.created_at == initial.created_at
    assert restored.expires_at == initial.expires_at
