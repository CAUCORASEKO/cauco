from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, TypeAlias

AgentContextValue: TypeAlias = str | int | float | bool | None
DEFAULT_MAX_CONTEXT_ITEMS = 4
DEFAULT_MAX_EXCERPT_CHARS = 2000
MAX_CONTEXT_ITEMS = 8
MIN_EXCERPT_CHARS = 100
MAX_EXCERPT_CHARS = 4000
MAX_TOTAL_CONTEXT_CHARS = 7000


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


@dataclass(frozen=True, slots=True)
class AgentContextRequest:
    instruction: str
    intent: str | None = None
    preferred_agent_id: str | None = None
    include_context: bool = True
    max_context_items: int = DEFAULT_MAX_CONTEXT_ITEMS
    max_excerpt_chars: int = DEFAULT_MAX_EXCERPT_CHARS
    allow_execution: bool = False

    def __post_init__(self) -> None:
        normalized = AgentRequest(
            instruction=self.instruction,
            intent=self.intent,
            preferred_agent_id=self.preferred_agent_id,
            allow_execution=self.allow_execution,
        )
        object.__setattr__(self, "instruction", normalized.instruction)
        object.__setattr__(self, "intent", normalized.intent)
        object.__setattr__(self, "preferred_agent_id", normalized.preferred_agent_id)
        if not 1 <= self.max_context_items <= MAX_CONTEXT_ITEMS:
            raise ValueError(
                f"max_context_items must be between 1 and {MAX_CONTEXT_ITEMS}."
            )
        if not MIN_EXCERPT_CHARS <= self.max_excerpt_chars <= MAX_EXCERPT_CHARS:
            raise ValueError(
                "max_excerpt_chars must be between "
                f"{MIN_EXCERPT_CHARS} and {MAX_EXCERPT_CHARS}."
            )

    def routing_request(self) -> AgentRequest:
        return AgentRequest(
            instruction=self.instruction,
            intent=self.intent,
            preferred_agent_id=self.preferred_agent_id,
            allow_execution=self.allow_execution,
        )


@dataclass(frozen=True, slots=True)
class AgentMemoryReference:
    memory_id: str
    name: str
    kind: str
    layer: str
    title: str
    relative_path: str
    reason_selected: str
    excerpt: str
    excerpt_truncated: bool
    modified_at: str | None = None
    excerpt_strategy: str = "document_start"
    selected_headings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentContext:
    agent_id: str
    instruction: str
    resolved_intent: str | None
    memory_references: tuple[AgentMemoryReference, ...]
    context_summary: str
    limitations: tuple[str, ...]
    metadata: Mapping[str, AgentContextValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class AgentPlanStep:
    order: int
    title: str
    description: str
    source_memory_ids: tuple[str, ...]
    proposed_action: str
    requires_confirmation: bool
    execution_available: bool
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.order < 1:
            raise ValueError("Agent plan step order must be positive.")
        if self.execution_available:
            raise ValueError("Phase 5B plan execution cannot be available.")


@dataclass(frozen=True, slots=True)
class AgentPlan:
    agent_id: str
    agent_name: str
    status: str
    objective: str
    context_used: bool
    steps: tuple[AgentPlanStep, ...]
    open_questions: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_confirmation: bool
    execution_performed: bool = False
    metadata: Mapping[str, AgentContextValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.execution_performed:
            raise ValueError("Phase 5B agents cannot report performed execution.")
        expected_orders = tuple(range(1, len(self.steps) + 1))
        if tuple(step.order for step in self.steps) != expected_orders:
            raise ValueError("Agent plan steps must use contiguous one-based ordering.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
