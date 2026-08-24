from cauco_reasoning import (
    ReasoningProposal,
    ReasoningRequest,
    ReasoningRequirement,
    ReasoningRequirementResolver,
    ReasoningResult,
    ReasoningService,
)

from cauco_core.reasoning import ReasoningOrchestrationService


class RecordingEngine:
    def __init__(self, result: ReasoningResult | None = None) -> None:
        self.calls = 0
        self.result = result or ReasoningResult(
            provider="test",
            model="test-model",
            text="advice",
            reasoning_performed=True,
        )

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.calls += 1
        return self.result


def make_service(engine: RecordingEngine) -> ReasoningOrchestrationService:
    return ReasoningOrchestrationService(
        ReasoningRequirementResolver(),
        ReasoningService(engine),
    )


def test_deterministic_request_does_not_invoke_reasoning() -> None:
    engine = RecordingEngine()

    outcome = make_service(engine).assess(ReasoningRequest("list my notes"))

    assert outcome.requirement is ReasoningRequirement.DETERMINISTIC
    assert outcome.reasoning_invoked is False
    assert outcome.result is None
    assert engine.calls == 0


def test_reasoning_required_request_invokes_provider_once() -> None:
    engine = RecordingEngine()

    outcome = make_service(engine).assess(ReasoningRequest("analyze this request"))

    assert outcome.requirement is ReasoningRequirement.REASONING_REQUIRED
    assert outcome.reasoning_invoked is True
    assert outcome.result is engine.result
    assert engine.calls == 1


def test_undecided_request_does_not_invoke_reasoning() -> None:
    engine = RecordingEngine()

    outcome = make_service(engine).assess(ReasoningRequest("process this item"))

    assert outcome.requirement is ReasoningRequirement.UNDECIDED
    assert outcome.reasoning_invoked is False
    assert outcome.result is None
    assert engine.calls == 0


def test_provider_failure_is_safe_and_non_executing() -> None:
    failure = ReasoningResult(
        provider="test",
        model="test-model",
        text="",
        structured_data={"reason": "provider_unavailable"},
        reasoning_performed=False,
    )
    engine = RecordingEngine(failure)

    outcome = make_service(engine).assess(ReasoningRequest("compare these options"))

    assert outcome.reasoning_invoked is True
    assert outcome.result is failure
    assert outcome.explanation == "Reasoning was required but the provider did not complete safely."
    assert engine.calls == 1


def test_failed_result_proposal_is_never_validated() -> None:
    class RejectValidation:
        def validate(self, proposal):
            raise AssertionError("failed provider proposal must not be validated")

    failure = ReasoningResult(
        provider="test",
        model="test-model",
        text="",
        reasoning_performed=False,
        proposal=ReasoningProposal(summary="Untrusted failed advice"),
    )
    engine = RecordingEngine(failure)
    service = ReasoningOrchestrationService(
        ReasoningRequirementResolver(),
        ReasoningService(engine),
        RejectValidation(),
    )

    outcome = service.assess(ReasoningRequest("compare these options"))

    assert outcome.proposal is failure.proposal
    assert outcome.validated_proposal is None


def test_provider_exception_is_safe_and_non_executing() -> None:
    class FailingEngine(RecordingEngine):
        def reason(self, request: ReasoningRequest) -> ReasoningResult:
            self.calls += 1
            raise RuntimeError("secret provider details")

    engine = FailingEngine()

    outcome = make_service(engine).assess(ReasoningRequest("compare these options"))

    assert outcome.reasoning_invoked is True
    assert outcome.result is None
    assert "secret" not in outcome.explanation
    assert engine.calls == 1


def test_reasoning_boundary_exposes_no_execution_or_mutation_path() -> None:
    engine = RecordingEngine()
    service = make_service(engine)

    outcome = service.assess(ReasoningRequest("recommend an approach"))

    assert outcome.result is engine.result
    assert not hasattr(outcome.result, "execute")
    assert not hasattr(service, "execution_service")
    assert not hasattr(service, "mutation_service")
    assert not hasattr(service, "tool_registry")


def test_reasoning_outcome_never_claims_execution_or_mutation() -> None:
    engine = RecordingEngine()

    outcomes = (
        make_service(engine).assess(ReasoningRequest("list my notes")),
        make_service(engine).assess(ReasoningRequest("analyze these options")),
        make_service(engine).assess(ReasoningRequest("process this item")),
    )

    for outcome in outcomes:
        assert outcome.execution_performed is False
        assert outcome.mutation_performed is False
