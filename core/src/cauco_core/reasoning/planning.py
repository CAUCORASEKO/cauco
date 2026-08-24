from dataclasses import dataclass

from cauco_agents import AgentContextRequest

from cauco_core.agents.planning import AgentPlanningOutcome, AgentPlanningService
from cauco_core.reasoning.proposals import ReasoningPlanningBridge
from cauco_core.reasoning.service import ReasoningOrchestrationService


@dataclass(frozen=True, slots=True)
class ReasoningAwarePlanningOutcome:
    planning: AgentPlanningOutcome
    reasoning_requested: bool
    reasoning_invoked: bool
    proposal_produced: bool
    proposal_validated: bool
    planning_context_enriched: bool
    provider: str | None = None
    model: str | None = None
    explanation: str = ""


class ReasoningAwarePlanningService:
    """Explicit opt-in advisory enrichment around the existing planner."""

    def __init__(
        self,
        reasoning: ReasoningOrchestrationService,
        bridge: ReasoningPlanningBridge,
        planner: AgentPlanningService,
    ) -> None:
        self.reasoning = reasoning
        self.bridge = bridge
        self.planner = planner

    def plan(
        self,
        request: AgentContextRequest,
        *,
        use_reasoning: bool = False,
        required_agent_id: str | None = None,
    ) -> ReasoningAwarePlanningOutcome:
        if not use_reasoning:
            planning = self.planner.plan(request, required_agent_id=required_agent_id)
            return self._outcome(
                planning,
                False,
                None,
                False,
                False,
                None,
                None,
                "Reasoning was not requested.",
            )

        reasoning_outcome = self.reasoning.assess(self._reasoning_request(request))
        enriched = self._non_executing_request(request)
        enriched_context = False
        if reasoning_outcome.validated_proposal is not None:
            enriched = self.bridge.to_context_request(
                enriched, reasoning_outcome.validated_proposal
            )
            enriched_context = True
        planning = self.planner.plan(enriched, required_agent_id=required_agent_id)
        result = reasoning_outcome.result
        return self._outcome(
            planning,
            True,
            reasoning_outcome,
            enriched_context,
            reasoning_outcome.validated_proposal is not None,
            result.provider if result else None,
            result.model if result else None,
        )

    @staticmethod
    def _reasoning_request(request: AgentContextRequest):
        from cauco_reasoning import ReasoningRequest

        return ReasoningRequest(
            instruction=request.instruction,
            agent_id=request.preferred_agent_id,
            context={"intent": request.intent},
        )

    @staticmethod
    def _non_executing_request(request: AgentContextRequest) -> AgentContextRequest:
        return AgentContextRequest(
            instruction=request.instruction,
            intent=request.intent,
            preferred_agent_id=request.preferred_agent_id,
            include_context=request.include_context,
            max_context_items=request.max_context_items,
            max_excerpt_chars=request.max_excerpt_chars,
            allow_execution=False,
            timezone=request.timezone,
            calendar_reference=request.calendar_reference,
            default_event_duration_minutes=request.default_event_duration_minutes,
            mail_account_reference=request.mail_account_reference,
            mailbox_reference=request.mailbox_reference,
        )

    @staticmethod
    def _outcome(
        planning,
        requested,
        reasoning_outcome,
        enriched,
        validated,
        provider,
        model,
        explanation=None,
    ):
        return ReasoningAwarePlanningOutcome(
            planning=planning,
            reasoning_requested=requested,
            reasoning_invoked=reasoning_outcome.reasoning_invoked if reasoning_outcome else False,
            proposal_produced=bool(reasoning_outcome and reasoning_outcome.proposal),
            proposal_validated=validated,
            planning_context_enriched=enriched,
            provider=provider,
            model=model,
            explanation=explanation or (reasoning_outcome.explanation if reasoning_outcome else ""),
        )
