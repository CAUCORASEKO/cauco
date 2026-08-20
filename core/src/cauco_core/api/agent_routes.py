from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, TypeAlias

from cauco_agents import (
    DEFAULT_MAX_CONTEXT_ITEMS,
    DEFAULT_MAX_EXCERPT_CHARS,
    MAX_CONTEXT_ITEMS,
    MAX_EXCERPT_CHARS,
    MIN_EXCERPT_CHARS,
    AgentContext,
    AgentContextRequest,
    AgentMatch,
    AgentMetadata,
    AgentPlan,
    AgentPlanReviewRecord,
    AgentPlanReviewStatus,
    AgentPlanStep,
    AgentRequest,
    AgentResult,
    AgentRouter,
    AgentRouteResult,
    AgentToolReference,
    UnknownPreferredAgentError,
)
from cauco_tools import ToolAdapterRegistry, ToolRegistry
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints

from cauco_core.agents.planning import AgentNotRelevantError, AgentPlanningOutcome
from cauco_core.agents.readiness import evaluate_plan_readiness
from cauco_core.agents.review_service import PlanReviewNoMatchError
from cauco_core.agents.review_store import (
    MAX_PLAN_REVIEW_TTL_SECONDS,
    MAX_REVIEW_REASON_CHARS,
    MAX_REVIEWER_NOTE_CHARS,
    MIN_PLAN_REVIEW_TTL_SECONDS,
    PlanReviewCapacityError,
    PlanReviewIntegrityError,
    PlanReviewNotFoundError,
    PlanReviewStateConflictError,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])
JsonScalar: TypeAlias = str | int | float | bool | None


class AgentApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRouteRequest(AgentApiModel):
    instruction: str = Field(max_length=4000)
    intent: str | None = Field(default=None, max_length=100)
    context: dict[str, JsonScalar] = Field(default_factory=dict, max_length=20)
    preferred_agent_id: str | None = Field(default=None, max_length=100)
    allow_execution: StrictBool = False


class AgentPlanRequest(AgentApiModel):
    instruction: str = Field(max_length=4000)
    intent: str | None = Field(default=None, max_length=100)
    preferred_agent_id: str | None = Field(default=None, max_length=100)
    include_context: StrictBool = True
    max_context_items: int = Field(default=DEFAULT_MAX_CONTEXT_ITEMS, ge=1, le=MAX_CONTEXT_ITEMS)
    max_excerpt_chars: int = Field(
        default=DEFAULT_MAX_EXCERPT_CHARS,
        ge=MIN_EXCERPT_CHARS,
        le=MAX_EXCERPT_CHARS,
    )
    allow_execution: StrictBool = False
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    calendar_reference: str | None = Field(default=None, min_length=17, max_length=89)
    default_event_duration_minutes: int | None = Field(default=None, ge=1, le=1440)


class AgentPlanReviewCreateRequest(AgentPlanRequest):
    ttl_seconds: int | None = Field(
        default=None,
        ge=MIN_PLAN_REVIEW_TTL_SECONDS,
        le=MAX_PLAN_REVIEW_TTL_SECONDS,
    )


ReviewerNote = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_REVIEWER_NOTE_CHARS),
]
ReviewReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_REVIEW_REASON_CHARS),
]


class AgentPlanReviewApproveRequest(AgentApiModel):
    reviewer_note: ReviewerNote | None = None


class AgentPlanReviewRejectRequest(AgentApiModel):
    reason: ReviewReason
    reviewer_note: ReviewerNote | None = None


class AgentPlanReviewCancelRequest(AgentApiModel):
    reason: ReviewReason | None = None
    reviewer_note: ReviewerNote | None = None


class AgentMetadataResponse(AgentApiModel):
    id: str
    name: str
    description: str
    version: str
    capabilities: list[str]
    supported_intents: list[str]
    priority: int


class AgentListResponse(AgentApiModel):
    agents: list[AgentMetadataResponse]
    count: int


class AgentRequestResponse(AgentApiModel):
    instruction: str
    intent: str | None
    context: dict[str, JsonScalar]
    preferred_agent_id: str | None
    allow_execution: bool


