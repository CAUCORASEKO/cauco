from dataclasses import FrozenInstanceError

import pytest

from cauco_core.execution.models import (
    AgentPlanStepExecutionRecord,
    ExecutionCapacityError,
    ExecutionConflictError,
    StepExecutionStatus,
)
from cauco_core.execution.store import ExecutionStore


def step() -> AgentPlanStepExecutionRecord:
    return AgentPlanStepExecutionRecord(
        step_index=1,
        tool_id="git",
        operation_id="status",
        target=None,
        status=StepExecutionStatus.PENDING,
    )


def test_store_capacity_duplicate_review_ordering_and_immutability() -> None:
    store = ExecutionStore(max_records=1)
    first = store.create("planrev_abcdefghijklmnopqrstuvwx", "0" * 64, (step(),))
    with pytest.raises(FrozenInstanceError):
        first.status = "failed"  # type: ignore[misc]
    with pytest.raises(ExecutionConflictError):
        store.create(first.review_id, "0" * 64, (step(),))
    with pytest.raises(ExecutionCapacityError):
        store.create("planrev_zyxwvutsrqponmlkjihgfedc", "1" * 64, (step(),))

    store.cancel(first.execution_id)
    second = store.create("planrev_zyxwvutsrqponmlkjihgfedc", "1" * 64, (step(),))
    assert store.list()[0].execution_id == second.execution_id
