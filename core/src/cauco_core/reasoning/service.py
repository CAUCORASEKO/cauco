import logging
from dataclasses import dataclass

from cauco_reasoning import (
    ReasoningDecision,
    ReasoningProposal,
    ReasoningRequest,
    ReasoningRequirement,
    ReasoningRequirementResolver,
    ReasoningResult,
    ReasoningService,
)

from cauco_core.reasoning.proposals import (
    ReasoningProposalValidator,
    ValidatedReasoningProposal,
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
    proposal: ReasoningProposal | None = None
    validated_proposal: ValidatedReasoningProposal | None = None


class ReasoningOrchestrationService:
    """Routes requests to reasoning without creating an execution path."""

    def __init__(
        self,
        resolver: ReasoningRequirementResolver,
        reasoning_service: ReasoningService,
        proposal_validator: ReasoningProposalValidator | None = None,
    ) -> None:
        self.resolver = resolver
        self.reasoning_service = reasoning_service
        self.proposal_validator = proposal_validator

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
                proposal=result.proposal,
                explanation="Reasoning was required but the provider did not complete safely.",
            )
        return ReasoningOutcome(
            requirement=decision.requirement,
            reasoning_invoked=True,
            result=result,
            proposal=result.proposal,
            validated_proposal=self._validate(result.proposal),
            explanation="Reasoning completed as an advisory result; no execution was performed.",
        )

    def _validate(
        self, proposal: ReasoningProposal | None
    ) -> ValidatedReasoningProposal | None:
        if proposal is None or self.proposal_validator is None:
            return None
        try:
            return self.proposal_validator.validate(proposal)
        except (TypeError, ValueError):
            return None

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