class SelectedAgentResponse(AgentApiModel):
    id: str
    name: str


class AgentMatchResponse(AgentApiModel):
    agent_id: str
    matched: bool
    score: int
    matched_signals: list[str]
    reasoning: list[str]
    priority: int


class AgentResultResponse(AgentApiModel):
    agent_id: str
    agent_name: str
    status: str
    summary: str
    proposed_actions: list[str]
    warnings: list[str]
    requires_confirmation: bool
    execution_performed: bool
    metadata: dict[str, JsonScalar]


class AgentRouteResponse(AgentApiModel):
    status: str
    routing_threshold: int
    request: AgentRequestResponse
    selected_agent: SelectedAgentResponse | None
    match: AgentMatchResponse | None
    matches: list[AgentMatchResponse]
    result: AgentResultResponse | None
    preferred_agent_rejected: bool


class AgentMemoryReferenceResponse(AgentApiModel):
    memory_id: str
    name: str
    kind: str
    layer: str
    title: str
    relative_path: str
    reason_selected: str
    excerpt: str
    excerpt_truncated: bool
    modified_at: str | None
    excerpt_strategy: str
    selected_headings: list[str]


class AgentContextResponse(AgentApiModel):
    agent_id: str
    instruction: str
    resolved_intent: str | None
    memory_references: list[AgentMemoryReferenceResponse]
    context_summary: str
    limitations: list[str]
    metadata: dict[str, JsonScalar]
    learning_guidance: list[dict[str, Any]]


class AgentPlanStepResponse(AgentApiModel):
    order: int
    title: str
    description: str
    source_memory_ids: list[str]
    proposed_action: str
    requires_confirmation: bool
    execution_available: bool
    warnings: list[str]
    tool_reference: AgentToolReferenceResponse
    operation_input: dict[str, Any] | None


class AgentToolReferenceResponse(AgentApiModel):
    tool_id: str
    operation_id: str
    target: str | None


class AgentPlanResponse(AgentApiModel):
    agent_id: str
    agent_name: str
    status: str
    objective: str
    context_used: bool
    steps: list[AgentPlanStepResponse]
    open_questions: list[str]
    warnings: list[str]
    requires_confirmation: bool
    execution_performed: bool
    metadata: dict[str, JsonScalar]


class AgentPlanningRoutingResponse(AgentApiModel):
    selected_agent: SelectedAgentResponse | None
    match: AgentMatchResponse | None
    matches: list[AgentMatchResponse]
    preferred_agent_rejected: bool


class AgentPlanningResponse(AgentApiModel):
    status: str
    routing: AgentPlanningRoutingResponse
    context: AgentContextResponse | None
    plan: AgentPlanResponse | None
    readiness: AgentPlanReadinessResponse | None


class PlanToolReadinessResponse(AgentApiModel):
    tool_id: str
    operation_id: str
    target: str | None
    registered: bool
    enabled: bool
    safe: bool | None
    confirmation_required: bool | None
    operation_exists: bool
    runtime_execution_allowed: bool
    adapter_available: bool
    executable_now: bool
    execution_enabled: bool
    mutation_confirmation_required: bool
    preview_required: bool
    blocking_reasons: list[str]


class AgentPlanReadinessResponse(AgentApiModel):
    ready: bool
    references: list[PlanToolReadinessResponse]
    execution_enabled: bool


class AgentReviewRoutingResponse(AgentApiModel):
    request: AgentRequestResponse
    selected_agent: SelectedAgentResponse
    match: AgentMatchResponse
    matches: list[AgentMatchResponse]
    result: AgentResultResponse
    preferred_agent_rejected: bool


class AgentPlanReviewResponse(AgentApiModel):
    review_id: str
    status: AgentPlanReviewStatus
    created_at: datetime
    expires_at: datetime
    updated_at: datetime
    instruction: str
    selected_agent_id: str
    routing: AgentReviewRoutingResponse
    context: AgentContextResponse
    plan: AgentPlanResponse
    snapshot_digest: str
    execution_authorized: bool
    execution_performed: bool
    approved_at: datetime | None
    rejected_at: datetime | None
    cancelled_at: datetime | None
    expired_at: datetime | None
    reviewer_note: str | None
    rejection_reason: str | None
    cancellation_reason: str | None
    approval_warning: str | None
    metadata: dict[str, JsonScalar]
    readiness: AgentPlanReadinessResponse


