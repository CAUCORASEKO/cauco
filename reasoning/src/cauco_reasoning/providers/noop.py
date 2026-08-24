from dataclasses import dataclass

from cauco_reasoning.models import ReasoningRequest, ReasoningResult


@dataclass(frozen=True, slots=True)
class NoOpReasoningEngine:
    """Reasoning engine used when autonomous reasoning is disabled."""

    provider_name: str = "noop"

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        return ReasoningResult(
            provider=self.provider_name,
            model=None,
            text="",
            structured_data={
                "agent_id": request.agent_id,
                "reason": "reasoning_disabled",
            },
            reasoning_performed=False,
        )
