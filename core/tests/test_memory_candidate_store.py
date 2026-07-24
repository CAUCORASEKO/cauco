from datetime import UTC, datetime, timedelta

import pytest

from cauco_core.learning.models import LessonCategory
from cauco_core.memory_candidates.models import (
    MemoryCandidateCapacityError,
    MemoryCandidateConflictError,
    MemoryCandidateDisposition,
    MemoryCandidateExpiredError,
    MemoryCandidateLesson,
    MemoryCandidateRecord,
    MemoryCandidateStatus,
    MemoryCandidateTarget,
)
from cauco_core.memory_candidates.store import (
    MemoryCandidateStore,
    deterministic_candidate_id,
)

EXPERIENCE_ID = "experience_abcdefghijklmnopqrstuvwx"
VERIFICATION_ID = "verify_abcdefghijklmnopqrstuvwx"
EXECUTION_ID = "exec_abcdefghijklmnopqrstuvwx"
REVIEW_ID = "planrev_abcdefghijklmnopqrstuvwx"
SNAPSHOT_DIGEST = "a" * 64
METHOD = "deterministic_experience_memory_candidate_v1"
RATIONALE = "This reusable lesson may improve the construction of future plans."


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


def lesson(
    *,
    category: LessonCategory = LessonCategory.PLANNING,
    observation: str = "The plan omitted a required precondition.",
    lesson_text: str = "Validate required preconditions before execution.",
    confidence: float = 0.9,
    tool_id: str | None = None,
    operation_id: str | None = None,
    step_index: int | None = None,
) -> MemoryCandidateLesson:
    return MemoryCandidateLesson(
        category=category,
        observation=observation,
        lesson=lesson_text,
        confidence=confidence,
        tool_id=tool_id,
        operation_id=operation_id,
        step_index=step_index,
    )


def create_candidate(
    store: MemoryCandidateStore,
    *,
    candidate_id: str | None = None,
    candidate_lesson: MemoryCandidateLesson | None = None,
):
    return store.create(
        candidate_id=candidate_id,
        experience_id=EXPERIENCE_ID,
        verification_id=VERIFICATION_ID,
        execution_id=EXECUTION_ID,
        review_id=REVIEW_ID,
        snapshot_digest=SNAPSHOT_DIGEST,
        lesson=candidate_lesson or lesson(),
        rationale=RATIONALE,
        method=METHOD,
    )


def test_valid_pending_candidate_model() -> None:
    created_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)

    record = MemoryCandidateRecord(
        candidate_id="memory_candidate_abcdefghijklmnopqrstuvwx",
        experience_id=EXPERIENCE_ID,
        verification_id=VERIFICATION_ID,
        execution_id=EXECUTION_ID,
        review_id=REVIEW_ID,
        snapshot_digest=SNAPSHOT_DIGEST,
        lesson=lesson(),
        target=MemoryCandidateTarget.LEARNING,
        status=MemoryCandidateStatus.PENDING_REVIEW,
        disposition=None,
        rationale=RATIONALE,
        created_at=created_at,
        expires_at=created_at + timedelta(days=7),
        reviewed_at=None,
        review_note=None,
        method=METHOD,
    )

    assert record.status is MemoryCandidateStatus.PENDING_REVIEW
    assert record.disposition is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_id", "bad"),
        ("experience_id", "bad"),
        ("verification_id", "bad"),
        ("execution_id", "bad"),
        ("snapshot_digest", "A" * 64),
    ],
)
def test_invalid_record_identifiers(
    field: str,
    value: str,
) -> None:
    created_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
    values = {
        "candidate_id": "memory_candidate_abcdefghijklmnopqrstuvwx",
        "experience_id": EXPERIENCE_ID,
        "verification_id": VERIFICATION_ID,
        "execution_id": EXECUTION_ID,
        "review_id": REVIEW_ID,
        "snapshot_digest": SNAPSHOT_DIGEST,
        "lesson": lesson(),
        "target": MemoryCandidateTarget.LEARNING,
        "status": MemoryCandidateStatus.PENDING_REVIEW,
        "disposition": None,
        "rationale": RATIONALE,
        "created_at": created_at,
        "expires_at": created_at + timedelta(days=7),
        "reviewed_at": None,
        "review_note": None,
        "method": METHOD,
    }
    values[field] = value

    with pytest.raises(ValueError):
        MemoryCandidateRecord(**values)


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_invalid_lesson_confidence(confidence: float) -> None:
    with pytest.raises(ValueError):
        lesson(confidence=confidence)


