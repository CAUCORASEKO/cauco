from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from cauco_agents import AgentContextRequest, AgentRegistry
from cauco_reasoning import ReasoningProposal


@dataclass(frozen=True, slots=True)
class ValidatedReasoningProposalStep:
    description: str
    suggested_agent_id: str | None
    suggested_intent: str | None
    requires_user_confirmation: bool


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ValidatedReasoningProposal:
    summary: str
    rationale: tuple[str, ...]
    suggested_steps: tuple[ValidatedReasoningProposalStep, ...]
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    confidence: float | None
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rationale", tuple(self.rationale))
        object.__setattr__(self, "suggested_steps", tuple(self.suggested_steps))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "limitations", tuple(self.limitations))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


class ReasoningProposalValidator:
    """Validates advisory proposals without creating executable references."""

    def __init__(self, agent_registry: AgentRegistry | None = None) -> None:
        self.agent_registry = agent_registry

    def validate(self, proposal: ReasoningProposal) -> ValidatedReasoningProposal:
        steps: list[ValidatedReasoningProposalStep] = []
        for step in proposal.suggested_steps:
            if step.suggested_agent_id and self.agent_registry is not None:
                try:
                    self.agent_registry.get(step.suggested_agent_id)
                except KeyError as error:
                    raise ValueError("Proposal contains an unknown agent.") from error
            steps.append(
                ValidatedReasoningProposalStep(
                    description=step.description,
                    suggested_agent_id=step.suggested_agent_id,
                    suggested_intent=step.suggested_intent.casefold()
                    if step.suggested_intent
                    else None,
                    requires_user_confirmation=step.requires_user_confirmation,
                )
            )
        return ValidatedReasoningProposal(
            summary=proposal.summary,
            rationale=proposal.rationale,
            suggested_steps=tuple(steps),
            assumptions=proposal.assumptions,
            limitations=proposal.limitations,
            confidence=proposal.confidence,
            metadata=_freeze(proposal.metadata),
        )


class ReasoningPlanningBridge:
    """Converts validated advice into bounded, non-executing planning input."""

    def to_context_request(
        self,
        request: AgentContextRequest,
        proposal: ValidatedReasoningProposal,
    ) -> AgentContextRequest:
        prefix = " Advisory reasoning summary: "
        available = max(0, 4000 - len(request.instruction) - len(prefix))
        advisory = f"{prefix}{proposal.summary[:available]}" if available else ""
        return AgentContextRequest(
            instruction=f"{request.instruction}{advisory}",
            intent=request.intent,
            preferred_agent_id=request.preferred_agent_id,
            include_context=request.include_context,
            max_context_items=request.max_context_items,
            max_excerpt_chars=request.max_excerpt_chars,
            allow_execution=False,
            timezone=request.timezone,
            calendar_reference=request.calendar_reference,
            default_event_duration_minutes=request.default_event_duration_minutes,
            mail_account_reference=request.mail_account_reference,
            mailbox_reference=request.mailbox_reference,
        )