class AgentPlanReviewListResponse(AgentApiModel):
    reviews: list[AgentPlanReviewResponse]
    count: int


def agent_router(request: Request) -> AgentRouter:
    return request.app.state.agent_router


@router.post("/plan", response_model=AgentPlanningResponse)
def plan_agent(payload: AgentPlanRequest, request: Request) -> AgentPlanningResponse:
    return perform_plan(payload, request)


@router.post("/{agent_id}/plan", response_model=AgentPlanningResponse)
def plan_explicit_agent(
    agent_id: str, payload: AgentPlanRequest, request: Request
) -> AgentPlanningResponse:
    try:
        request.app.state.agent_registry.get(agent_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent '{agent_id}'.",
        ) from error
    if payload.preferred_agent_id not in (None, agent_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="preferred_agent_id must match the explicit planning agent.",
        )
    return perform_plan(payload, request, required_agent_id=agent_id)


@router.post(
    "/plan-reviews",
    response_model=AgentPlanReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_plan_review(
    payload: AgentPlanReviewCreateRequest, request: Request
) -> AgentPlanReviewResponse:
    try:
        context_request = context_request_from_payload(payload)
        record = request.app.state.agent_plan_review_service.create(
            context_request,
            ttl_seconds=payload.ttl_seconds,
        )
        return plan_review_response(
            record,
            request.app.state.tool_registry,
            request.app.state.tool_adapter_registry,
        )
    except UnknownPreferredAgentError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except PlanReviewNoMatchError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except PlanReviewCapacityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The plan review could not be created.",
        ) from error


@router.get("/plan-reviews", response_model=AgentPlanReviewListResponse)
def list_plan_reviews(
    request: Request,
    review_status: Annotated[AgentPlanReviewStatus | None, Query(alias="status")] = None,
    agent_id: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AgentPlanReviewListResponse:
    records = request.app.state.agent_plan_review_store.list(
        status=review_status,
        agent_id=agent_id,
        limit=limit,
    )
    reviews = [
        plan_review_response(
            record,
            request.app.state.tool_registry,
            request.app.state.tool_adapter_registry,
        )
        for record in records
    ]
    return AgentPlanReviewListResponse(reviews=reviews, count=len(reviews))


@router.get("/plan-reviews/{review_id}", response_model=AgentPlanReviewResponse)
def get_plan_review(review_id: str, request: Request) -> AgentPlanReviewResponse:
    try:
        return plan_review_response(
            request.app.state.agent_plan_review_store.get(review_id),
            request.app.state.tool_registry,
            request.app.state.tool_adapter_registry,
        )
    except PlanReviewNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/plan-reviews/{review_id}/approve", response_model=AgentPlanReviewResponse)
def approve_plan_review(
    review_id: str,
    payload: AgentPlanReviewApproveRequest,
    request: Request,
) -> AgentPlanReviewResponse:
    return transition_plan_review(
        lambda: request.app.state.agent_plan_review_store.approve(
            review_id, reviewer_note=payload.reviewer_note
        ),
        request.app.state.tool_registry,
        request.app.state.tool_adapter_registry,
    )


@router.post("/plan-reviews/{review_id}/reject", response_model=AgentPlanReviewResponse)
def reject_plan_review(
    review_id: str,
    payload: AgentPlanReviewRejectRequest,
    request: Request,
) -> AgentPlanReviewResponse:
    return transition_plan_review(
        lambda: request.app.state.agent_plan_review_store.reject(
            review_id,
            reason=payload.reason,
            reviewer_note=payload.reviewer_note,
        ),
        request.app.state.tool_registry,
        request.app.state.tool_adapter_registry,
    )


@router.post("/plan-reviews/{review_id}/cancel", response_model=AgentPlanReviewResponse)
def cancel_plan_review(
    review_id: str,
    payload: AgentPlanReviewCancelRequest,
    request: Request,
) -> AgentPlanReviewResponse:
    return transition_plan_review(
        lambda: request.app.state.agent_plan_review_store.cancel(
            review_id,
            reason=payload.reason,
            reviewer_note=payload.reviewer_note,
        ),
        request.app.state.tool_registry,
        request.app.state.tool_adapter_registry,
    )


@router.get("", response_model=AgentListResponse)
def list_agents(request: Request) -> AgentListResponse:
    metadata = request.app.state.agent_registry.list_metadata()
    agents = [metadata_response(item) for item in metadata]
    return AgentListResponse(agents=agents, count=len(agents))


@router.get("/{agent_id}", response_model=AgentMetadataResponse)
def get_agent(agent_id: str, request: Request) -> AgentMetadataResponse:
    try:
        agent = request.app.state.agent_registry.get(agent_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent '{agent_id}'.",
        ) from error
    return metadata_response(agent.metadata)


@router.post("/route", response_model=AgentRouteResponse)
def route_agent(payload: AgentRouteRequest, request: Request) -> AgentRouteResponse:
    try:
        agent_request = AgentRequest(
            instruction=payload.instruction,
            intent=payload.intent,
            context=payload.context,
            preferred_agent_id=payload.preferred_agent_id,
            allow_execution=payload.allow_execution,
        )
        routed = agent_router(request).route(agent_request)
        return route_response(routed, agent_router(request).threshold)
    except UnknownPreferredAgentError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TypeError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The agent registry contains an invalid routing agent.",
        ) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The agent routing request could not be completed.",
        ) from error


