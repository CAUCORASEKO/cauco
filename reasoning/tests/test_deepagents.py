import sys
import types

from cauco_reasoning import DeepAgentsReasoningEngine, ReasoningRequest
from cauco_reasoning.providers.deepagents import (
    _EXCLUDED_TOOLS,
    _INITIALIZED_MODELS,
    initialize_deepagents_harness,
)


def test_provider_construction_and_request_forwarding() -> None:
    calls = []

    def runtime(**kwargs):
        calls.append(kwargs)
        return {"messages": [{"content": "answer"}]}

    engine = DeepAgentsReasoningEngine("test-model", provider_name="test-provider", runtime=runtime)
    result = engine.reason(ReasoningRequest("Do this", agent_id="agent", context={"x": "y"}))

    assert calls[0]["model"] == "test-model"
    assert calls[0]["tools"] == []
    assert "Do this" in calls[0]["messages"][0]["content"]
    assert "x: y" in calls[0]["messages"][0]["content"]
    assert result.provider == "test-provider"
    assert result.model == "test-model"
    assert result.text == "answer"
    assert result.reasoning_performed is True


def test_provider_failure_is_safe_and_has_no_side_effect_path() -> None:
    mutations = []

    def failing_runtime(**kwargs):
        mutations.append(kwargs.get("tools"))
        raise RuntimeError("secret=do-not-leak")

    result = DeepAgentsReasoningEngine("model", runtime=failing_runtime).reason(
        ReasoningRequest("reason")
    )

    assert result.reasoning_performed is False
    assert result.text == ""
    assert result.structured_data["reason"] == "provider_unavailable"
    assert "secret" not in str(result.structured_data)
    assert mutations == [[]]


def test_repeated_harness_initialization_registers_once(monkeypatch) -> None:
    registered = []

    class HarnessProfile:
        def __init__(self, *, excluded_tools, general_purpose_subagent):
            self.excluded_tools = excluded_tools
            self.general_purpose_subagent = general_purpose_subagent

    class GeneralPurposeSubagentProfile:
        def __init__(self, *, enabled):
            self.enabled = enabled

    def register(model, profile):
        registered.append((model, profile))

    fake_deepagents = types.ModuleType("deepagents")
    fake_deepagents.HarnessProfile = HarnessProfile
    fake_deepagents.GeneralPurposeSubagentProfile = GeneralPurposeSubagentProfile
    fake_deepagents.register_harness_profile = register
    monkeypatch.setitem(sys.modules, "deepagents", fake_deepagents)

    for model in ("model-once", "model-twice"):
        _INITIALIZED_MODELS.discard(model)
        initialize_deepagents_harness(model)
        initialize_deepagents_harness(model)

    assert [model for model, _ in registered] == ["model-once", "model-twice"]
    for _, profile in registered:
        assert profile.excluded_tools == _EXCLUDED_TOOLS
        assert profile.general_purpose_subagent.enabled is False


def test_text_content_blocks_are_converted_without_repr() -> None:
    class Message:
        def __init__(self) -> None:
            self.content = [
                {"type": "text", "text": "first"},
                {"text": " second"},
            ]

    calls = []
    engine = DeepAgentsReasoningEngine(
        "model",
        runtime=lambda **kwargs: calls.append(kwargs) or {"messages": [Message()]},
    )
    result = engine.reason(ReasoningRequest("reason"))

    assert result.text == "first second"
    assert "{" not in result.text
    assert calls[0]["tools"] == []


def test_pydantic_style_structured_response_is_json_compatible() -> None:
    class Structured:
        def model_dump(self):
            return {"answer": "ok", "items": (1, True)}

    result = DeepAgentsReasoningEngine(
        "model", runtime=lambda **kwargs: {"structured_response": Structured()}
    ).reason(ReasoningRequest("reason"))

    assert result.structured_data["answer"] == "ok"
    assert result.structured_data["items"] == [1, True]
