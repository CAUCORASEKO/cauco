from cauco_agents.base import Agent, AgentMetadata
from cauco_agents.builtin import (
    CalendarAgent,
    EmailAgent,
    GitAgent,
    ProjectAgent,
    ResearchAgent,
)


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent[object, object]] = {}

    def register(self, agent: Agent[object, object]) -> None:
        agent_id = agent.metadata.agent_id
        if agent_id in self._agents:
            raise ValueError(f"Agent '{agent_id}' is already registered.")
        self._agents[agent_id] = agent

    def get(self, agent_id: str) -> Agent[object, object]:
        try:
            return self._agents[agent_id]
        except KeyError as error:
            raise KeyError(f"Unknown agent '{agent_id}'.") from error

    def list_agents(self) -> tuple[Agent[object, object], ...]:
        return tuple(self._agents[agent_id] for agent_id in sorted(self._agents))

    def list_metadata(self) -> tuple[AgentMetadata, ...]:
        return tuple(agent.metadata for agent in self.list_agents())

    def __len__(self) -> int:
        return len(self._agents)


def create_default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(CalendarAgent())
    registry.register(EmailAgent())
    registry.register(ProjectAgent())
    registry.register(GitAgent())
    registry.register(ResearchAgent())
    return registry