def metadata_response(metadata: AgentMetadata) -> AgentMetadataResponse:
    return AgentMetadataResponse(
        id=metadata.agent_id,
        name=metadata.name,
        description=metadata.description,
        version=metadata.version,
        capabilities=list(metadata.capabilities),
        supported_intents=list(metadata.supported_intents),
        priority=metadata.priority,
    )


def match_response(match: AgentMatch) -> AgentMatchResponse:
    return AgentMatchResponse(
        agent_id=match.agent_id,
        matched=match.matched,
        score=match.score,
        matched_signals=list(match.matched_signals),
        reasoning=list(match.reasoning),
        priority=match.priority,
    )


def result_response(result: AgentResult) -> AgentResultResponse:
    return AgentResultResponse(
        agent_id=result.agent_id,
        agent_name=result.agent_name,
        status=result.status,
        summary=result.summary,
        proposed_actions=list(result.proposed_actions),
        warnings=list(result.warnings),
        requires_confirmation=result.requires_confirmation,
        execution_performed=result.execution_performed,
        metadata=dict(result.metadata),
    )


def route_response(routed: AgentRouteResult, threshold: int) -> AgentRouteResponse:
    selected = None
    if routed.selected_agent_id is not None and routed.selected_agent_name is not None:
        selected = SelectedAgentResponse(
            id=routed.selected_agent_id,
            name=routed.selected_agent_name,
        )
    return AgentRouteResponse(
        status="matched" if routed.result is not None else "no_match",
        routing_threshold=threshold,
        request=AgentRequestResponse(
            instruction=routed.request.instruction,
            intent=routed.request.intent,
            context=dict(routed.request.context),
            preferred_agent_id=routed.request.preferred_agent_id,
            allow_execution=routed.request.allow_execution,
        ),
        selected_agent=selected,
        match=match_response(routed.match) if routed.match is not None else None,
        matches=[match_response(match) for match in routed.matches],
        result=result_response(routed.result) if routed.result is not None else None,
        preferred_agent_rejected=routed.preferred_agent_rejected,
    )


