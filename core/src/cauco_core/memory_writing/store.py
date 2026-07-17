from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock

from cauco_core.memory_writing.models import (
    MemoryWriteProposal,
    MemoryWriteProposalState,
    StoredMemoryWriteProposal,
)


class ProposalStoreError(RuntimeError):
    """Base class for proposal lifecycle failures."""


class ProposalNotFoundError(ProposalStoreError):
    """Raised when a proposal ID is unknown to this process."""


class ProposalExpiredError(ProposalStoreError):
    """Raised when confirmation is attempted after the proposal TTL."""


class ProposalStateConflictError(ProposalStoreError):
    """Raised when a proposal is not pending."""


@dataclass
class _ProposalRecord:
    proposal: MemoryWriteProposal
    state: MemoryWriteProposalState
    created_at: datetime
    expires_at: datetime
    applied_at: datetime | None = None


class MemoryWriteProposalStore:
    """In-process proposal storage; records are lost when the backend restarts."""

    def __init__(
        self,
        *,
        ttl: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl.total_seconds() <= 0:
            raise ValueError("Proposal TTL must be positive.")
        self.ttl = ttl
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self._records: dict[str, _ProposalRecord] = {}
        self._lock = RLock()

    def put(self, proposal: MemoryWriteProposal) -> StoredMemoryWriteProposal:
        with self._lock:
            existing = self._records.get(proposal.proposal_id)
            if existing is not None:
                self._expire_if_needed(existing)
                if existing.state in {
                    MemoryWriteProposalState.PENDING,
                    MemoryWriteProposalState.APPLIED,
                }:
                    return self._snapshot(existing)
            record = _ProposalRecord(
                proposal=proposal.model_copy(deep=True),
                state=MemoryWriteProposalState.PENDING,
                created_at=proposal.created_at,
                expires_at=proposal.created_at + self.ttl,
            )
            self._records[proposal.proposal_id] = record
            return self._snapshot(record)

    def get(self, proposal_id: str) -> StoredMemoryWriteProposal:
        with self._lock:
            record = self._record(proposal_id)
            self._expire_if_needed(record)
            return self._snapshot(record)

    def get_pending(self, proposal_id: str) -> StoredMemoryWriteProposal:
        with self._lock:
            record = self._record(proposal_id)
            self._expire_if_needed(record)
            if record.state is MemoryWriteProposalState.EXPIRED:
                raise ProposalExpiredError("The memory write proposal has expired.")
            if record.state is not MemoryWriteProposalState.PENDING:
                raise ProposalStateConflictError(
                    f"The memory write proposal is already {record.state.value}."
                )
            return self._snapshot(record)

    def mark_applied(self, proposal_id: str, applied_at: datetime) -> StoredMemoryWriteProposal:
        with self._lock:
            record = self._record(proposal_id)
            self._expire_if_needed(record)
            if record.state is MemoryWriteProposalState.EXPIRED:
                raise ProposalExpiredError("The memory write proposal has expired.")
            if record.state is not MemoryWriteProposalState.PENDING:
                raise ProposalStateConflictError(
                    f"The memory write proposal is already {record.state.value}."
                )
            record.state = MemoryWriteProposalState.APPLIED
            record.applied_at = applied_at
            return self._snapshot(record)

    def _record(self, proposal_id: str) -> _ProposalRecord:
        record = self._records.get(proposal_id)
        if record is None:
            raise ProposalNotFoundError("Memory write proposal not found.")
        return record

    def _expire_if_needed(self, record: _ProposalRecord) -> None:
        if (
            record.state is MemoryWriteProposalState.PENDING
            and self.clock() >= record.expires_at
        ):
            record.state = MemoryWriteProposalState.EXPIRED

    @staticmethod
    def _snapshot(record: _ProposalRecord) -> StoredMemoryWriteProposal:
        return StoredMemoryWriteProposal(
            proposal=record.proposal.model_copy(deep=True),
            state=record.state,
            created_at=record.created_at,
            expires_at=record.expires_at,
            applied_at=record.applied_at,
        )
