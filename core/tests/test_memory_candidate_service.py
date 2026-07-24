from datetime import UTC, datetime

import pytest

from cauco_core.learning.models import (
    ExperienceOutcome,
    LessonCandidate,
    LessonCategory,
)
from cauco_core.learning.store import ExperienceStore
from cauco_core.memory_candidates.models import (
    MemoryCandidateNotFoundError,
    MemoryCandidateStatus,
    MemoryCandidateTarget,
    MemoryCandidateValidationError,
)
from cauco_core.memory_candidates.service import MemoryCandidateService
from cauco_core.memory_candidates.store import MemoryCandidateStore

VERIFICATION_ID = "verify_abcdefghijklmnopqrstuvwx"
EXECUTION_ID = "exec_abcdefghijklmnopqrstuvwx"
REVIEW_ID = "planrev_abcdefghijklmnopqrstuvwx"
SNAPSHOT_DIGEST = "a" * 64


def create_experience(
    store: ExperienceStore,
    *,
    lessons: tuple[LessonCandidate, ...],
):
    return store.create(
        verification_id=VERIFICATION_ID,
        execution_id=EXECUTION_ID,
        review_id=REVIEW_ID,
        snapshot_digest=SNAPSHOT_DIGEST,
        outcome=ExperienceOutcome.SUCCESS,
        summary="The execution produced reusable operational learning.",
        recommendation="Retain reusable lessons for future decisions.",
        lesson_candidates=lessons,
        method="test_experience_consolidation",
    )


def reusable_lesson(
    *,
    category: LessonCategory,
    observation: str,
    lesson: str,
    confidence: float = 0.9,
    tool_id: str | None = None,
    operation_id: str | None = None,
    step_index: int | None = None,
) -> LessonCandidate:
    return LessonCandidate(
        category=category,
        observation=observation,
        lesson=lesson,
        confidence=confidence,
        reusable=True,
        tool_id=tool_id,
        operation_id=operation_id,
        step_index=step_index,
    )


def test_creates_one_candidate_per_reusable_lesson() -> None:
    experience_store = ExperienceStore(clock=lambda: datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    candidate_store = MemoryCandidateStore()
    service = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=candidate_store,
    )

    experience = create_experience(
        experience_store,
        lessons=(
            reusable_lesson(
                category=LessonCategory.PLANNING,
                observation="The plan omitted a prerequisite.",
                lesson="Validate prerequisites before execution.",
            ),
            reusable_lesson(
                category=LessonCategory.EXECUTION,
                observation="The operation lacked a safe fallback.",
                lesson="Define a safe fallback before execution.",
                tool_id="git",
                operation_id="status",
                step_index=1,
            ),
        ),
    )

    candidates = service.create_for_experience(experience.experience_id)

    assert len(candidates) == 2
    assert all(candidate.status is MemoryCandidateStatus.PENDING_REVIEW for candidate in candidates)
    assert all(candidate.target is MemoryCandidateTarget.LEARNING for candidate in candidates)


def test_ignores_non_reusable_lessons() -> None:
    experience_store = ExperienceStore()
    candidate_store = MemoryCandidateStore()
    service = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=candidate_store,
    )

    experience = create_experience(
        experience_store,
        lessons=(
            LessonCandidate(
                category=LessonCategory.PLANNING,
                observation="Temporary condition.",
                lesson="Do not promote this lesson.",
                confidence=0.5,
                reusable=False,
            ),
            reusable_lesson(
                category=LessonCategory.VERIFICATION,
                observation="Success criteria were incomplete.",
                lesson="Define measurable success criteria.",
            ),
        ),
    )

    candidates = service.create_for_experience(experience.experience_id)

    assert len(candidates) == 1
    assert candidates[0].lesson.category is LessonCategory.VERIFICATION


def test_no_reusable_lessons_raises_validation_error() -> None:
    experience_store = ExperienceStore()
    service = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=MemoryCandidateStore(),
    )

    experience = create_experience(
        experience_store,
        lessons=(
            LessonCandidate(
                category=LessonCategory.PLANNING,
                observation="Temporary observation.",
                lesson="Temporary lesson.",
                confidence=0.4,
                reusable=False,
            ),
        ),
    )

    with pytest.raises(
        MemoryCandidateValidationError,
        match="no reusable lessons",
    ):
        service.create_for_experience(experience.experience_id)


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (
            LessonCategory.PLANNING,
            "This reusable lesson may improve the construction of future plans.",
        ),
        (
            LessonCategory.EXECUTION,
            "This reusable lesson may improve how future approved operations are performed.",
        ),
        (
            LessonCategory.VERIFICATION,
            "This reusable lesson may improve the definition "
            "and evaluation of future success criteria.",
        ),
        (
            LessonCategory.TOOL_RELIABILITY,
            "This reusable lesson may improve future decisions involving this tool-operation pair.",
        ),
    ],
)
def test_category_rationale_mapping(
    category: LessonCategory,
    expected: str,
) -> None:
    experience_store = ExperienceStore()
    service = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=MemoryCandidateStore(),
    )

    experience = create_experience(
        experience_store,
        lessons=(
            reusable_lesson(
                category=category,
                observation="Observation.",
                lesson="Reusable lesson.",
            ),
        ),
    )

    candidate = service.create_for_experience(experience.experience_id)[0]

    assert candidate.rationale == expected


