from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Any

MAX_PROPOSAL_STEPS = 12
MAX_PROPOSAL_ITEMS = 20
MAX_PROPOSAL_TEXT = 4000
MAX_METADATA_DEPTH = 5
MAX_METADATA_KEY = 150


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text.")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > MAX_PROPOSAL_TEXT:
        raise ValueError(f"{field_name} must contain 1 to {MAX_PROPOSAL_TEXT} characters.")
    return normalized


def _items(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if len(values) > MAX_PROPOSAL_ITEMS:
        raise ValueError(f"{field_name} contains too many items.")
    return tuple(_text(value, field_name) for value in values)


def _metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_METADATA_DEPTH:
        raise ValueError("Proposal metadata nesting is too deep.")
    if isinstance(value, Mapping):
        if len(value) > MAX_PROPOSAL_ITEMS:
            raise ValueError("Proposal metadata contains too many entries.")
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Proposal metadata keys must be text.")
            normalized_key = " ".join(key.split())
            if not normalized_key or len(normalized_key) > MAX_METADATA_KEY:
                raise ValueError("Proposal metadata keys are invalid.")
            copied[normalized_key] = _metadata(item, depth=depth + 1)
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_PROPOSAL_ITEMS:
            raise ValueError("Proposal metadata contains too many items.")
        return tuple(_metadata(item, depth=depth + 1) for item in value)
    if isinstance(value, str):
        if len(value) > MAX_PROPOSAL_TEXT:
            raise ValueError("Proposal metadata text is too long.")
        return value
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Proposal metadata numbers must be finite.")
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise ValueError("Proposal metadata must contain JSON-compatible values.")


@dataclass(frozen=True, slots=True)
class ReasoningProposalStep:
    description: str
    suggested_agent_id: str | None = None
    suggested_intent: str | None = None
    requires_user_confirmation: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "description", _text(self.description, "Step description"))
        if self.suggested_agent_id is not None:
            object.__setattr__(
                self,
                "suggested_agent_id",
                _text(self.suggested_agent_id, "Agent ID"),
            )
        if self.suggested_intent is not None:
            object.__setattr__(self, "suggested_intent", _text(self.suggested_intent, "Intent"))
        if not isinstance(self.requires_user_confirmation, bool):
            raise ValueError("Step confirmation requirement must be boolean.")


@dataclass(frozen=True, slots=True)
class ReasoningProposal:
    summary: str
    rationale: tuple[str, ...] = ()
    suggested_steps: tuple[ReasoningProposalStep, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _text(self.summary, "Proposal summary"))
        object.__setattr__(self, "rationale", _items(tuple(self.rationale), "Rationale"))
        object.__setattr__(
            self, "assumptions", _items(tuple(self.assumptions), "Assumptions")
        )
        object.__setattr__(
            self, "limitations", _items(tuple(self.limitations), "Limitations")
        )
        steps = tuple(self.suggested_steps)
        if len(steps) > MAX_PROPOSAL_STEPS:
            raise ValueError("Proposal contains too many steps.")
        if any(not isinstance(step, ReasoningProposalStep) for step in steps):
            raise ValueError("Proposal steps must be advisory reasoning steps.")
        object.__setattr__(self, "suggested_steps", steps)
        if self.confidence is not None and (
                isinstance(self.confidence, bool)
                or not isinstance(self.confidence, (int, float))
                or not isfinite(self.confidence)
                or not 0 <= self.confidence <= 1
        ):
            raise ValueError("Proposal confidence must be between 0 and 1.")
        object.__setattr__(self, "metadata", _metadata(self.metadata))