def perform_plan(
    payload: AgentPlanRequest,
    request: Request,
    *,
    required_agent_id: str | None = None,
) -> AgentPlanningResponse:
    preferred_agent_id = required_agent_id or payload.preferred_agent_id
    try:
        context_request = AgentContextRequest(
            instruction=payload.instruction,
            intent=payload.intent,
            preferred_agent_id=preferred_agent_id,
            include_context=payload.include_context,
            max_context_items=payload.max_context_items,
            max_excerpt_chars=payload.max_excerpt_chars,
            allow_execution=payload.allow_execution,
            timezone=payload.timezone,
            calendar_reference=payload.calendar_reference,
            default_event_duration_minutes=payload.default_event_duration_minutes,
        )
        outcome = request.app.state.agent_planning_service.plan(
            context_request,
            required_agent_id=required_agent_id,
        )
        return planning_response(
            outcome,
            request.app.state.tool_registry,
            request.app.state.tool_adapter_registry,
        )
    except UnknownPreferredAgentError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except AgentNotRelevantError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TypeError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected agent cannot construct a deterministic plan.",
        ) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The agent planning request could not be completed.",
        ) from error


def planning_response(
    outcome: AgentPlanningOutcome,
    tool_registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry,
) -> AgentPlanningResponse:
    routed = outcome.routing
    selected = None
    if routed.selected_agent_id is not None and routed.selected_agent_name is not None:
        selected = SelectedAgentResponse(
            id=routed.selected_agent_id,
            name=routed.selected_agent_name,
        )
    return AgentPlanningResponse(
        status="planned" if outcome.plan is not None else "no_match",
        routing=AgentPlanningRoutingResponse(
            selected_agent=selected,
            match=match_response(routed.match) if routed.match is not None else None,
            matches=[match_response(match) for match in routed.matches],
            preferred_agent_rejected=routed.preferred_agent_rejected,
        ),
        context=context_response(outcome.context) if outcome.context is not None else None,
        plan=plan_response(outcome.plan) if outcome.plan is not None else None,
        readiness=(
            readiness_response(outcome.plan, tool_registry, adapter_registry)
            if outcome.plan is not None
            else None
        ),
    )


def context_response(context: AgentContext) -> AgentContextResponse:
    return AgentContextResponse(
        agent_id=context.agent_id,
        instruction=context.instruction,
        resolved_intent=context.resolved_intent,
        memory_references=[
            AgentMemoryReferenceResponse(
                memory_id=reference.memory_id,
                name=reference.name,
                kind=reference.kind,
                layer=reference.layer,
                title=reference.title,
                relative_path=reference.relative_path,
                reason_selected=reference.reason_selected,
                excerpt=reference.excerpt,
                excerpt_truncated=reference.excerpt_truncated,
                modified_at=reference.modified_at,
                excerpt_strategy=reference.excerpt_strategy,
                selected_headings=list(reference.selected_headings),
            )
            for reference in context.memory_references
        ],
        context_summary=context.context_summary,
        limitations=list(context.limitations),
        metadata=dict(context.metadata),
        learning_guidance=[dict(item) for item in context.learning_guidance],
    )


def plan_step_response(step: AgentPlanStep) -> AgentPlanStepResponse:
    if step.tool_reference is None:
        raise ValueError("Agent plan step is missing its tool reference.")
    return AgentPlanStepResponse(
        order=step.order,
        title=step.title,
        description=step.description,
        source_memory_ids=list(step.source_memory_ids),
        proposed_action=step.proposed_action,
        requires_confirmation=step.requires_confirmation,
        execution_available=step.execution_available,
        warnings=list(step.warnings),
        tool_reference=tool_reference_response(step.tool_reference),
        operation_input=operation_input_response(step.operation_input),
    )


def operation_input_response(value: object | None) -> dict[str, Any] | None:
    if value is None:
        return None
    fields = getattr(value, "__dataclass_fields__", {})
    return {
        name: list(item) if isinstance(item := getattr(value, name), tuple) else item
        for name in fields
    }


def plan_response(plan: AgentPlan) -> AgentPlanResponse:
    return AgentPlanResponse(
        agent_id=plan.agent_id,
        agent_name=plan.agent_name,
        status=plan.status,
        objective=plan.objective,
        context_used=plan.context_used,
        steps=[plan_step_response(step) for step in plan.steps],
        open_questions=list(plan.open_questions),
        warnings=list(plan.warnings),
        requires_confirmation=plan.requires_confirmation,
        execution_performed=plan.execution_performed,
        metadata=dict(plan.metadata),
    )


