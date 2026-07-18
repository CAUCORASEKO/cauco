from dataclasses import dataclass

from cauco_agents import (
    AgentContext,
    AgentContextRequest,
    AgentPlan,
    AgentRouter,
    AgentRouteResult,
    PlanningAgent,
)
from cauco_agents.registry import AgentRegistry

from cauco_core.agents.context import AgentContextResolver


class AgentNotRelevantError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AgentPlanningOutcome:
    routing: AgentRouteResult
    context: AgentContext | None
    plan: AgentPlan | None


class AgentPlanningService:
    def __init__(
        self,
        router: AgentRouter,
        registry: AgentRegistry,
        context_resolver: AgentContextResolver,
    ) -> None:
        self.router = router
        self.registry = registry
        self.context_resolver = context_resolver

    def plan(
        self,
        request: AgentContextRequest,
        *,
        required_agent_id: str | None = None,
    ) -> AgentPlanningOutcome:
        routed = self.router.route(request.routing_request())
        if required_agent_id is not None and routed.selected_agent_id != required_agent_id:
            raise AgentNotRelevantError(
                f"Agent '{required_agent_id}' does not meet the routing threshold "
                "for this instruction."
            )
        if routed.selected_agent_id is None:
            return AgentPlanningOutcome(routing=routed, context=None, plan=None)
        agent = self.registry.get(routed.selected_agent_id)
        if not isinstance(agent, PlanningAgent):
            raise TypeError("The selected agent does not support deterministic planning.")
        context = self.context_resolver.resolve(routed.selected_agent_id, request)
        plan = agent.plan(context, allow_execution=request.allow_execution)
        return AgentPlanningOutcome(routing=routed, context=context, plan=plan)