def test_preserves_experience_references_and_lesson_fields() -> None:
    experience_store = ExperienceStore()
    service = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=MemoryCandidateStore(),
    )

    experience = create_experience(
        experience_store,
        lessons=(
            reusable_lesson(
                category=LessonCategory.TOOL_RELIABILITY,
                observation="The tool operation was unreliable.",
                lesson="Verify this operation before depending on it.",
                confidence=0.83,
                tool_id="git",
                operation_id="push",
                step_index=2,
            ),
        ),
    )

    candidate = service.create_for_experience(experience.experience_id)[0]

    assert candidate.experience_id == experience.experience_id
    assert candidate.verification_id == experience.verification_id
    assert candidate.execution_id == experience.execution_id
    assert candidate.review_id == experience.review_id
    assert candidate.snapshot_digest == experience.snapshot_digest
    assert candidate.lesson.confidence == 0.83
    assert candidate.lesson.tool_id == "git"
    assert candidate.lesson.operation_id == "push"
    assert candidate.lesson.step_index == 2
    assert candidate.method == ("deterministic_experience_memory_candidate_v1")


def test_duplicate_lessons_are_suppressed() -> None:
    experience_store = ExperienceStore()
    service = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=MemoryCandidateStore(),
    )

    duplicate = reusable_lesson(
        category=LessonCategory.PLANNING,
        observation="Same observation.",
        lesson="Same lesson.",
    )
    experience = create_experience(
        experience_store,
        lessons=(duplicate, duplicate),
    )

    candidates = service.create_for_experience(experience.experience_id)

    assert len(candidates) == 1


def test_repeat_creation_is_idempotent() -> None:
    experience_store = ExperienceStore()
    candidate_store = MemoryCandidateStore()
    service = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=candidate_store,
    )

    experience = create_experience(
        experience_store,
        lessons=(
            reusable_lesson(
                category=LessonCategory.PLANNING,
                observation="Stable observation.",
                lesson="Stable lesson.",
            ),
        ),
    )

    first = service.create_for_experience(experience.experience_id)
    repeated = service.create_for_experience(experience.experience_id)

    assert repeated == first
    assert candidate_store.list() == first


def test_candidate_ids_are_stable_across_stores() -> None:
    experience_store = ExperienceStore()
    experience = create_experience(
        experience_store,
        lessons=(
            reusable_lesson(
                category=LessonCategory.EXECUTION,
                observation="Stable observation.",
                lesson="Stable lesson.",
                tool_id="git",
                operation_id="status",
                step_index=1,
            ),
        ),
    )

    first = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=MemoryCandidateStore(),
    ).create_for_experience(experience.experience_id)

    second = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=MemoryCandidateStore(),
    ).create_for_experience(experience.experience_id)

    assert first[0].candidate_id == second[0].candidate_id


def test_unknown_experience_maps_to_candidate_not_found() -> None:
    service = MemoryCandidateService(
        experience_store=ExperienceStore(),
        candidate_store=MemoryCandidateStore(),
    )

    with pytest.raises(
        MemoryCandidateNotFoundError,
        match="Experience record not found",
    ):
        service.create_for_experience("experience_abcdefghijklmnopqrstuvwx")


def test_candidates_have_deterministic_sort_order() -> None:
    experience_store = ExperienceStore()
    service = MemoryCandidateService(
        experience_store=experience_store,
        candidate_store=MemoryCandidateStore(),
    )

    experience = create_experience(
        experience_store,
        lessons=(
            reusable_lesson(
                category=LessonCategory.TOOL_RELIABILITY,
                observation="Tool observation.",
                lesson="Tool lesson.",
                tool_id="git",
                operation_id="push",
                step_index=2,
            ),
            reusable_lesson(
                category=LessonCategory.PLANNING,
                observation="Planning observation.",
                lesson="Planning lesson.",
            ),
            reusable_lesson(
                category=LessonCategory.EXECUTION,
                observation="Execution observation.",
                lesson="Execution lesson.",
                step_index=1,
            ),
        ),
    )

    candidates = service.create_for_experience(experience.experience_id)

    assert [candidate.lesson.category for candidate in candidates] == [
        LessonCategory.EXECUTION,
        LessonCategory.PLANNING,
        LessonCategory.TOOL_RELIABILITY,
    ]
