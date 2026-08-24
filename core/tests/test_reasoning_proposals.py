import pytest
from cauco_agents import AgentContextRequest, AgentPlanStep, create_default_registry
from cauco_reasoning import ReasoningProposal, ReasoningProposalStep

from cauco_core.reasoning import (
    ReasoningPlanningBridge,
    ReasoningProposalValidator,
)


def proposal() -> ReasoningProposal:
    return ReasoningProposal(
        summary="Compare the available options.",
        rationale=("The request is ambiguous.",),
        suggested_steps=(
            ReasoningProposalStep(
                "Compare the options", suggested_agent_id="research", suggested_intent="Compare"
            ),
        ),
        metadata={"source": "advisory"},
    )


def test_validator_accepts_advisory_proposal_and_normalizes_intent() -> None:
    validated = ReasoningProposalValidator(create_default_registry()).validate(proposal())

    assert validated.summary == "Compare the available options."
    assert validated.suggested_steps[0].suggested_intent == "compare"
    assert validated.metadata == {"source": "advisory"}


def test_validator_rejects_unknown_agent() -> None:
    invalid = ReasoningProposal(
        summary="Advice",
        suggested_steps=(ReasoningProposalStep("Do something", suggested_agent_id="unknown"),),
    )

    with pytest.raises(ValueError, match="unknown agent"):
        ReasoningProposalValidator(create_default_registry()).validate(invalid)


def test_bridge_always_creates_non_executing_context_request() -> None:
    validator = ReasoningProposalValidator(create_default_registry())
    bridge = ReasoningPlanningBridge()

    request = bridge.to_context_request(
        AgentContextRequest("Original request", allow_execution=True),
        validator.validate(proposal()),
    )

    assert isinstance(request, AgentContextRequest)
    assert request.allow_execution is False
    assert "Compare the available options." in request.instruction
    assert request.preferred_agent_id is None


def test_validated_proposal_is_deeply_immutable() -> None:
    validated = ReasoningProposalValidator(create_default_registry()).validate(
        ReasoningProposal(summary="Advice", metadata={"nested": {"value": "safe"}})
    )

    with pytest.raises(TypeError):
        validated.metadata["new"] = "value"
    with pytest.raises(TypeError):
        validated.metadata["nested"]["value"] = "changed"
    with pytest.raises(AttributeError):
        validated.suggested_steps = ()


def test_validated_steps_never_become_executable_plan_steps() -> None:
    validated = ReasoningProposalValidator(create_default_registry()).validate(proposal())

    assert all(not isinstance(step, AgentPlanStep) for step in validated.suggested_steps)


def test_proposal_bounds_and_metadata_are_defensive() -> None:
    with pytest.raises(ValueError):
        ReasoningProposal(
            summary="x",
            suggested_steps=tuple(ReasoningProposalStep("x") for _ in range(13)),
        )
    with pytest.raises(ValueError):
        ReasoningProposal(summary="x", metadata={"bad": object()})
