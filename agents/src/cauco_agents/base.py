from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True, slots=True)
class AgentMetadata:
    agent_id: str
    name: str
    description: str
    uses_model: bool = False

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("Agent ID cannot be empty.")


class Agent(ABC, Generic[InputT, OutputT]):
    metadata: AgentMetadata

    @abstractmethod
    def run(self, input_data: InputT) -> OutputT:
        """Process structured input without an autonomous loop."""
