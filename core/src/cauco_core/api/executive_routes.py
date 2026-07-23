from __future__ import annotations

from cauco_agents import AgentPlanReviewStatus
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from cauco_core.execution.models import ExecutionStatus
from cauco_core.executive import (
    ExecutiveControlService,
    ExecutiveState,
    IntentStatus,
)

router = APIRouter(prefix="/api/executive", tags=["executive"])


class ExecutiveApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutiveDecisionRequest(ExecutiveApiModel):
    intent_status: IntentStatus
    perception_available: StrictBool = False
    plan_available: StrictBool = False
    review_status: AgentPlanReviewStatus | None = None
    execution_status: ExecutionStatus | None = None
    execution_record_available: StrictBool = False
    execution_performed: StrictBool = False
    outcome_verified: StrictBool = False
    verification_succeeded: StrictBool | None = None


class ExecutiveDecisionResponse(ExecutiveApiModel):
    next_action: str
    requires_human_approval: bool
    transition_permitted: bool
    reason: str
    blocking_reasons: list[str] = Field(default_factory=list)


def _service(request: Request) -> ExecutiveControlService:
    service = getattr(request.app.state, "executive_control_service", None)
    if not isinstance(service, ExecutiveControlService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Executive control service is unavailable.",
        )
    return service


@router.post(
    "/decide",
    response_model=ExecutiveDecisionResponse,
    status_code=status.HTTP_200_OK,
)
def decide(
    payload: ExecutiveDecisionRequest,
    request: Request,
) -> ExecutiveDecisionResponse:
    try:
        state = ExecutiveState(
            intent_status=payload.intent_status,
            perception_available=payload.perception_available,
            plan_available=payload.plan_available,
            review_status=payload.review_status,
            execution_status=payload.execution_status,
            execution_record_available=payload.execution_record_available,
            execution_performed=payload.execution_performed,
            outcome_verified=payload.outcome_verified,
            verification_succeeded=payload.verification_succeeded,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    decision = _service(request).decide(state)

    return ExecutiveDecisionResponse(
        next_action=decision.next_action.value,
        requires_human_approval=decision.requires_human_approval,
        transition_permitted=decision.transition_permitted,
        reason=decision.reason,
        blocking_reasons=list(decision.blocking_reasons),
    )
