from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cauco_core.execution.models import (
    AgentPlanStepExecutionRecord,
    StepExecutionStatus,
)
from cauco_core.execution.sqlite_store import SQLiteExecutionStore
from cauco_core.persistence import SQLiteDatabase
from cauco_core.verification import (
    SQLiteVerificationStore,
    StepVerificationResult,
    VerificationConflictError,
    VerificationOutcome,
    VerificationRecommendation,
)


def clock_at(value: datetime):
    return lambda: value


def pending_execution_step() -> AgentPlanStepExecutionRecord:
    return AgentPlanStepExecutionRecord(
        step_index=1,
        tool_id="git",
        operation_id="status",
        target=None,
        status=StepExecutionStatus.PENDING,
    )


def verification_step(
    *,
    index: int = 1,
    outcome: VerificationOutcome = VerificationOutcome.SUCCEEDED,
) -> StepVerificationResult:
    return StepVerificationResult(
        step_index=index,
        tool_id="git",
        operation_id="status",
        outcome=outcome,
        method="direct observation",
        expected_conditions=("expected",),
        observed_conditions=("observed",),
        evidence_references=("evidence://step",),
        deviations=(),
        unresolved_conditions=(),
        rollback_available=True,
    )


def create_execution(
    database: SQLiteDatabase,
    *,
    review_id: str,
    snapshot_digest: str,
):
    return SQLiteExecutionStore(database).create(
        review_id,
        snapshot_digest,
        (pending_execution_step(),),
    )


def create_verification(
    store: SQLiteVerificationStore,
    *,
    execution_id: str,
    review_id: str,
    snapshot_digest: str,
    outcome: VerificationOutcome = VerificationOutcome.SUCCEEDED,
):
    return store.create(
        execution_id=execution_id,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
        outcome=outcome,
        recommendation=VerificationRecommendation.COMPLETE,
        method="post-execution verification",
        step_results=(verification_step(outcome=outcome),),
        evidence_references=("evidence://record",),
        deviations=("minor deviation",),
        unresolved_conditions=("follow-up",),
        rollback_available=True,
    )


def test_record_survives_store_restart(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    created_at = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)
    review_id = "planrev_abcdefghijklmnopqrstuvwx"
    snapshot_digest = "a" * 64

    execution = create_execution(
        database,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
    )

    store = SQLiteVerificationStore(
        database,
        clock=clock_at(created_at),
    )
    created = create_verification(
        store,
        execution_id=execution.execution_id,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
    )

    restored_store = SQLiteVerificationStore(database)
    restored = restored_store.get(created.verification_id)

    assert restored == created
    assert restored.created_at == created_at
    assert restored_store.for_execution(created.execution_id) == created
    assert restored.metadata == {}


def test_duplicate_execution_is_rejected_after_restart(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    review_id = "planrev_abcdefghijklmnopqrstuvwx"
    snapshot_digest = "b" * 64

    execution = create_execution(
        database,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
    )

    create_verification(
        SQLiteVerificationStore(database),
        execution_id=execution.execution_id,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
    )

    restored_store = SQLiteVerificationStore(database)

    with pytest.raises(
        VerificationConflictError,
        match="already exists",
    ):
        create_verification(
            restored_store,
            execution_id=execution.execution_id,
            review_id=review_id,
            snapshot_digest=snapshot_digest,
        )


def test_list_filters_and_orders_newest_first(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    start = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)

    first_review_id = "planrev_abcdefghijklmnopqrstuvwx"
    second_review_id = "planrev_zyxwvutsrqponmlkjihgfedc"

    first_execution = create_execution(
        database,
        review_id=first_review_id,
        snapshot_digest="c" * 64,
    )
    second_execution = create_execution(
        database,
        review_id=second_review_id,
        snapshot_digest="d" * 64,
    )

    first = create_verification(
        SQLiteVerificationStore(database, clock=clock_at(start)),
        execution_id=first_execution.execution_id,
        review_id=first_review_id,
        snapshot_digest="c" * 64,
        outcome=VerificationOutcome.FAILED,
    )
    second = create_verification(
        SQLiteVerificationStore(
            database,
            clock=clock_at(start + timedelta(minutes=1)),
        ),
        execution_id=second_execution.execution_id,
        review_id=second_review_id,
        snapshot_digest="d" * 64,
    )

    store = SQLiteVerificationStore(database)

    assert store.list() == (second, first)
    assert store.list(review_id=first_review_id) == (first,)
    assert store.list(outcome=VerificationOutcome.SUCCEEDED) == (second,)


def test_capacity_evicts_oldest_record_from_memory_and_sqlite(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")
    start = datetime(2026, 7, 24, 10, 0, tzinfo=UTC)

    executions = [
        create_execution(
            database,
            review_id=review_id,
            snapshot_digest=digest * 64,
        )
        for review_id, digest in (
            ("planrev_abcdefghijklmnopqrstuvwx", "e"),
            ("planrev_zyxwvutsrqponmlkjihgfedc", "f"),
            ("planrev_mnopqrstuvwxyzabcdefghij", "1"),
        )
    ]

    first_store = SQLiteVerificationStore(
        database,
        max_records=2,
        clock=clock_at(start),
    )
    first = create_verification(
        first_store,
        execution_id=executions[0].execution_id,
        review_id=executions[0].review_id,
        snapshot_digest=executions[0].snapshot_digest,
    )

    second_store = SQLiteVerificationStore(
        database,
        max_records=2,
        clock=clock_at(start + timedelta(minutes=1)),
    )
    second = create_verification(
        second_store,
        execution_id=executions[1].execution_id,
        review_id=executions[1].review_id,
        snapshot_digest=executions[1].snapshot_digest,
    )

    third_store = SQLiteVerificationStore(
        database,
        max_records=2,
        clock=clock_at(start + timedelta(minutes=2)),
    )
    third = create_verification(
        third_store,
        execution_id=executions[2].execution_id,
        review_id=executions[2].review_id,
        snapshot_digest=executions[2].snapshot_digest,
    )

    restored = SQLiteVerificationStore(database, max_records=2)

    assert restored.list() == (third, second)
    assert first.verification_id not in {record.verification_id for record in restored.list()}


def test_sqlite_failure_restores_in_memory_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SQLiteDatabase(tmp_path / "cauco.db")

    first_execution = create_execution(
        database,
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="2" * 64,
    )
    second_execution = create_execution(
        database,
        review_id="planrev_zyxwvutsrqponmlkjihgfedc",
        snapshot_digest="3" * 64,
    )

    store = SQLiteVerificationStore(database, max_records=1)

    original = create_verification(
        store,
        execution_id=first_execution.execution_id,
        review_id=first_execution.review_id,
        snapshot_digest=first_execution.snapshot_digest,
    )

    def fail_persist(*args, **kwargs):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(store, "_persist_record", fail_persist)

    with pytest.raises(RuntimeError, match="database write failed"):
        create_verification(
            store,
            execution_id=second_execution.execution_id,
            review_id=second_execution.review_id,
            snapshot_digest=second_execution.snapshot_digest,
        )

    assert store.list() == (original,)
    assert store.for_execution(original.execution_id) == original

    restored = SQLiteVerificationStore(database, max_records=1)
    assert restored.list() == (original,)
