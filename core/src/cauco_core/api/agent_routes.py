from typing import TypeAlias

from cauco_agents import (
    AgentMatch,
    AgentMetadata,
    AgentRequest,
    AgentResult,
    AgentRouter,
    AgentRouteResult,
    UnknownPreferredAgentError,
)
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

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


def agent_router(request: Request) -> AgentRouter:
    return request.app.state.agent_router


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
