from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    tool_id: str
    name: str
    description: str
    read_only: bool
    risk: RiskLevel

    def __post_init__(self) -> None:
        if not self.tool_id.strip():
            raise ValueError("Tool ID cannot be empty.")


class BaseTool(ABC, Generic[InputT, OutputT]):
    metadata: ToolMetadata

    @abstractmethod
    def execute(self, input_data: InputT) -> OutputT:
        """Execute a bounded operation described by the tool contract."""
