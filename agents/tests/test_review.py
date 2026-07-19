from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from cauco_agents import (
    AgentContext,
    AgentPlanReviewRecord,
    AgentPlanReviewStatus,
    AgentRequest,
    AgentRouter,
    ProjectAgent,
    create_default_registry,
)


def review_record() -> AgentPlanReviewRecord:
    instruction = "Plan the Cauco project"
    routing = AgentRouter(create_default_registry()).route(AgentRequest(instruction))
    context = AgentContext(
        agent_id="project",
        instruction=instruction,
        resolved_intent="planning",
        memory_references=(),
        context_summary="No test memory.",
        limitations=("Memory is inert.",),
    )
    plan = ProjectAgent().plan(context)
    now = datetime(2026, 7, 19, 10, 0, tzinfo=UTC)
    return AgentPlanReviewRecord(
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        status=AgentPlanReviewStatus.PENDING_REVIEW,
        created_at=now,
        expires_at=now + timedelta(minutes=30),
        updated_at=now,
        instruction=instruction,
        selected_agent_id="project",
        routing=routing,
        context=context,
        plan=plan,
        snapshot_digest="0" * 64,
    )


def test_plan_review_record_is_immutable_and_pending_by_contract() -> None:
    record = review_record()

    assert record.status is AgentPlanReviewStatus.PENDING_REVIEW
    assert record.execution_authorized is False
    assert record.execution_performed is False
    with pytest.raises(FrozenInstanceError):
        record.status = AgentPlanReviewStatus.APPROVED  # type: ignore[misc]
    with pytest.raises(TypeError):
        record.metadata["forged"] = True  # type: ignore[index]


def test_plan_review_record_rejects_execution_and_invalid_authorization() -> None:
    record = review_record()
    values = {
        field: getattr(record, field)
        for field in record.__dataclass_fields__  # type: ignore[attr-defined]
    }
    values["execution_performed"] = True
    with pytest.raises(ValueError, match="performed execution"):
        AgentPlanReviewRecord(**values)

    values["execution_performed"] = False
    values["execution_authorized"] = True
    with pytest.raises(ValueError, match="Only approved"):
        AgentPlanReviewRecord(**values)