def context_request_from_payload(payload: AgentPlanRequest) -> AgentContextRequest:
    return AgentContextRequest(
        instruction=payload.instruction,
        intent=payload.intent,
        preferred_agent_id=payload.preferred_agent_id,
        include_context=payload.include_context,
        max_context_items=payload.max_context_items,
        max_excerpt_chars=payload.max_excerpt_chars,
        allow_execution=payload.allow_execution,
        timezone=payload.timezone,
        calendar_reference=payload.calendar_reference,
        default_event_duration_minutes=payload.default_event_duration_minutes,
    )


def transition_plan_review(
    transition: Callable[[], AgentPlanReviewRecord],
    tool_registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry,
) -> AgentPlanReviewResponse:
    try:
        return plan_review_response(transition(), tool_registry, adapter_registry)
    except PlanReviewNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (PlanReviewStateConflictError, PlanReviewIntegrityError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


def plan_review_response(
    record: AgentPlanReviewRecord,
    tool_registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry,
) -> AgentPlanReviewResponse:
    routed = record.routing
    if (
        routed.selected_agent_id is None
        or routed.selected_agent_name is None
        or routed.match is None
        or routed.result is None
    ):
        raise ValueError("Stored plan review routing is incomplete.")
    return AgentPlanReviewResponse(
        review_id=record.review_id,
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at,
        updated_at=record.updated_at,
        instruction=record.instruction,
        selected_agent_id=record.selected_agent_id,
        routing=AgentReviewRoutingResponse(
            request=AgentRequestResponse(
                instruction=routed.request.instruction,
                intent=routed.request.intent,
                context=dict(routed.request.context),
                preferred_agent_id=routed.request.preferred_agent_id,
                allow_execution=routed.request.allow_execution,
            ),
            selected_agent=SelectedAgentResponse(
                id=routed.selected_agent_id,
                name=routed.selected_agent_name,
            ),
            match=match_response(routed.match),
            matches=[match_response(match) for match in routed.matches],
            result=result_response(routed.result),
            preferred_agent_rejected=routed.preferred_agent_rejected,
        ),
        context=context_response(record.context),
        plan=plan_response(record.plan),
        snapshot_digest=record.snapshot_digest,
        execution_authorized=record.execution_authorized,
        execution_performed=record.execution_performed,
        approved_at=record.approved_at,
        rejected_at=record.rejected_at,
        cancelled_at=record.cancelled_at,
        expired_at=record.expired_at,
        reviewer_note=record.reviewer_note,
        rejection_reason=record.rejection_reason,
        cancellation_reason=record.cancellation_reason,
        approval_warning=record.approval_warning,
        metadata=dict(record.metadata),
        readiness=readiness_response(record.plan, tool_registry, adapter_registry),
    )


def tool_reference_response(reference: AgentToolReference) -> AgentToolReferenceResponse:
    return AgentToolReferenceResponse(
        tool_id=reference.tool_id,
        operation_id=reference.operation_id,
        target=reference.target,
    )


def readiness_response(
    plan: AgentPlan,
    tool_registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry,
) -> AgentPlanReadinessResponse:
    readiness = evaluate_plan_readiness(plan, tool_registry, adapter_registry)
    return AgentPlanReadinessResponse(
        ready=readiness.ready,
        execution_enabled=readiness.execution_enabled,
        references=[
            PlanToolReadinessResponse(
                tool_id=item.tool_id,
                operation_id=item.operation_id,
                target=item.target,
                registered=item.registered,
                enabled=item.enabled,
                safe=item.safe,
                confirmation_required=item.confirmation_required,
                operation_exists=item.operation_exists,
                runtime_execution_allowed=item.runtime_execution_allowed,
                adapter_available=item.adapter_available,
                executable_now=item.executable_now,
                execution_enabled=item.execution_enabled,
                mutation_confirmation_required=item.mutation_confirmation_required,
                preview_required=item.preview_required,
                blocking_reasons=list(item.blocking_reasons),
            )
            for item in readiness.references
        ],
    )
