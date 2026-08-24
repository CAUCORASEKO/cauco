from cauco_agents import AgentContextRequest, create_default_registry
from cauco_reasoning import (
    ReasoningProposal,
    ReasoningProposalStep,
    ReasoningRequest,
    ReasoningRequirementResolver,
    ReasoningResult,
    ReasoningService,
)

from cauco_core.agents.planning import AgentPlanningOutcome
from cauco_core.reasoning import (
    ReasoningAwarePlanningService,
    ReasoningOrchestrationService,
    ReasoningPlanningBridge,
    ReasoningProposalValidator,
)


class Engine:
    def __init__(self, result: ReasoningResult) -> None:
        self.result = result
        self.calls = 0

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.calls += 1
        return self.result


class Planner:
    def __init__(self) -> None:
        self.requests = []

    def plan(self, request, *, required_agent_id=None):
        self.requests.append((request, required_agent_id))
        return AgentPlanningOutcome(routing=None, context=None, plan=None)


def make_planner(result: ReasoningResult):
    engine = Engine(result)
    reasoning = ReasoningOrchestrationService(
        ReasoningRequirementResolver(),
        ReasoningService(engine),
        ReasoningProposalValidator(create_default_registry()),
    )
    planner = Planner()
    service = ReasoningAwarePlanningService(
        reasoning,
        ReasoningPlanningBridge(),
        planner,
    )
    return service, engine, planner


def test_reasoning_is_explicit_opt_in_and_preserves_deterministic_planning() -> None:
    service, engine, planner = make_planner(
        ReasoningResult(provider="test", model="m", text="advice", reasoning_performed=True)
    )
    request = AgentContextRequest("list notes", allow_execution=True)

    outcome = service.plan(request)

    assert engine.calls == 0
    assert outcome.reasoning_requested is False
    assert planner.requests[0][0] is request


def test_valid_advice_enriches_planning_without_escalating_or_forcing_routing() -> None:
    proposal = ReasoningProposal(
        summary="Compare options",
        suggested_steps=(
            ReasoningProposalStep(
                "Compare",
                suggested_agent_id="research",
                suggested_intent="research-comparison",
            ),
        ),
    )
    service, engine, planner = make_planner(
        ReasoningResult(
            provider="test", model="m", text="advice", proposal=proposal, reasoning_performed=True
        )
    )
    request = AgentContextRequest(
        "analyze options",
        intent="caller-intent",
        preferred_agent_id="git",
        allow_execution=True,
    )

    outcome = service.plan(request, use_reasoning=True)
    enriched, required_agent = planner.requests[0]

    assert engine.calls == 1
    assert outcome.planning_context_enriched is True
    assert outcome.proposal_validated is True
    assert enriched.allow_execution is False
    assert enriched.preferred_agent_id == "git"
    assert enriched.intent == "caller-intent"
    assert required_agent is None
    assert request.allow_execution is True


def test_invalid_or_missing_advice_does_not_block_planning() -> None:
    service, engine, planner = make_planner(
        ReasoningResult(provider="test", model="m", text="advice", reasoning_performed=True)
    )

    request = AgentContextRequest("analyze options", allow_execution=True)
    outcome = service.plan(request, use_reasoning=True)

    assert engine.calls == 1
    assert outcome.planning_context_enriched is False
    assert planner.requests[0][0].allow_execution is False
    assert request.allow_execution is True


def test_provider_failure_continues_with_non_executing_planning() -> None:
    class FailingEngine:
        calls = 0

        def reason(self, request: ReasoningRequest) -> ReasoningResult:
            self.calls += 1
            raise RuntimeError("secret provider credential")

    engine = FailingEngine()
    reasoning = ReasoningOrchestrationService(
        ReasoningRequirementResolver(),
        ReasoningService(engine),
        ReasoningProposalValidator(create_default_registry()),
    )
    planner = Planner()
    service = ReasoningAwarePlanningService(
        reasoning,
        ReasoningPlanningBridge(),
        planner,
    )
    request = AgentContextRequest("analyze options", allow_execution=True)

    outcome = service.plan(request, use_reasoning=True)

    assert engine.calls == 1
    assert planner.requests[0][0].allow_execution is False
    assert request.allow_execution is True
    assert "secret" not in outcome.explanation
