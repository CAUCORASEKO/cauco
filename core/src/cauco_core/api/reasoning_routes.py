from cauco_agents import (
    DEFAULT_MAX_CONTEXT_ITEMS,
    DEFAULT_MAX_EXCERPT_CHARS,
    MAX_CONTEXT_ITEMS,
    MAX_EXCERPT_CHARS,
    MIN_EXCERPT_CHARS,
    AgentContextRequest,
    UnknownPreferredAgentError,
)
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from cauco_core.api.agent_routes import (
    AgentContextResponse,
    AgentMatchResponse,
    AgentPlanResponse,
    SelectedAgentResponse,
    context_response,
    match_response,
    plan_response,
)
from cauco_core.reasoning import ReasoningAwarePlanningOutcome

router = APIRouter(prefix="/api/reasoning", tags=["reasoning"])


class ReasoningPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    calendar_reference: str | None = Field(default=None, min_length=17, max_length=89)
    default_event_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    mail_account_reference: str | None = Field(
        default=None,
        min_length=17,
        max_length=89,
        pattern=r"^mailacct_[A-Za-z0-9_-]{8,80}$",
    )
    mailbox_reference: str | None = Field(
        default=None,
        min_length=16,
        max_length=88,
        pattern=r"^mailbox_[A-Za-z0-9_-]{8,80}$",
    )
    use_reasoning: StrictBool = False


class ReasoningPlanningRoutingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_agent: SelectedAgentResponse | None
    match: AgentMatchResponse | None
    matches: list[AgentMatchResponse]
    preferred_agent_rejected: bool


class ReasoningPlanningDataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    routing: ReasoningPlanningRoutingResponse
    context: AgentContextResponse | None
    plan: AgentPlanResponse | None
    proposal_only: bool = True
    execution_performed: bool = False
    review_approved: bool = False
    runtime_started: bool = False


class ReasoningAwarePlanningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning_requested: bool
    reasoning_invoked: bool
    proposal_produced: bool
    proposal_validated: bool
    planning_context_enriched: bool
    provider: str | None
    model: str | None
    explanation: str
    planning: ReasoningPlanningDataResponse


@router.post("/plan", response_model=ReasoningAwarePlanningResponse)
def plan_with_reasoning(
    payload: ReasoningPlanRequest,
    request: Request,
) -> ReasoningAwarePlanningResponse:
    try:
        context_request = AgentContextRequest(
            instruction=payload.instruction,
            intent=payload.intent,
            preferred_agent_id=payload.preferred_agent_id,
            include_context=payload.include_context,
            max_context_items=payload.max_context_items,
            max_excerpt_chars=payload.max_excerpt_chars,
            allow_execution=False,
            timezone=payload.timezone,
            calendar_reference=payload.calendar_reference,
            default_event_duration_minutes=payload.default_event_duration_minutes,
            mail_account_reference=payload.mail_account_reference,
            mailbox_reference=payload.mailbox_reference,
        )
        outcome = request.app.state.reasoning_aware_planning_service.plan(
            context_request,
            use_reasoning=payload.use_reasoning,
        )
        return reasoning_planning_response(outcome)
    except UnknownPreferredAgentError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
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
            detail="The advisory planning request could not be completed.",
        ) from error


def reasoning_planning_response(
    outcome: ReasoningAwarePlanningOutcome,
) -> ReasoningAwarePlanningResponse:
    planning = outcome.planning
    routed = planning.routing
    selected = None
    if routed.selected_agent_id is not None and routed.selected_agent_name is not None:
        selected = SelectedAgentResponse(
            id=routed.selected_agent_id,
            name=routed.selected_agent_name,
        )
    return ReasoningAwarePlanningResponse(
        reasoning_requested=outcome.reasoning_requested,
        reasoning_invoked=outcome.reasoning_invoked,
        proposal_produced=outcome.proposal_produced,
        proposal_validated=outcome.proposal_validated,
        planning_context_enriched=outcome.planning_context_enriched,
        provider=outcome.provider,
        model=outcome.model,
        explanation=outcome.explanation,
        planning=ReasoningPlanningDataResponse(
            status="planned" if planning.plan is not None else "no_match",
            routing=ReasoningPlanningRoutingResponse(
                selected_agent=selected,
                match=match_response(routed.match) if routed.match is not None else None,
                matches=[match_response(match) for match in routed.matches],
                preferred_agent_rejected=routed.preferred_agent_rejected,
            ),
            context=context_response(planning.context) if planning.context is not None else None,
            plan=plan_response(planning.plan) if planning.plan is not None else None,
        ),
    )
