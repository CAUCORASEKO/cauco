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
    ExperienceConflictError,
    ExperienceNotFoundError,
    ExperienceOutcome,
    LessonCandidate,
    LessonCategory,
)
from cauco_core.learning.sqlite_store import SQLiteExperienceStore
from cauco_core.persistence import SQLiteDatabase
from cauco_core.verification import (
    SQLiteVerificationStore,
    StepVerificationResult,
    VerificationOutcome,
    VerificationRecommendation,
)


def clock_at(value: datetime):
    return lambda: value


def lesson() -> LessonCandidate:
    return LessonCandidate(
        category=LessonCategory.VERIFICATION,
        observation="Evidence was unavailable.",
        lesson="Plans should include explicit verification.",
        confidence=0.95,
        reusable=True,
        tool_id="git",
        operation_id="status",
        step_index=1,
    )


def create_verification(
    database: SQLiteDatabase,
    *,
    review_id: str,
    snapshot_digest: str,
):
    execution = SQLiteExecutionStore(database).create(
        review_id,
        snapshot_digest,
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

    verification = SQLiteVerificationStore(database).create(
        execution_id=execution.execution_id,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
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

    return execution, verification


def create_experience(
    store: SQLiteExperienceStore,
    *,
    verification_id: str,
    execution_id: str,
    review_id: str,
    snapshot_digest: str,
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    lesson_candidates: tuple[LessonCandidate, ...] = (),
):
    return store.create(
        verification_id=verification_id,
        execution_id=execution_id,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
        outcome=outcome,
        summary="Consolidated experience.",
        lesson_candidates=lesson_candidates,
        recommendation="complete",
        method="test_consolidation",
    )


def test_experience_survives_store_restart(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    created_at = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    review_id = "planrev_abcdefghijklmnopqrstuvwx"
    snapshot_digest = "a" * 64

    execution, verification = create_verification(
        database,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
    )

    created = create_experience(
        SQLiteExperienceStore(database, clock=clock_at(created_at)),
        verification_id=verification.verification_id,
        execution_id=execution.execution_id,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
        outcome=ExperienceOutcome.INCONCLUSIVE,
        lesson_candidates=(lesson(),),
    )

    restored_store = SQLiteExperienceStore(database)
    restored = restored_store.get(created.experience_id)

    assert restored == created
    assert restored.created_at == created_at
    assert restored_store.for_verification(verification.verification_id) == created
    assert restored.memory_candidate is True


def test_duplicate_verification_is_rejected_after_restart(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    review_id = "planrev_abcdefghijklmnopqrstuvwx"
    snapshot_digest = "b" * 64

    execution, verification = create_verification(
        database,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
    )

    create_experience(
        SQLiteExperienceStore(database),
        verification_id=verification.verification_id,
        execution_id=execution.execution_id,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
    )

    restored_store = SQLiteExperienceStore(database)

    with pytest.raises(ExperienceConflictError, match="already exists"):
        create_experience(
            restored_store,
            verification_id=verification.verification_id,
            execution_id=execution.execution_id,
            review_id=review_id,
            snapshot_digest=snapshot_digest,
        )


def test_list_filters_and_orders_newest_first(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    start = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)

    first_execution, first_verification = create_verification(
        database,
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="c" * 64,
    )
    second_execution, second_verification = create_verification(
        database,
        review_id="planrev_zyxwvutsrqponmlkjihgfedc",
        snapshot_digest="d" * 64,
    )

    first = create_experience(
        SQLiteExperienceStore(database, clock=clock_at(start)),
        verification_id=first_verification.verification_id,
        execution_id=first_execution.execution_id,
        review_id=first_execution.review_id,
        snapshot_digest=first_execution.snapshot_digest,
    )

    second = create_experience(
        SQLiteExperienceStore(
            database,
            clock=clock_at(start + timedelta(minutes=1)),
        ),
        verification_id=second_verification.verification_id,
        execution_id=second_execution.execution_id,
        review_id=second_execution.review_id,
        snapshot_digest=second_execution.snapshot_digest,
        outcome=ExperienceOutcome.FAILURE,
        lesson_candidates=(lesson(),),
    )

    store = SQLiteExperienceStore(database)

    assert store.list() == (second, first)
    assert store.list(review_id=first.review_id) == (first,)
    assert store.list(outcome=ExperienceOutcome.FAILURE) == (second,)
    assert store.list(memory_candidate=True) == (second,)
    assert store.list(memory_candidate=False) == (first,)


def test_capacity_eviction_is_persisted(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    start = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    records = []

    for index, (review_id, digest) in enumerate(
        (
            ("planrev_abcdefghijklmnopqrstuvwx", "e"),
            ("planrev_zyxwvutsrqponmlkjihgfedc", "f"),
            ("planrev_mnopqrstuvwxyzabcdefghij", "1"),
        )
    ):
        execution, verification = create_verification(
            database,
            review_id=review_id,
            snapshot_digest=digest * 64,
        )

        record = create_experience(
            SQLiteExperienceStore(
                database,
                max_records=2,
                clock=clock_at(start + timedelta(minutes=index)),
            ),
            verification_id=verification.verification_id,
            execution_id=execution.execution_id,
            review_id=review_id,
            snapshot_digest=digest * 64,
        )
        records.append(record)

    restored = SQLiteExperienceStore(database, max_records=2)

    assert restored.list() == (records[2], records[1])

    with pytest.raises(ExperienceNotFoundError):
        restored.get(records[0].experience_id)


def test_sqlite_failure_restores_in_memory_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")

    first_execution, first_verification = create_verification(
        database,
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="2" * 64,
    )
    second_execution, second_verification = create_verification(
        database,
        review_id="planrev_zyxwvutsrqponmlkjihgfedc",
        snapshot_digest="3" * 64,
    )

    store = SQLiteExperienceStore(database, max_records=1)

    original = create_experience(
        store,
        verification_id=first_verification.verification_id,
        execution_id=first_execution.execution_id,
        review_id=first_execution.review_id,
        snapshot_digest=first_execution.snapshot_digest,
    )

    @contextmanager
    def fail_transaction():
        raise RuntimeError("database write failed")
        yield

    monkeypatch.setattr(database, "transaction", fail_transaction)

    with pytest.raises(RuntimeError, match="database write failed"):
        create_experience(
            store,
            verification_id=second_verification.verification_id,
            execution_id=second_execution.execution_id,
            review_id=second_execution.review_id,
            snapshot_digest=second_execution.snapshot_digest,
        )

    assert store.list() == (original,)
    assert store.for_verification(original.verification_id) == original


def test_deleting_verification_cascades_experience(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    execution, verification = create_verification(
        database,
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="4" * 64,
    )

    experience = create_experience(
        SQLiteExperienceStore(database),
        verification_id=verification.verification_id,
        execution_id=execution.execution_id,
        review_id=execution.review_id,
        snapshot_digest=execution.snapshot_digest,
    )

    with database.transaction() as connection:
        connection.execute(
            """
            DELETE FROM verification_records
            WHERE verification_id = ?
            """,
            (verification.verification_id,),
        )

    restored = SQLiteExperienceStore(database)

    with pytest.raises(ExperienceNotFoundError):
        restored.get(experience.experience_id)