def test_invalid_step_index() -> None:
    with pytest.raises(ValueError):
        lesson(step_index=0)


def test_pending_candidate_cannot_contain_review_state() -> None:
    created_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)

    with pytest.raises(ValueError):
        MemoryCandidateRecord(
            candidate_id="memory_candidate_abcdefghijklmnopqrstuvwx",
            experience_id=EXPERIENCE_ID,
            verification_id=VERIFICATION_ID,
            execution_id=EXECUTION_ID,
            review_id=REVIEW_ID,
            snapshot_digest=SNAPSHOT_DIGEST,
            lesson=lesson(),
            target=MemoryCandidateTarget.LEARNING,
            status=MemoryCandidateStatus.PENDING_REVIEW,
            disposition=MemoryCandidateDisposition.PROMOTE_TO_MEMORY,
            rationale=RATIONALE,
            created_at=created_at,
            expires_at=created_at + timedelta(days=7),
            reviewed_at=created_at,
            review_note=None,
            method=METHOD,
        )


def test_expired_candidate_cannot_contain_review_state() -> None:
    created_at = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)

    with pytest.raises(ValueError):
        MemoryCandidateRecord(
            candidate_id="memory_candidate_abcdefghijklmnopqrstuvwx",
            experience_id=EXPERIENCE_ID,
            verification_id=VERIFICATION_ID,
            execution_id=EXECUTION_ID,
            review_id=REVIEW_ID,
            snapshot_digest=SNAPSHOT_DIGEST,
            lesson=lesson(),
            target=MemoryCandidateTarget.LEARNING,
            status=MemoryCandidateStatus.EXPIRED,
            disposition=None,
            rationale=RATIONALE,
            created_at=created_at,
            expires_at=created_at + timedelta(days=7),
            reviewed_at=None,
            review_note="Should not exist",
            method=METHOD,
        )


def test_create_get_and_idempotent_duplicate() -> None:
    store = MemoryCandidateStore()
    candidate_id = deterministic_candidate_id(EXPERIENCE_ID, lesson())

    first = create_candidate(store, candidate_id=candidate_id)
    repeated = create_candidate(store, candidate_id=candidate_id)

    assert repeated == first
    assert store.get(candidate_id) == first
    assert store.for_experience(EXPERIENCE_ID) == (first,)


def test_deterministic_candidate_identity() -> None:
    candidate_lesson = lesson(
        category=LessonCategory.TOOL_RELIABILITY,
        tool_id="git",
        operation_id="status",
        step_index=1,
    )

    first = deterministic_candidate_id(
        EXPERIENCE_ID,
        candidate_lesson,
    )
    second = deterministic_candidate_id(
        EXPERIENCE_ID,
        candidate_lesson,
    )

    assert first == second
    assert first.startswith("memory_candidate_")
    assert len(first.removeprefix("memory_candidate_")) == 64


def test_list_filters_and_newest_first() -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    store = MemoryCandidateStore(clock=clock)

    first = create_candidate(
        store,
        candidate_id="memory_candidate_aaaaaaaaaaaaaaaaaaaaaaaa",
    )
    clock.advance(timedelta(seconds=1))
    second = create_candidate(
        store,
        candidate_id="memory_candidate_bbbbbbbbbbbbbbbbbbbbbbbb",
        candidate_lesson=lesson(
            category=LessonCategory.EXECUTION,
            observation="The execution used an unreliable operation.",
            lesson_text="Prefer verified operations.",
        ),
    )

    assert store.list() == (second, first)
    assert store.list(
        experience_id=EXPERIENCE_ID,
        review_id=REVIEW_ID,
        status=MemoryCandidateStatus.PENDING_REVIEW,
        target=MemoryCandidateTarget.LEARNING,
        limit=1,
    ) == (second,)


def test_approve_normalizes_review_note() -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    store = MemoryCandidateStore(clock=clock)
    created = create_candidate(store)

    clock.advance(timedelta(minutes=5))
    approved = store.approve(
        created.candidate_id,
        "  Reviewed and accepted.  ",
    )

    assert approved.status is MemoryCandidateStatus.APPROVED
    assert approved.disposition is MemoryCandidateDisposition.PROMOTE_TO_MEMORY
    assert approved.review_note == "Reviewed and accepted."
    assert approved.reviewed_at == clock.value


