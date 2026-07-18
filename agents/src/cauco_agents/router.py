from dataclasses import replace

from cauco_agents.base import BaseAgent
from cauco_agents.models import AgentMatch, AgentRequest, AgentRouteResult
from cauco_agents.registry import AgentRegistry

DEFAULT_ROUTING_THRESHOLD = 40


class UnknownPreferredAgentError(LookupError):
    pass


class AgentRouter:
    def __init__(
        self,
        registry: AgentRegistry,
        *,
        threshold: int = DEFAULT_ROUTING_THRESHOLD,
    ) -> None:
        if not 1 <= threshold <= 100:
            raise ValueError("Agent routing threshold must be between 1 and 100.")
        self.registry = registry
        self.threshold = threshold

    def route(self, request: AgentRequest) -> AgentRouteResult:
        agents = self._routing_agents()
        matches = tuple(agent.can_handle(request) for agent in agents)
        matches_by_id = {match.agent_id: match for match in matches}
        agents_by_id = {agent.id: agent for agent in agents}

        preferred_rejected = False
        selected: BaseAgent | None = None
        selected_match: AgentMatch | None = None
        if request.preferred_agent_id is not None:
            if request.preferred_agent_id not in agents_by_id:
                raise UnknownPreferredAgentError(
                    f"Unknown preferred agent '{request.preferred_agent_id}'."
                )
            preferred_match = matches_by_id[request.preferred_agent_id]
            if preferred_match.score >= self.threshold:
                selected = agents_by_id[request.preferred_agent_id]
                selected_match = preferred_match
            else:
                preferred_rejected = True

        if selected is None:
            ranked = sorted(
                matches,
                key=lambda match: (-match.score, -match.priority, match.agent_id),
            )
            if ranked and ranked[0].score >= self.threshold:
                selected_match = ranked[0]
                selected = agents_by_id[selected_match.agent_id]

        if selected is None or selected_match is None:
            return AgentRouteResult(
                request=request,
                selected_agent_id=None,
                selected_agent_name=None,
                match=None,
                matches=matches,
                result=None,
                preferred_agent_rejected=preferred_rejected,
            )

        result = selected.execute(request)
        if preferred_rejected:
            result = replace(
                result,
                warnings=(
                    *result.warnings,
                    "The preferred agent was not selected because it did not meet the routing threshold.",
                ),
            )
        return AgentRouteResult(
            request=request,
            selected_agent_id=selected.id,
            selected_agent_name=selected.metadata.name,
            match=selected_match,
            matches=matches,
            result=result,
            preferred_agent_rejected=preferred_rejected,
        )

    def _routing_agents(self) -> tuple[BaseAgent, ...]:
        agents = self.registry.list_agents()
        if not all(isinstance(agent, BaseAgent) for agent in agents):
            raise TypeError("AgentRouter registry contains an incompatible agent contract.")
        return tuple(agent for agent in agents if isinstance(agent, BaseAgent))
