from cauco_agents.base import Agent


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

    def list_metadata(self) -> tuple:
        return tuple(agent.metadata for agent in self._agents.values())

    def __len__(self) -> int:
        return len(self._agents)
