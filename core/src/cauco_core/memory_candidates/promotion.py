from cauco_core.memory_candidates.models import (
    MemoryCandidateDisposition,
    MemoryCandidateExpiredError,
    MemoryCandidateStatus,
    MemoryCandidateTarget,
)
from cauco_core.memory_candidates.store import MemoryCandidateStore
from cauco_core.memory_writing.models import StoredMemoryWriteProposal
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import MemoryWriteProposalStore


class MemoryCandidatePromotionError(RuntimeError):
    pass


class MemoryCandidateNotPromotableError(MemoryCandidatePromotionError):
    pass


class MemoryCandidatePromotionService:
    def __init__(
        self,
        candidate_store: MemoryCandidateStore,
        proposal_builder: MemoryWriteProposalBuilder,
        proposal_store: MemoryWriteProposalStore,
    ) -> None:
        self.candidate_store = candidate_store
        self.proposal_builder = proposal_builder
        self.proposal_store = proposal_store

    def promote(self, candidate_id: str) -> StoredMemoryWriteProposal:
        candidate = self.candidate_store.get(candidate_id)
        if candidate.status is MemoryCandidateStatus.EXPIRED:
            raise MemoryCandidateExpiredError("The memory candidate has expired.")
        if (
            candidate.status is not MemoryCandidateStatus.APPROVED
            or candidate.disposition is not MemoryCandidateDisposition.PROMOTE_TO_MEMORY
            or candidate.target is not MemoryCandidateTarget.LEARNING
        ):
            raise MemoryCandidateNotPromotableError("The memory candidate is not promotable.")
        proposal = self.proposal_builder.build_from_memory_candidate(candidate)
        return self.proposal_store.put(proposal)
