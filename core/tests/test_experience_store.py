from datetime import UTC, datetime, timedelta

import pytest

from cauco_core.learning.models import (
    ExperienceConflictError,
    ExperienceNotFoundError,
    ExperienceOutcome,
    ExperienceRecord,
    LessonCandidate,
    LessonCategory,
)
from cauco_core.learning.store import ExperienceStore

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)


def reusable_lesson() -> LessonCandidate:
    return LessonCandidate(
        category=LessonCategory.VERIFICATION,
        observation="Evidence was unavailable.",
        lesson="Plans should include explicit verification.",
        confidence=0.95,
        reusable=True,
        tool_id="core.files",
        operation_id="write",
        step_index=1,
    )


def create_record(
    store: ExperienceStore,
    *,
    suffix: str,
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    lessons: tuple[LessonCandidate, ...] = (),
    review_id: str = "review-1",
) -> ExperienceRecord:
    return store.create(
        verification_id="verify_" + suffix * 24,
        execution_id="exec_" + suffix * 24,
        review_id=review_id,
        snapshot_digest=suffix * 64,
        outcome=outcome,
        summary="Consolidated experience.",
        lesson_candidates=lessons,
        recommendation="complete",
        method="test",
    )


def test_experience_store_creates_and_retrieves_record():
    store = ExperienceStore(clock=lambda: NOW)

    record = create_record(
        store,
        suffix="a",
        outcome=ExperienceOutcome.INCONCLUSIVE,
        lessons=(reusable_lesson(),),
    )

    assert store.get(record.experience_id) == record
    assert store.for_verification(record.verification_id) == record
    assert record.memory_candidate is True


def test_experience_record_validates_memory_candidate():
    with pytest.raises(
        ValueError,
        match="memory candidate must reflect reusable lessons",
    ):
        ExperienceRecord(
            experience_id="experience_" + "a" * 24,
            verification_id="verify_" + "b" * 24,
            execution_id="exec_" + "c" * 24,
            review_id="review-1",
            snapshot_digest="d" * 64,
            created_at=NOW,
            outcome=ExperienceOutcome.SUCCESS,
            summary="Verified.",
            lesson_candidates=(reusable_lesson(),),
            memory_candidate=False,
            recommendation="complete",
            method="test",
        )


def test_experience_store_rejects_duplicate_verification():
    store = ExperienceStore(clock=lambda: NOW)

    create_record(store, suffix="a")

    with pytest.raises(ExperienceConflictError, match="already exists"):
        create_record(store, suffix="a")


def test_experience_store_filters_and_orders_newest_first():
    current = NOW

    def clock() -> datetime:
        return current

    store = ExperienceStore(clock=clock)

    first = create_record(
        store,
        suffix="a",
        review_id="review-a",
    )

    current += timedelta(seconds=1)

    second = create_record(
        store,
        suffix="b",
        outcome=ExperienceOutcome.FAILURE,
        lessons=(reusable_lesson(),),
        review_id="review-b",
    )

    assert store.list() == (second, first)
    assert store.list(review_id="review-b") == (second,)
    assert store.list(outcome=ExperienceOutcome.FAILURE) == (second,)
    assert store.list(memory_candidate=True) == (second,)
    assert store.list(memory_candidate=False) == (first,)


def test_experience_store_evicts_oldest_record():
    current = NOW

    def clock() -> datetime:
        return current

    store = ExperienceStore(max_records=2, clock=clock)

    first = create_record(store, suffix="a")

    current += timedelta(seconds=1)
    second = create_record(store, suffix="b")

    current += timedelta(seconds=1)
    third = create_record(store, suffix="c")

    with pytest.raises(ExperienceNotFoundError):
        store.get(first.experience_id)

    assert store.list() == (third, second)
