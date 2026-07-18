import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from cauco_agents.models import (
    AgentContext,
    AgentMatch,
    AgentPlan,
    AgentRequest,
    AgentResult,
)

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True, slots=True)
class AgentMetadata:
    agent_id: str
    name: str
    description: str
    uses_model: bool = False
    version: str = "1.0.0"
    capabilities: tuple[str, ...] = ()
    supported_intents: tuple[str, ...] = ()
    priority: int = 0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", self.agent_id):
            raise ValueError("Agent ID must use lowercase letters, numbers, hyphens, or underscores.")
        if not self.name.strip() or not self.description.strip() or not self.version.strip():
            raise ValueError("Agent name, description, and version cannot be empty.")
        if not 0 <= self.priority <= 100:
            raise ValueError("Agent priority must be between 0 and 100.")
        if any(not value.strip() for value in (*self.capabilities, *self.supported_intents)):
            raise ValueError("Agent capabilities and supported intents cannot be empty.")


class Agent(ABC, Generic[InputT, OutputT]):
    metadata: AgentMetadata

    @abstractmethod
    def run(self, input_data: InputT) -> OutputT:
        """Process structured input without an autonomous loop."""


class BaseAgent(Agent[AgentRequest, AgentResult], ABC):
    """Common contract for deterministic, proposal-only routing agents."""

    @property
    def id(self) -> str:
        return self.metadata.agent_id

    @abstractmethod
    def can_handle(self, request: AgentRequest) -> AgentMatch:
        """Return deterministic match evidence without executing an action."""

    @abstractmethod
    def execute(self, request: AgentRequest) -> AgentResult:
        """Return a structured proposal only; Phase 5A performs no execution."""

    def run(self, input_data: AgentRequest) -> AgentResult:
        return self.execute(input_data)


class PlanningAgent(BaseAgent, ABC):
    """Routing agent that can construct a deterministic plan from resolved context."""

    @abstractmethod
    def plan(self, context: AgentContext, *, allow_execution: bool = False) -> AgentPlan:
        """Build a proposal-only plan from bounded, untrusted memory context."""
