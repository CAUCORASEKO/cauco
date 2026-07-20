from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.execution.models import (
    AgentPlanStepExecutionRecord,
    ExecutionStatus,
    StepExecutionStatus,
)
from cauco_core.execution.sqlite_store import SQLiteExecutionStore
from cauco_core.main import create_app


def test_create_app_restores_execution_after_restart(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    database_path = tmp_path / "runtime" / "cauco.db"

    settings = Settings(
        brain_dir=brain,
        database_path=database_path,
    )

    first_app = create_app(settings)

    with TestClient(first_app):
        assert isinstance(first_app.state.execution_store, SQLiteExecutionStore)
        assert first_app.state.database.path == database_path.resolve()

        created = first_app.state.execution_store.create(
            "planrev_abcdefghijklmnopqrstuvwx",
            "0" * 64,
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
        first_app.state.execution_store.append_event(
            created.execution_id,
            "integration_test",
            "success",
            "Execution persisted before application restart.",
        )

    second_app = create_app(settings)

    with TestClient(second_app):
        restored = second_app.state.execution_store.get(created.execution_id)

        assert restored.execution_id == created.execution_id
        assert restored.review_id == created.review_id
        assert restored.status is ExecutionStatus.PENDING_EXECUTION
        assert restored.step_records[0].status is StepExecutionStatus.PENDING
        assert [event.event_type for event in restored.audit_events] == [
            "execution_created",
            "integration_test",
        ]