@pytest.mark.parametrize(
    "disposition",
    [
        MemoryCandidateDisposition.RETAIN_AS_EXPERIENCE_ONLY,
        MemoryCandidateDisposition.DISCARD,
    ],
)
def test_reject_with_supported_disposition(
    disposition: MemoryCandidateDisposition,
) -> None:
    store = MemoryCandidateStore()
    created = create_candidate(store)

    rejected = store.reject(
        created.candidate_id,
        disposition,
        "  Human review  ",
    )

    assert rejected.status is MemoryCandidateStatus.REJECTED
    assert rejected.disposition is disposition
    assert rejected.review_note == "Human review"


def test_reject_cannot_promote_to_memory() -> None:
    store = MemoryCandidateStore()
    created = create_candidate(store)

    with pytest.raises(ValueError):
        store.reject(
            created.candidate_id,
            MemoryCandidateDisposition.PROMOTE_TO_MEMORY,
        )


def test_candidate_cannot_be_reviewed_twice() -> None:
    store = MemoryCandidateStore()
    created = create_candidate(store)
    store.approve(created.candidate_id)

    with pytest.raises(MemoryCandidateConflictError):
        store.reject(
            created.candidate_id,
            MemoryCandidateDisposition.DISCARD,
        )


def test_get_returns_expired_record() -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    store = MemoryCandidateStore(
        ttl=timedelta(minutes=1),
        clock=clock,
    )
    created = create_candidate(store)

    clock.advance(timedelta(minutes=1))
    expired = store.get(created.candidate_id)

    assert expired.status is MemoryCandidateStatus.EXPIRED
    assert expired.disposition is None
    assert expired.reviewed_at is None


def test_approval_after_expiration_is_rejected() -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    store = MemoryCandidateStore(
        ttl=timedelta(minutes=1),
        clock=clock,
    )
    created = create_candidate(store)

    clock.advance(timedelta(minutes=1))

    with pytest.raises(MemoryCandidateExpiredError):
        store.approve(created.candidate_id)

    assert store.get(created.candidate_id).status is MemoryCandidateStatus.EXPIRED


def test_capacity_evicts_terminal_record_first() -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    store = MemoryCandidateStore(max_records=2, clock=clock)

    first = create_candidate(
        store,
        candidate_id="memory_candidate_aaaaaaaaaaaaaaaaaaaaaaaa",
    )
    store.reject(
        first.candidate_id,
        MemoryCandidateDisposition.DISCARD,
    )

    clock.advance(timedelta(seconds=1))
    second = create_candidate(
        store,
        candidate_id="memory_candidate_bbbbbbbbbbbbbbbbbbbbbbbb",
    )

    clock.advance(timedelta(seconds=1))
    third = create_candidate(
        store,
        candidate_id="memory_candidate_cccccccccccccccccccccccc",
    )

    assert store.list() == (third, second)


def test_capacity_expires_stale_pending_before_eviction() -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    store = MemoryCandidateStore(
        ttl=timedelta(minutes=1),
        max_records=1,
        clock=clock,
    )

    first = create_candidate(
        store,
        candidate_id="memory_candidate_aaaaaaaaaaaaaaaaaaaaaaaa",
    )
    clock.advance(timedelta(minutes=1))

    second = create_candidate(
        store,
        candidate_id="memory_candidate_bbbbbbbbbbbbbbbbbbbbbbbb",
    )

    assert second.candidate_id != first.candidate_id
    assert store.list() == (second,)


def test_capacity_rejects_eviction_of_active_pending_record() -> None:
    store = MemoryCandidateStore(max_records=1)
    create_candidate(
        store,
        candidate_id="memory_candidate_aaaaaaaaaaaaaaaaaaaaaaaa",
    )

    with pytest.raises(MemoryCandidateCapacityError):
        create_candidate(
            store,
            candidate_id="memory_candidate_bbbbbbbbbbbbbbbbbbbbbbbb",
        )


def test_records_are_immutable() -> None:
    store = MemoryCandidateStore()
    created = create_candidate(store)

    with pytest.raises(AttributeError):
        created.status = MemoryCandidateStatus.APPROVED
