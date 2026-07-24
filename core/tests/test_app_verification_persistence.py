from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.execution.models import (
    AgentPlanStepExecutionRecord,
    StepExecutionStatus,
)
from cauco_core.main import create_app
from cauco_core.verification import (
    SQLiteVerificationStore,
    StepVerificationResult,
    VerificationOutcome,
    VerificationRecommendation,
)


def test_create_app_restores_verification_after_restart(tmp_path: Path) -> None:
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
            first_app.state.verification_store,
            SQLiteVerificationStore,
        )

        execution = first_app.state.execution_store.create(
            "planrev_abcdefghijklmnopqrstuvwx",
            "a" * 64,
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

        created = first_app.state.verification_store.create(
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
                    observed_conditions=("Git status was observed.",),
                    evidence_references=("execution-step:1:git:status",),
                    rollback_available=False,
                ),
            ),
            evidence_references=("execution-step:1:git:status",),
            rollback_available=False,
        )

    second_app = create_app(settings)

    with TestClient(second_app):
        restored = second_app.state.verification_store.get(
            created.verification_id,
        )

        assert restored == created
        assert restored.execution_id == execution.execution_id
        assert restored.review_id == execution.review_id
        assert restored.outcome is VerificationOutcome.SUCCEEDED
        assert restored.recommendation is VerificationRecommendation.COMPLETE
        assert restored.metadata == {}

        by_execution = second_app.state.verification_store.for_execution(
            execution.execution_id,
        )
        assert by_execution == created
