from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.agents.sqlite_store import SQLiteAgentPlanReviewStore
from cauco_agents import AgentContextRequest
from cauco_core.config import Settings
from cauco_core.main import create_app


def test_app_restores_review_and_approval_without_execution(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    settings = Settings(brain_dir=brain, database_path=tmp_path / "runtime" / "cauco.db")
    first = create_app(settings)
    with TestClient(first):
        assert isinstance(first.state.agent_plan_review_store, SQLiteAgentPlanReviewStore)
        record = first.state.agent_plan_review_service.create(
            AgentContextRequest(instruction="Plan the Cauco project")
        )

    second = create_app(settings)
    with TestClient(second):
        restored = second.state.agent_plan_review_store.get(record.review_id)
        assert restored.status.value == "pending_review"
        approved = second.state.agent_plan_review_store.approve(record.review_id)
        execution = second.state.execution_store.create(approved.review_id, approved.snapshot_digest, ())
        assert execution.execution_performed is False
        assert execution.step_records == ()

    third = create_app(settings)
    with TestClient(third):
        assert third.state.agent_plan_review_store.get(record.review_id).status.value == "approved"
