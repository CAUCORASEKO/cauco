import pytest

from cauco_reasoning import ReasoningRequest, ReasoningResult


def test_reasoning_request_normalizes_instruction() -> None:
    request = ReasoningRequest(
        instruction="  Revisa   mis correos  ",
        agent_id="email",
        context={"mailbox": "inbox"},
    )

    assert request.instruction == "Revisa mis correos"
    assert request.agent_id == "email"
    assert request.context["mailbox"] == "inbox"


def test_reasoning_request_rejects_empty_instruction() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ReasoningRequest(instruction="   ")


def test_reasoning_request_context_is_immutable() -> None:
    source = {"language": "es"}

    request = ReasoningRequest(
        instruction="Review mail",
        context=source,
    )

    source["language"] = "en"

    assert request.context["language"] == "es"

    with pytest.raises(TypeError):
        request.context["language"] = "fi"  # type: ignore[index]


def test_reasoning_result_is_provider_neutral() -> None:
    result = ReasoningResult(
        provider="local",
        model="example-model",
        text="proposal",
        structured_data={"kind": "plan"},
        reasoning_performed=True,
    )

    assert result.provider == "local"
    assert result.model == "example-model"
    assert result.text == "proposal"
    assert result.structured_data["kind"] == "plan"
    assert result.reasoning_performed is True
