from typing import TypeAlias

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
    AgentPlanStep,
    AgentRequest,
    AgentResult,
    AgentRouter,
    AgentRouteResult,
    UnknownPreferredAgentError,
)
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from cauco_core.agents.planning import AgentNotRelevantError, AgentPlanningOutcome

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
    max_context_items: int = Field(
        default=DEFAULT_MAX_CONTEXT_ITEMS, ge=1, le=MAX_CONTEXT_ITEMS
    )
    max_excerpt_chars: int = Field(
        default=DEFAULT_MAX_EXCERPT_CHARS,
        ge=MIN_EXCERPT_CHARS,
        le=MAX_EXCERPT_CHARS,
    )
    allow_execution: StrictBool = False


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


class AgentPlanStepResponse(AgentApiModel):
    order: int
    title: str
    description: str
    source_memory_ids: list[str]
    proposed_action: str
    requires_confirmation: bool
    execution_available: bool
    warnings: list[str]


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
        )
        outcome = request.app.state.agent_planning_service.plan(
            context_request,
            required_agent_id=required_agent_id,
        )
        return planning_response(outcome)
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


def planning_response(outcome: AgentPlanningOutcome) -> AgentPlanningResponse:
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
    )


def plan_step_response(step: AgentPlanStep) -> AgentPlanStepResponse:
    return AgentPlanStepResponse(
        order=step.order,
        title=step.title,
        description=step.description,
        source_memory_ids=list(step.source_memory_ids),
        proposed_action=step.proposed_action,
        requires_confirmation=step.requires_confirmation,
        execution_available=step.execution_available,
        warnings=list(step.warnings),
    )


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
