from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cauco_tools import ToolExecutionResult

from cauco_core.execution.models import (
    AgentPlanStepExecutionRecord,
    ExecutionCapacityError,
    ExecutionConflictError,
    ExecutionStatus,
    StepExecutionStatus,
)
from cauco_core.execution.sqlite_store import SQLiteExecutionStore
from cauco_core.persistence import SQLiteDatabase


def pending_step(
    *,
    step_index: int = 1,
    operation_id: str = "status",
) -> AgentPlanStepExecutionRecord:
    return AgentPlanStepExecutionRecord(
        step_index=step_index,
        tool_id="git",
        operation_id=operation_id,
        target=None,
        status=StepExecutionStatus.PENDING,
    )


def create_store(
    path: Path,
    *,
    max_records: int = 100,
) -> SQLiteExecutionStore:
    return SQLiteExecutionStore(
        SQLiteDatabase(path),
        max_records=max_records,
    )


def test_execution_survives_store_restart(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    first_store = create_store(path)

    created = first_store.create(
        "planrev_abcdefghijklmnopqrstuvwx",
        "0" * 64,
        (pending_step(),),
    )
    first_store.append_event(
        created.execution_id,
        "integrity_verified",
        "success",
        "Approved snapshot integrity verified.",
    )

    second_store = create_store(path)
    restored = second_store.get(created.execution_id)

    assert restored == first_store.get(created.execution_id)
    assert restored.status is ExecutionStatus.PENDING_EXECUTION
    assert restored.step_records[0].status is StepExecutionStatus.PENDING
    assert [event.event_type for event in restored.audit_events] == [
        "execution_created",
        "integrity_verified",
    ]


def test_completed_tool_result_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    store = create_store(path)

    created = store.create(
        "planrev_abcdefghijklmnopqrstuvwx",
        "1" * 64,
        (pending_step(),),
    )
    running = store.start_step(created.execution_id, 1)

    started_at = running.step_records[0].started_at
    assert started_at is not None
    completed_at = started_at + timedelta(milliseconds=12)

    result = ToolExecutionResult(
        tool_id="git",
        operation_id="status",
        success=True,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=12,
        output="working tree clean",
        structured_data={
            "branch": "main",
            "clean": True,
            "paths": ["core", "tools"],
        },
        truncated=False,
        execution_performed=True,
        mutation_performed=False,
    )

    finished = store.finish_step(
        created.execution_id,
        1,
        result=result,
        error=None,
        performed=True,
    )

    restored = create_store(path).get(created.execution_id)
    restored_step = restored.step_records[0]

    assert finished.status is ExecutionStatus.COMPLETED
    assert restored.status is ExecutionStatus.COMPLETED
    assert restored.execution_performed is True
    assert restored_step.status is StepExecutionStatus.COMPLETED
    assert restored_step.result == result
    assert restored_step.result is not None
    assert restored_step.result.structured_data["branch"] == "main"
    assert restored_step.result.structured_data["paths"] == ("core", "tools")


def test_failed_result_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    store = create_store(path)

    created = store.create(
        "planrev_abcdefghijklmnopqrstuvwx",
        "2" * 64,
        (pending_step(),),
    )
    running = store.start_step(created.execution_id, 1)
    started_at = running.step_records[0].started_at
    assert started_at is not None

    result = ToolExecutionResult(
        tool_id="git",
        operation_id="status",
        success=False,
        started_at=started_at,
        completed_at=started_at,
        duration_ms=0,
        output="",
        error_code="safe_failure",
        error_message="Operation failed safely.",
        execution_performed=True,
    )

    store.finish_step(
        created.execution_id,
        1,
        result=result,
        error=result.error_message,
        performed=True,
    )

    restored = create_store(path).get(created.execution_id)

    assert restored.status is ExecutionStatus.FAILED
    assert restored.failure_reason == "Operation failed safely."
    assert restored.step_records[0].result == result


def test_cancelled_execution_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    store = create_store(path)

    created = store.create(
        "planrev_abcdefghijklmnopqrstuvwx",
        "3" * 64,
        (pending_step(),),
    )
    store.cancel(created.execution_id)

    restored = create_store(path).get(created.execution_id)

    assert restored.status is ExecutionStatus.CANCELLED
    assert restored.step_records[0].status is StepExecutionStatus.CANCELLED
    assert restored.completed_at is not None


def test_duplicate_review_is_rejected_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    first_store = create_store(path)

    first_store.create(
        "planrev_abcdefghijklmnopqrstuvwx",
        "4" * 64,
        (pending_step(),),
    )

    second_store = create_store(path)

    with pytest.raises(ExecutionConflictError):
        second_store.create(
            "planrev_abcdefghijklmnopqrstuvwx",
            "5" * 64,
            (pending_step(),),
        )


def test_terminal_record_is_evicted_persistently_for_capacity(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    store = create_store(path, max_records=1)

    first = store.create(
        "planrev_abcdefghijklmnopqrstuvwx",
        "6" * 64,
        (pending_step(),),
    )
    store.cancel(first.execution_id)

    second = store.create(
        "planrev_zyxwvutsrqponmlkjihgfedc",
        "7" * 64,
        (pending_step(),),
    )

    restored_store = create_store(path, max_records=1)

    assert restored_store.list()[0].execution_id == second.execution_id
    assert len(restored_store.list()) == 1


def test_active_capacity_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    store = create_store(path, max_records=1)

    store.create(
        "planrev_abcdefghijklmnopqrstuvwx",
        "8" * 64,
        (pending_step(),),
    )

    with pytest.raises(ExecutionCapacityError):
        store.create(
            "planrev_zyxwvutsrqponmlkjihgfedc",
            "9" * 64,
            (pending_step(),),
        )

    restored = create_store(path, max_records=1)

    assert len(restored.list()) == 1


def test_rejected_audit_events_are_bounded_and_persistent(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    store = create_store(path)

    for index in range(105):
        store.record_rejected_attempt(
            f"planrev_{index:024d}",
            "Execution creation was rejected.",
        )

    restored = create_store(path)

    assert len(restored._rejected_events) == 100
    assert restored._rejected_events[-1].review_id == "planrev_000000000000000000000104"


def test_list_filters_and_order_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "cauco.db"
    moments = iter(
        [
            datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
            datetime(2026, 7, 20, 8, 1, tzinfo=UTC),
            datetime(2026, 7, 20, 8, 2, tzinfo=UTC),
            datetime(2026, 7, 20, 8, 3, tzinfo=UTC),
            datetime(2026, 7, 20, 8, 4, tzinfo=UTC),
            datetime(2026, 7, 20, 8, 5, tzinfo=UTC),
        ]
    )
    database = SQLiteDatabase(path)
    store = SQLiteExecutionStore(database, clock=lambda: next(moments))

    first = store.create(
        "planrev_abcdefghijklmnopqrstuvwx",
        "a" * 64,
        (pending_step(),),
    )
    second = store.create(
        "planrev_zyxwvutsrqponmlkjihgfedc",
        "b" * 64,
        (pending_step(),),
    )

    restored = create_store(path)

    assert [item.execution_id for item in restored.list()] == [
        second.execution_id,
        first.execution_id,
    ]
    assert restored.list(review_id=first.review_id) == (restored.get(first.execution_id),)
    assert len(restored.list(status=ExecutionStatus.PENDING_EXECUTION)) == 2
