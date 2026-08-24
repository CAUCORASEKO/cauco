from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from cauco_reasoning.proposals import ReasoningProposal

ReasoningValue = str | int | float | bool | None


def _freeze_mapping(
    value: Mapping[str, ReasoningValue],
) -> Mapping[str, ReasoningValue]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class ReasoningRequest:
    """Bounded input supplied to a reasoning engine."""

    instruction: str
    agent_id: str | None = None
    context: Mapping[str, ReasoningValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        instruction = " ".join(self.instruction.split())
        if not instruction:
            raise ValueError("Reasoning instruction cannot be empty.")
        if len(instruction) > 8_000:
            raise ValueError("Reasoning instruction cannot exceed 8000 characters.")

        agent_id = self.agent_id.strip() if self.agent_id is not None else None
        if agent_id == "":
            agent_id = None

        if len(self.context) > 50:
            raise ValueError("Reasoning context cannot contain more than 50 entries.")

        copied: dict[str, ReasoningValue] = {}
        for key, value in self.context.items():
            normalized_key = key.strip()

            if not normalized_key or len(normalized_key) > 150:
                raise ValueError(
                    "Reasoning context keys must contain between 1 and 150 characters."
                )

            if not isinstance(value, (str, int, float, bool, type(None))):
                raise ValueError("Reasoning context values must be JSON scalar values.")

            if isinstance(value, str) and len(value) > 4_000:
                raise ValueError("Reasoning context text values cannot exceed 4000 characters.")

            copied[normalized_key] = value

        object.__setattr__(self, "instruction", instruction)
        object.__setattr__(self, "agent_id", agent_id)
        object.__setattr__(self, "context", _freeze_mapping(copied))


@dataclass(frozen=True, slots=True)
class ReasoningResult:
    """Provider-neutral result returned by a reasoning engine."""

    provider: str
    model: str | None
    text: str
    structured_data: Mapping[str, Any] = field(default_factory=dict)
    reasoning_performed: bool = False
    proposal: ReasoningProposal | None = None

    def __post_init__(self) -> None:
        provider = self.provider.strip()
        if not provider:
            raise ValueError("Reasoning provider cannot be empty.")

        model = self.model.strip() if self.model is not None else None
        if model == "":
            model = None

        if len(self.text) > 100_000:
            raise ValueError("Reasoning result text cannot exceed 100000 characters.")

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(
            self,
            "structured_data",
            MappingProxyType(dict(self.structured_data)),
        )
