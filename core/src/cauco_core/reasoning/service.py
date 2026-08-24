import logging
from dataclasses import dataclass

from cauco_reasoning import (
    ReasoningDecision,
    ReasoningRequest,
    ReasoningRequirement,
    ReasoningRequirementResolver,
    ReasoningResult,
    ReasoningService,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReasoningOutcome:
    """Advisory reasoning outcome; it does not execute or mutate anything."""

    requirement: ReasoningRequirement
    reasoning_invoked: bool
    result: ReasoningResult | None = None
    explanation: str = ""
    execution_performed: bool = False
    mutation_performed: bool = False


class ReasoningOrchestrationService:
    """Routes requests to reasoning without creating an execution path."""

    def __init__(
        self,
        resolver: ReasoningRequirementResolver,
        reasoning_service: ReasoningService,
    ) -> None:
        self.resolver = resolver
        self.reasoning_service = reasoning_service

    def assess(self, request: ReasoningRequest) -> ReasoningOutcome:
        decision = self.resolver.resolve(request)
        if decision.requirement is not ReasoningRequirement.REASONING_REQUIRED:
            return self._not_invoked(decision)

        try:
            result = self.reasoning_service.reason(request)
        except Exception:
            logger.exception("Reasoning provider failed during advisory assessment")
            return ReasoningOutcome(
                requirement=decision.requirement,
                reasoning_invoked=True,
                explanation=(
                    "Reasoning was required but the provider failed safely; "
                    "no execution was performed."
                ),
            )
        if not result.reasoning_performed:
            return ReasoningOutcome(
                requirement=decision.requirement,
                reasoning_invoked=True,
                result=result,
                explanation="Reasoning was required but the provider did not complete safely.",
            )
        return ReasoningOutcome(
            requirement=decision.requirement,
            reasoning_invoked=True,
            result=result,
            explanation="Reasoning completed as an advisory result; no execution was performed.",
        )

    @staticmethod
    def _not_invoked(decision: ReasoningDecision) -> ReasoningOutcome:
        if decision.requirement is ReasoningRequirement.DETERMINISTIC:
            explanation = "Reasoning was not required; no reasoning provider was invoked."
        else:
            explanation = "Reasoning requirement was undecided; no reasoning provider was invoked."
        return ReasoningOutcome(
            requirement=decision.requirement,
            reasoning_invoked=False,
            explanation=explanation,
        )
