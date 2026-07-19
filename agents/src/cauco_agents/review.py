import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from cauco_agents.models import (
    AgentContext,
    AgentContextValue,
    AgentPlan,
    AgentRequest,
    AgentResult,
    AgentRouteResult,
)

APPROVAL_WARNING = "Approval authorizes the reviewed plan snapshot only. No action was executed."


class AgentPlanReviewStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class AgentPlanReviewRecord:
    review_id: str
    status: AgentPlanReviewStatus
    created_at: datetime
    expires_at: datetime
    updated_at: datetime
    instruction: str
    selected_agent_id: str
    routing: AgentRouteResult
    context: AgentContext
    plan: AgentPlan
    snapshot_digest: str
    execution_authorized: bool = False
    execution_performed: bool = False
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    cancelled_at: datetime | None = None
    expired_at: datetime | None = None
    reviewer_note: str | None = None
    rejection_reason: str | None = None
    cancellation_reason: str | None = None
    approval_warning: str | None = None
    metadata: Mapping[str, AgentContextValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"planrev_[A-Za-z0-9_-]{20,}", self.review_id):
            raise ValueError("Plan review ID must be an opaque URL-safe identifier.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.snapshot_digest):
            raise ValueError("Plan review snapshot digest must be a SHA-256 hex digest.")
        if self.execution_performed:
            raise ValueError("Plan review records cannot report performed execution.")
        if self.execution_authorized != (
            self.status is AgentPlanReviewStatus.APPROVED
        ):
            raise ValueError("Only approved plan reviews can authorize future execution.")
        if self.expires_at <= self.created_at or self.updated_at < self.created_at:
            raise ValueError("Plan review timestamps are inconsistent.")
        if self.instruction != self.context.instruction:
            raise ValueError("The reviewed instruction must match the resolved context.")
        if self.selected_agent_id != self.plan.agent_id:
            raise ValueError("The selected agent must match the reviewed plan.")
        if self.context.agent_id != self.selected_agent_id:
            raise ValueError("The reviewed context must match the selected agent.")
        if self.routing.selected_agent_id != self.selected_agent_id:
            raise ValueError("The reviewed routing must match the selected agent.")
        if self.status is AgentPlanReviewStatus.APPROVED:
            if self.approved_at is None or self.approval_warning != APPROVAL_WARNING:
                raise ValueError("Approved plan reviews require an approval timestamp and warning.")
        elif self.approved_at is not None or self.approval_warning is not None:
            raise ValueError("Only approved plan reviews can contain approval metadata.")
        if (self.status is AgentPlanReviewStatus.REJECTED) != (
            self.rejected_at is not None
        ):
            raise ValueError("Rejected plan review timestamps are inconsistent.")
        if (self.status is AgentPlanReviewStatus.REJECTED) != (
            self.rejection_reason is not None
        ):
            raise ValueError("Rejected plan reviews require a rejection reason.")
        if (self.status is AgentPlanReviewStatus.CANCELLED) != (
            self.cancelled_at is not None
        ):
            raise ValueError("Cancelled plan review timestamps are inconsistent.")
        if (
            self.status is not AgentPlanReviewStatus.CANCELLED
            and self.cancellation_reason is not None
        ):
            raise ValueError("Only cancelled plan reviews can contain a cancellation reason.")
        if (self.status is AgentPlanReviewStatus.EXPIRED) != (
            self.expired_at is not None
        ):
            raise ValueError("Expired plan review timestamps are inconsistent.")

        object.__setattr__(self, "routing", _copy_routing(self.routing))
        object.__setattr__(self, "context", _copy_context(self.context))
        object.__setattr__(self, "plan", _copy_plan(self.plan))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def _copy_routing(routing: AgentRouteResult) -> AgentRouteResult:
    request = AgentRequest(
        instruction=routing.request.instruction,
        intent=routing.request.intent,
        context=dict(routing.request.context),
        preferred_agent_id=routing.request.preferred_agent_id,
        allow_execution=routing.request.allow_execution,
    )
    result = None
    if routing.result is not None:
        result = AgentResult(
            agent_id=routing.result.agent_id,
            agent_name=routing.result.agent_name,
            status=routing.result.status,
            summary=routing.result.summary,
            proposed_actions=tuple(routing.result.proposed_actions),
            warnings=tuple(routing.result.warnings),
            requires_confirmation=routing.result.requires_confirmation,
            execution_performed=routing.result.execution_performed,
            metadata=dict(routing.result.metadata),
        )
    return AgentRouteResult(
        request=request,
        selected_agent_id=routing.selected_agent_id,
        selected_agent_name=routing.selected_agent_name,
        match=replace(routing.match) if routing.match is not None else None,
        matches=tuple(replace(match) for match in routing.matches),
        result=result,
        preferred_agent_rejected=routing.preferred_agent_rejected,
    )


def _copy_context(context: AgentContext) -> AgentContext:
    return AgentContext(
        agent_id=context.agent_id,
        instruction=context.instruction,
        resolved_intent=context.resolved_intent,
        memory_references=tuple(replace(reference) for reference in context.memory_references),
        context_summary=context.context_summary,
        limitations=tuple(context.limitations),
        metadata=dict(context.metadata),
    )


def _copy_plan(plan: AgentPlan) -> AgentPlan:
    return AgentPlan(
        agent_id=plan.agent_id,
        agent_name=plan.agent_name,
        status=plan.status,
        objective=plan.objective,
        context_used=plan.context_used,
        steps=tuple(replace(step) for step in plan.steps),
        open_questions=tuple(plan.open_questions),
        warnings=tuple(plan.warnings),
        requires_confirmation=plan.requires_confirmation,
        execution_performed=plan.execution_performed,
        metadata=dict(plan.metadata),
    )
