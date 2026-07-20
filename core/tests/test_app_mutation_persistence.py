from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.execution.models import AgentPlanStepExecutionRecord, StepExecutionStatus
from cauco_core.main import create_app
from cauco_core.mutations.models import MutationPreviewStatus
from cauco_core.mutations.sqlite_store import SQLiteMutationPreviewStore


def test_create_app_restores_mutation_preview_after_restart(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    database_path = tmp_path / "runtime" / "cauco.db"

    settings = Settings(
        brain_dir=brain,
        database_path=database_path,
    )

    first_app = create_app(settings)

    with TestClient(first_app):
        assert isinstance(
            first_app.state.mutation_preview_store,
            SQLiteMutationPreviewStore,
        )

        execution = first_app.state.execution_store.create(
            "planrev_abcdefghijklmnopqrstuvwx",
            "0" * 64,
            (
                AgentPlanStepExecutionRecord(
                    step_index=1,
                    tool_id="filesystem",
                    operation_id="write_text_file",
                    target="notes.txt",
                    status=StepExecutionStatus.PENDING,
                ),
            ),
        )

        created = first_app.state.mutation_preview_store.create(
            execution_id=execution.execution_id,
            review_id=execution.review_id,
            step_index=1,
            tool_id="filesystem",
            operation_id="write_text_file",
            target="notes.txt",
            normalized_arguments={
                "relative_path": "notes.txt",
                "content": "persistent application preview",
            },
            before_state={
                "exists": False,
            },
            proposed_after_state={
                "exists": True,
                "characters": 30,
            },
            diff_preview="+persistent application preview",
            preview_digest="a" * 64,
            confirmation_phrase="WRITE WORKSPACE FILE",
        )

        assert created.status is MutationPreviewStatus.PENDING_CONFIRMATION

    second_app = create_app(settings)

    with TestClient(second_app):
        assert isinstance(
            second_app.state.mutation_preview_store,
            SQLiteMutationPreviewStore,
        )

        restored = second_app.state.mutation_preview_store.get(created.preview_id)
        active = second_app.state.mutation_preview_store.active(
            execution.execution_id,
            1,
        )

        assert restored.preview_id == created.preview_id
        assert restored.execution_id == execution.execution_id
        assert restored.review_id == execution.review_id
        assert restored.status is MutationPreviewStatus.PENDING_CONFIRMATION
        assert restored.normalized_arguments["content"] == ("persistent application preview")
        assert active.preview_id == created.preview_id
