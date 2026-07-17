from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory_writing.models import (
    MemoryWriteProposalState,
    MemoryWriteRequest,
)
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import (
    MemoryWriteProposalStore,
    ProposalExpiredError,
    ProposalNotFoundError,
    ProposalStateConflictError,
)


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def test_store_lifecycle_ttl_and_payload_isolation(tmp_path: Path) -> None:
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    brain = tmp_path / "brain"
    brain.mkdir()
    engine = MemoryEngine(brain)
    engine.refresh()
    builder = MemoryWriteProposalBuilder(engine, clock=clock)
    store = MemoryWriteProposalStore(ttl=timedelta(minutes=30), clock=clock)
    proposal = builder.build(MemoryWriteRequest(instruction="Add a task to test storage"))

    pending = store.put(proposal)
    assert pending.state is MemoryWriteProposalState.PENDING
    assert pending.created_at == now
    assert pending.expires_at == now + timedelta(minutes=30)
    assert pending.applied_at is None

    pending.proposal.markdown_preview = "forged"
    assert store.get(proposal.proposal_id).proposal.markdown_preview == proposal.markdown_preview

    applied_at = now + timedelta(minutes=1)
    applied = store.mark_applied(proposal.proposal_id, applied_at)
    assert applied.state is MemoryWriteProposalState.APPLIED
    assert applied.applied_at == applied_at
    with pytest.raises(ProposalStateConflictError):
        store.get_pending(proposal.proposal_id)


def test_store_enforces_expiration_and_unknown_ids(tmp_path: Path) -> None:
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    brain = tmp_path / "brain"
    brain.mkdir()
    engine = MemoryEngine(brain)
    engine.refresh()
    proposal = MemoryWriteProposalBuilder(engine, clock=clock).build(
        MemoryWriteRequest(instruction="Add a task to test expiry")
    )
    store = MemoryWriteProposalStore(ttl=timedelta(minutes=30), clock=clock)
    store.put(proposal)

    clock.current = now + timedelta(minutes=30)
    assert store.get(proposal.proposal_id).state is MemoryWriteProposalState.EXPIRED
    with pytest.raises(ProposalExpiredError):
        store.get_pending(proposal.proposal_id)
    with pytest.raises(ProposalNotFoundError):
        store.get("proposal_unknown")


def test_same_applied_proposal_is_never_reopened(tmp_path: Path) -> None:
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    brain = tmp_path / "brain"
    brain.mkdir()
    engine = MemoryEngine(brain)
    engine.refresh()
    builder = MemoryWriteProposalBuilder(engine, clock=clock)
    store = MemoryWriteProposalStore(clock=clock)
    first = builder.build(MemoryWriteRequest(instruction="Add a task to preserve state"))
    store.put(first)
    store.mark_applied(first.proposal_id, now)

    clock.current = now + timedelta(minutes=1)
    regenerated = builder.build(MemoryWriteRequest(instruction="Add a task to preserve state"))
    stored = store.put(regenerated)
    assert stored.proposal.created_at == now
    assert stored.state is MemoryWriteProposalState.APPLIED


def test_same_pending_proposal_keeps_original_payload_and_expiry(tmp_path: Path) -> None:
    now = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    clock = MutableClock(now)
    brain = tmp_path / "brain"
    brain.mkdir()
    engine = MemoryEngine(brain)
    engine.refresh()
    builder = MemoryWriteProposalBuilder(engine, clock=clock)
    store = MemoryWriteProposalStore(clock=clock)
    first = builder.build(MemoryWriteRequest(instruction="Add a task to remain pending"))
    initial = store.put(first)

    clock.current = now + timedelta(minutes=1)
    second = builder.build(MemoryWriteRequest(instruction="Add a task to remain pending"))
    repeated = store.put(second)

    assert repeated.proposal.created_at == initial.proposal.created_at
    assert repeated.expires_at == initial.expires_at
    assert repeated.state is MemoryWriteProposalState.PENDING
