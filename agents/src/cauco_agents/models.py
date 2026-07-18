from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, TypeAlias

AgentContextValue: TypeAlias = str | int | float | bool | None


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True, slots=True)
class AgentRequest:
    instruction: str
    intent: str | None = None
    context: Mapping[str, AgentContextValue] = field(default_factory=dict)
    preferred_agent_id: str | None = None
    allow_execution: bool = False

    def __post_init__(self) -> None:
        instruction = normalize_whitespace(self.instruction)
        if not instruction:
            raise ValueError("Agent instruction cannot be empty.")
        if len(instruction) > 4000:
            raise ValueError("Agent instruction cannot exceed 4000 characters.")
        object.__setattr__(self, "instruction", instruction)

        intent = normalize_whitespace(self.intent) if self.intent is not None else None
        preferred = (
            normalize_whitespace(self.preferred_agent_id)
            if self.preferred_agent_id is not None
            else None
        )
        object.__setattr__(self, "intent", intent or None)
        object.__setattr__(self, "preferred_agent_id", preferred or None)

        if len(self.context) > 20:
            raise ValueError("Agent context cannot contain more than 20 entries.")
        copied_context: dict[str, AgentContextValue] = {}
        for key, value in self.context.items():
            normalized_key = normalize_whitespace(key)
            if not normalized_key or len(normalized_key) > 100:
                raise ValueError("Agent context keys must contain 1 to 100 characters.")
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise ValueError("Agent context values must be JSON scalar values.")
            if isinstance(value, str) and len(value) > 1000:
                raise ValueError("Agent context text values cannot exceed 1000 characters.")
            copied_context[normalized_key] = value
        object.__setattr__(self, "context", MappingProxyType(copied_context))


@dataclass(frozen=True, slots=True)
class AgentMatch:
    agent_id: str
    matched: bool
    score: int
    matched_signals: tuple[str, ...]
    reasoning: tuple[str, ...]
    priority: int

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("Agent match score must be between 0 and 100.")
        if self.matched != (self.score > 0):
            raise ValueError("Agent match state must agree with its score.")


@dataclass(frozen=True, slots=True)
class AgentResult:
    agent_id: str
    agent_name: str
    status: str
    summary: str
    proposed_actions: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_confirmation: bool
    execution_performed: bool = False
    metadata: Mapping[str, AgentContextValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.execution_performed:
            raise ValueError("Phase 5A agents cannot report performed execution.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class AgentRouteResult:
    request: AgentRequest
    selected_agent_id: str | None
    selected_agent_name: str | None
    match: AgentMatch | None
    matches: tuple[AgentMatch, ...]
    result: AgentResult | None
    preferred_agent_rejected: bool = False
