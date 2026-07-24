from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.execution.models import (
    AgentPlanStepExecutionRecord,
    StepExecutionStatus,
)
from cauco_core.learning.models import (
    ExperienceOutcome,
    LessonCandidate,
    LessonCategory,
)
from cauco_core.main import create_app
from cauco_core.memory_candidates.models import (
    MemoryCandidateDisposition,
    MemoryCandidateStatus,
)
from cauco_core.memory_candidates.sqlite_store import (
    SQLiteMemoryCandidateStore,
)
from cauco_core.verification import (
    StepVerificationResult,
    VerificationOutcome,
    VerificationRecommendation,
)


def test_memory_candidate_and_review_survive_app_restart(
    tmp_path: Path,
) -> None:
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
            first_app.state.memory_candidate_store,
            SQLiteMemoryCandidateStore,
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

        verification = first_app.state.verification_store.create(
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

        experience = first_app.state.experience_store.create(
            verification_id=verification.verification_id,
            execution_id=execution.execution_id,
            review_id=execution.review_id,
            snapshot_digest=execution.snapshot_digest,
            outcome=ExperienceOutcome.SUCCESS,
            summary="The execution produced reusable learning.",
            recommendation="Retain reusable lessons.",
            lesson_candidates=(
                LessonCandidate(
                    category=LessonCategory.PLANNING,
                    observation="A required precondition was omitted.",
                    lesson="Validate required preconditions first.",
                    confidence=0.9,
                    reusable=True,
                ),
            ),
            method="test",
        )

        candidates = first_app.state.memory_candidate_service.create_for_experience(
            experience.experience_id
        )
        created = candidates[0]

        reviewed = first_app.state.memory_candidate_store.reject(
            created.candidate_id,
            MemoryCandidateDisposition.RETAIN_AS_EXPERIENCE_ONLY,
            "Keep as experience only.",
        )

    second_app = create_app(settings)

    with TestClient(second_app):
        restored = second_app.state.memory_candidate_store.get(
            created.candidate_id,
        )

        assert restored == reviewed
        assert restored.status is MemoryCandidateStatus.REJECTED
        assert restored.disposition is MemoryCandidateDisposition.RETAIN_AS_EXPERIENCE_ONLY
        assert restored.review_note == "Keep as experience only."

        by_experience = second_app.state.memory_candidate_store.for_experience(
            experience.experience_id
        )

        assert by_experience == (restored,)
