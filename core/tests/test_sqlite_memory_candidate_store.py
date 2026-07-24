from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cauco_core.execution.models import (
    AgentPlanStepExecutionRecord,
    StepExecutionStatus,
)
from cauco_core.execution.sqlite_store import SQLiteExecutionStore
from cauco_core.learning.models import (
    ExperienceOutcome,
    LessonCandidate,
    LessonCategory,
)
from cauco_core.learning.sqlite_store import SQLiteExperienceStore
from cauco_core.memory_candidates.models import (
    MemoryCandidateDisposition,
    MemoryCandidateExpiredError,
    MemoryCandidateLesson,
    MemoryCandidateStatus,
)
from cauco_core.memory_candidates.sqlite_store import (
    SQLiteMemoryCandidateStore,
)
from cauco_core.persistence import SQLiteDatabase
from cauco_core.verification import (
    StepVerificationResult,
    VerificationOutcome,
    VerificationRecommendation,
)
from cauco_core.verification.sqlite_store import SQLiteVerificationStore

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


def lesson() -> MemoryCandidateLesson:
    return MemoryCandidateLesson(
        category=LessonCategory.PLANNING,
        observation="The plan omitted a required precondition.",
        lesson="Validate required preconditions before execution.",
        confidence=0.9,
    )


def create_experience(database: SQLiteDatabase):
    execution_store = SQLiteExecutionStore(database)
    verification_store = SQLiteVerificationStore(database)
    experience_store = SQLiteExperienceStore(database)

    execution = execution_store.create(
        REVIEW_ID,
        SNAPSHOT_DIGEST,
        (
            AgentPlanStepExecutionRecord(
                step_index=1,
                tool_id="git",
                operation_id="status",
                target=None,
                status=StepExecutionStatus.PENDING,
            ),
        ),
    )

    verification = verification_store.create(
        execution_id=execution.execution_id,
        review_id=execution.review_id,
        snapshot_digest=execution.snapshot_digest,
        outcome=VerificationOutcome.SUCCEEDED,
        recommendation=VerificationRecommendation.COMPLETE,
        method="integration_test",
        step_results=(
            StepVerificationResult(
                step_index=1,
                tool_id="git",
                operation_id="status",
                outcome=VerificationOutcome.SUCCEEDED,
                method="integration_test",
            ),
        ),
    )

    experience = experience_store.create(
        verification_id=verification.verification_id,
        execution_id=execution.execution_id,
        review_id=execution.review_id,
        snapshot_digest=execution.snapshot_digest,
        outcome=ExperienceOutcome.SUCCESS,
        summary="The verified execution produced reusable operational learning.",
        recommendation="Retain the lesson for future planning decisions.",
        lesson_candidates=(
            LessonCandidate(
                category=LessonCategory.PLANNING,
                observation="The plan omitted a required precondition.",
                lesson="Validate required preconditions before execution.",
                confidence=0.9,
                reusable=True,
            ),
        ),
        method="test",
    )

    return execution, verification, experience


def create_candidate(
    store: SQLiteMemoryCandidateStore,
    experience,
):
    return store.create(
        candidate_id=(
            "memory_candidate_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        ),
        experience_id=experience.experience_id,
        verification_id=experience.verification_id,
        execution_id=experience.execution_id,
        review_id=experience.review_id,
        snapshot_digest=experience.snapshot_digest,
        lesson=lesson(),
        rationale=RATIONALE,
        method=METHOD,
    )


def test_candidate_survives_restart(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)

    first_store = SQLiteMemoryCandidateStore(database)
    created = create_candidate(first_store, experience)

    restored_store = SQLiteMemoryCandidateStore(database)
    restored = restored_store.get(created.candidate_id)

    assert restored == created


def test_approval_survives_restart(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)

    store = SQLiteMemoryCandidateStore(database)
    created = create_candidate(store, experience)
    approved = store.approve(
        created.candidate_id,
        "Approved by reviewer",
    )

    restored = SQLiteMemoryCandidateStore(database).get(created.candidate_id)

    assert restored == approved
    assert restored.status is MemoryCandidateStatus.APPROVED
    assert restored.disposition is MemoryCandidateDisposition.PROMOTE_TO_MEMORY


@pytest.mark.parametrize(
    "disposition",
    [
        MemoryCandidateDisposition.RETAIN_AS_EXPERIENCE_ONLY,
        MemoryCandidateDisposition.DISCARD,
    ],
)
def test_rejection_survives_restart(
    tmp_path: Path,
    disposition: MemoryCandidateDisposition,
) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)

    store = SQLiteMemoryCandidateStore(database)
    created = create_candidate(store, experience)
    rejected = store.reject(
        created.candidate_id,
        disposition,
        "Rejected by reviewer",
    )

    restored = SQLiteMemoryCandidateStore(database).get(created.candidate_id)

    assert restored == rejected
    assert restored.status is MemoryCandidateStatus.REJECTED
    assert restored.disposition is disposition


