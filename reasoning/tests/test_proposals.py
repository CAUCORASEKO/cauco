from math import inf

import pytest

from cauco_reasoning import ReasoningProposal, ReasoningProposalStep


def test_proposal_rejects_non_advisory_step_objects() -> None:
    with pytest.raises(ValueError, match="advisory reasoning steps"):
        ReasoningProposal(summary="Advice", suggested_steps=(object(),))


def test_step_confirmation_requires_boolean() -> None:
    with pytest.raises(ValueError, match="must be boolean"):
        ReasoningProposalStep("Review", requires_user_confirmation="yes")


@pytest.mark.parametrize("confidence", [True, inf, -0.1, 1.1])
def test_proposal_rejects_invalid_confidence(confidence) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        ReasoningProposal(summary="Advice", confidence=confidence)


def test_proposal_metadata_is_bounded_and_json_compatible() -> None:
    with pytest.raises(ValueError, match="keys must be text"):
        ReasoningProposal(summary="Advice", metadata={1: "value"})
    with pytest.raises(ValueError, match="text is too long"):
        ReasoningProposal(summary="Advice", metadata={"value": "x" * 4001})
    with pytest.raises(ValueError, match="numbers must be finite"):
        ReasoningProposal(summary="Advice", metadata={"value": inf})


def test_proposal_metadata_depth_is_bounded() -> None:
    nested = {"level": {"level": {"level": {"level": {"level": {"level": "x"}}}}}}

    with pytest.raises(ValueError, match="nesting is too deep"):
        ReasoningProposal(summary="Advice", metadata=nested)
