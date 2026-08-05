from collections import Counter

from cauco_core.learning.models import LessonCategory
from cauco_core.memory_candidates.models import (
    MemoryCandidateDisposition,
    MemoryCandidateStatus,
    MemoryCandidateTarget,
)
from cauco_core.memory_candidates.store import MemoryCandidateStore
from cauco_core.memory_writing.models import MemoryWriteProposalState
from cauco_core.memory_writing.store import MemoryWriteProposalStore
from cauco_core.reflection.models import ReflectionPattern, ReflectionReport, ReflectionSummary


class ReflectionResolver:
    METHOD = "deterministic_applied_learning_reflection_v1"
    MAX_RECORDS = 100
    MAX_PATTERNS = 20

    def __init__(
        self, candidate_store: MemoryCandidateStore, proposal_store: MemoryWriteProposalStore
    ):
        self.candidate_store = candidate_store
        self.proposal_store = proposal_store

    def resolve(self) -> ReflectionReport:
        candidates = self.candidate_store.list(
            status=MemoryCandidateStatus.APPROVED,
            target=MemoryCandidateTarget.LEARNING,
            limit=self.MAX_RECORDS,
        )
        approved = tuple(
            candidate
            for candidate in candidates
            if candidate.disposition is MemoryCandidateDisposition.PROMOTE_TO_MEMORY
        )
        by_id = {candidate.candidate_id: candidate for candidate in approved}
        applied = self.proposal_store.list(
            state=MemoryWriteProposalState.APPLIED,
            source_type="memory_candidate",
            limit=self.MAX_RECORDS,
        )
        applied_candidates = tuple(
            by_id[stored.proposal.source_id]
            for stored in applied
            if stored.proposal.source_id in by_id
        )
        categories = Counter(candidate.lesson.category.value for candidate in applied_candidates)
        lessons = Counter(
            (candidate.lesson.category.value, candidate.lesson.lesson)
            for candidate in applied_candidates
        )
        patterns = tuple(
            ReflectionPattern(category, lesson, count)
            for (category, lesson), count in sorted(
                lessons.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
            )[: self.MAX_PATTERNS]
        )
        return ReflectionReport(
            summary=ReflectionSummary(
                approved_candidates=len(approved),
                applied_learning_proposals=len(applied_candidates),
                planning=categories.get(LessonCategory.PLANNING.value, 0),
                execution=categories.get(LessonCategory.EXECUTION.value, 0),
                verification=categories.get(LessonCategory.VERIFICATION.value, 0),
            ),
            patterns=patterns,
            method=self.METHOD,
            limitations=(
                "Deterministic persisted approved candidates and applied learning proposals "
                "only; no mutation or model inference.",
                f"Results are bounded to {self.MAX_RECORDS} candidates, proposals, and "
                f"{self.MAX_PATTERNS} patterns.",
            ),
        )