def test_expiration_is_persisted_after_get(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)

    store = SQLiteMemoryCandidateStore(
        database,
        ttl=timedelta(minutes=1),
        clock=clock,
    )
    created = create_candidate(store, experience)

    clock.advance(timedelta(minutes=1))
    expired = store.get(created.candidate_id)

    assert expired.status is MemoryCandidateStatus.EXPIRED

    restored = SQLiteMemoryCandidateStore(
        database,
        ttl=timedelta(minutes=1),
        clock=clock,
    ).get(created.candidate_id)

    assert restored.status is MemoryCandidateStatus.EXPIRED


def test_expiration_is_persisted_after_list(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)

    store = SQLiteMemoryCandidateStore(
        database,
        ttl=timedelta(minutes=1),
        clock=clock,
    )
    created = create_candidate(store, experience)

    clock.advance(timedelta(minutes=1))
    listed = store.list()

    assert listed[0].status is MemoryCandidateStatus.EXPIRED

    restored = SQLiteMemoryCandidateStore(
        database,
        ttl=timedelta(minutes=1),
        clock=clock,
    ).get(created.candidate_id)

    assert restored.status is MemoryCandidateStatus.EXPIRED


def test_approval_after_expiration_is_rejected_and_persisted(
    tmp_path: Path,
) -> None:
    clock = MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)

    store = SQLiteMemoryCandidateStore(
        database,
        ttl=timedelta(minutes=1),
        clock=clock,
    )
    created = create_candidate(store, experience)

    clock.advance(timedelta(minutes=1))

    with pytest.raises(MemoryCandidateExpiredError):
        store.approve(created.candidate_id)

    restored = SQLiteMemoryCandidateStore(
        database,
        ttl=timedelta(minutes=1),
        clock=clock,
    ).get(created.candidate_id)

    assert restored.status is MemoryCandidateStatus.EXPIRED


def test_create_rolls_back_memory_on_database_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)
    store = SQLiteMemoryCandidateStore(database)

    @contextmanager
    def fail_transaction():
        raise RuntimeError("database write failed")
        yield

    monkeypatch.setattr(
        database,
        "transaction",
        fail_transaction,
    )

    with pytest.raises(RuntimeError):
        create_candidate(store, experience)

    assert store.list() == ()


def test_approve_rolls_back_memory_on_database_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)
    store = SQLiteMemoryCandidateStore(database)
    created = create_candidate(store, experience)

    @contextmanager
    def fail_transaction():
        raise RuntimeError("database write failed")
        yield

    monkeypatch.setattr(
        database,
        "transaction",
        fail_transaction,
    )

    with pytest.raises(RuntimeError):
        store.approve(created.candidate_id)

    current = store.get(created.candidate_id)

    assert current.status is MemoryCandidateStatus.PENDING_REVIEW
    assert current.disposition is None
    assert current.reviewed_at is None


def test_reject_rolls_back_memory_on_database_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)
    store = SQLiteMemoryCandidateStore(database)
    created = create_candidate(store, experience)

    @contextmanager
    def fail_transaction():
        raise RuntimeError("database write failed")
        yield

    monkeypatch.setattr(
        database,
        "transaction",
        fail_transaction,
    )

    with pytest.raises(RuntimeError):
        store.reject(
            created.candidate_id,
            MemoryCandidateDisposition.DISCARD,
        )

    current = store.get(created.candidate_id)

    assert current.status is MemoryCandidateStatus.PENDING_REVIEW
    assert current.disposition is None
    assert current.reviewed_at is None


def test_capacity_eviction_is_persisted(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)

    store = SQLiteMemoryCandidateStore(
        database,
        max_records=1,
    )
    first = create_candidate(store, experience)
    store.reject(
        first.candidate_id,
        MemoryCandidateDisposition.DISCARD,
    )

    second = store.create(
        candidate_id=(
            "memory_candidate_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        ),
        experience_id=experience.experience_id,
        verification_id=experience.verification_id,
        execution_id=experience.execution_id,
        review_id=experience.review_id,
        snapshot_digest=experience.snapshot_digest,
        lesson=MemoryCandidateLesson(
            category=LessonCategory.EXECUTION,
            observation="Execution failed.",
            lesson="Use a safer operation.",
            confidence=0.8,
        ),
        rationale=(
            "This reusable lesson may improve how future approved operations are performed."
        ),
        method=METHOD,
    )

    restored = SQLiteMemoryCandidateStore(
        database,
        max_records=1,
    )

    assert restored.list() == (second,)


def test_deleting_experience_cascades_candidate(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    _, _, experience = create_experience(database)

    store = SQLiteMemoryCandidateStore(database)
    created = create_candidate(store, experience)

    with database.transaction() as connection:
        connection.execute(
            """
            DELETE FROM experience_records
            WHERE experience_id = ?
            """,
            (experience.experience_id,),
        )

    restored = SQLiteMemoryCandidateStore(database)

    assert restored.list() == ()
    assert created.candidate_id not in {record.candidate_id for record in restored.list()}
