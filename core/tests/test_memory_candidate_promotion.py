from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cauco_core.learning.models import LessonCategory
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory_candidates.models import (
    MemoryCandidateDisposition,
    MemoryCandidateLesson,
    MemoryCandidateStatus,
)
from cauco_core.memory_candidates.promotion import (
    MemoryCandidateNotPromotableError,
    MemoryCandidatePromotionService,
)
from cauco_core.memory_candidates.store import MemoryCandidateStore
from cauco_core.memory_writing.analyzer import MemoryWriteProposalError
from cauco_core.memory_writing.models import (
    MemoryWriteOperation,
    MemoryWriteProposalState,
    MemoryWriteRequest,
)
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import MemoryWriteProposalStore

FIXED_TIME = datetime(2026, 8, 5, 7, 0, tzinfo=UTC)


def components(tmp_path: Path):
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "memory.md").write_text(
        "# Memory\n\n"
        "## Current context\n\n"
        "- Existing context.\n\n"
        "## Reference notes\n\n"
        "- Existing reference.\n",
        encoding="utf-8",
    )

    engine = MemoryEngine(brain)
    engine.refresh()

    candidate_store = MemoryCandidateStore(
        ttl=timedelta(days=7),
        clock=lambda: FIXED_TIME,
    )
    proposal_store = MemoryWriteProposalStore(
        clock=lambda: FIXED_TIME,
    )
    builder = MemoryWriteProposalBuilder(
        engine,
        clock=lambda: FIXED_TIME,
    )
    service = MemoryCandidatePromotionService(
        candidate_store,
        builder,
        proposal_store,
    )
    return candidate_store, proposal_store, builder, service


def create_candidate(candidate_store: MemoryCandidateStore):
    candidate = candidate_store.create(
        candidate_id="memory_candidate_" + "a" * 64,
        experience_id="experience_abcdefghijklmnopqrstuvwx",
        verification_id="verify_abcdefghijklmnopqrstuvwx",
        execution_id="exec_abcdefghijklmnopqrstuvwx",
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="b" * 64,
        lesson=MemoryCandidateLesson(
            category=LessonCategory.PLANNING,
            observation="A precondition was omitted.",
            lesson="Validate required preconditions before execution.",
            confidence=0.95,
        ),
        rationale="Reusable planning lesson.",
        method="test",
    )
    return candidate_store.approve(
        candidate.candidate_id,
        "Approved for durable learning.",
    )


def test_approved_candidate_creates_pending_learning_proposal(tmp_path: Path) -> None:
    candidate_store, _, _, service = components(tmp_path)
    candidate = create_candidate(candidate_store)

    stored = service.promote(candidate.candidate_id)

    assert stored.state is MemoryWriteProposalState.PENDING
    assert stored.proposal.operation is MemoryWriteOperation.ADD_LEARNING_NOTE
    assert stored.proposal.target_file == "memory.md"
    assert stored.proposal.target_section == "Reference notes"
    assert stored.proposal.source_type == "memory_candidate"
    assert stored.proposal.source_id == candidate.candidate_id
    assert stored.proposal.requires_confirmation is True
    assert "Validate required preconditions" in stored.proposal.markdown_preview


def test_promotion_is_idempotent(tmp_path: Path) -> None:
    candidate_store, _, _, service = components(tmp_path)
    candidate = create_candidate(candidate_store)

    first = service.promote(candidate.candidate_id)
    second = service.promote(candidate.candidate_id)

    assert second == first


def test_pending_candidate_cannot_be_promoted(tmp_path: Path) -> None:
    candidate_store, _, _, service = components(tmp_path)

    candidate = candidate_store.create(
        candidate_id="memory_candidate_" + "c" * 64,
        experience_id="experience_abcdefghijklmnopqrstuvwx",
        verification_id="verify_abcdefghijklmnopqrstuvwx",
        execution_id="exec_abcdefghijklmnopqrstuvwx",
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="d" * 64,
        lesson=MemoryCandidateLesson(
            category=LessonCategory.EXECUTION,
            observation="Structured output was absent.",
            lesson="Return structured execution results.",
            confidence=0.9,
        ),
        rationale="Reusable execution lesson.",
        method="test",
    )

    assert candidate.status is MemoryCandidateStatus.PENDING_REVIEW

    with pytest.raises(MemoryCandidateNotPromotableError):
        service.promote(candidate.candidate_id)


def test_rejected_candidate_cannot_be_promoted(tmp_path: Path) -> None:
    candidate_store, _, _, service = components(tmp_path)

    candidate = candidate_store.create(
        candidate_id="memory_candidate_" + "e" * 64,
        experience_id="experience_abcdefghijklmnopqrstuvwx",
        verification_id="verify_abcdefghijklmnopqrstuvwx",
        execution_id="exec_abcdefghijklmnopqrstuvwx",
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="f" * 64,
        lesson=MemoryCandidateLesson(
            category=LessonCategory.VERIFICATION,
            observation="Evidence was incomplete.",
            lesson="Preserve sufficient verification evidence.",
            confidence=0.92,
        ),
        rationale="Reusable verification lesson.",
        method="test",
    )
    candidate_store.reject(
        candidate.candidate_id,
        MemoryCandidateDisposition.DISCARD,
    )

    with pytest.raises(MemoryCandidateNotPromotableError):
        service.promote(candidate.candidate_id)


def test_public_builder_rejects_internal_learning_operation(tmp_path: Path) -> None:
    _, _, builder, _ = components(tmp_path)

    with pytest.raises(
        MemoryWriteProposalError,
        match="only be created from approved memory candidates",
    ):
        builder.build(
            MemoryWriteRequest(
                instruction="Store this arbitrary learning note.",
                operation=MemoryWriteOperation.ADD_LEARNING_NOTE,
            )
        )
