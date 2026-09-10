from collections.abc import Iterator
from pathlib import Path

import pytest
from cauco_reasoning import (
    ReasoningProposal,
    ReasoningProposalStep,
    ReasoningRequest,
    ReasoningResult,
    ReasoningService,
)
from fastapi.testclient import TestClient

from cauco_core.ai.exceptions import ProviderUnavailableError
from cauco_core.ai.service import AIChatResult
from cauco_core.config import Settings
from cauco_core.main import create_app


class RecordingEngine:
    def __init__(self, result: ReasoningResult) -> None:
        self.result = result
        self.calls = 0

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.calls += 1
        return self.result


class RecordingAIService:
    def __init__(self, response: str = "", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    def chat(self, message: str, model: str | None = None, *, use_memory: bool = True) -> AIChatResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return AIChatResult(
            provider="fake",
            model="fake-model",
            response=self.response,
        )


@pytest.fixture
def reasoning_client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Tasks.md").write_text(
        "# Tasks\n\n## Current Priorities\n\n- Complete reasoning API.\n",
        encoding="utf-8",
    )
    (brain / "Projects.md").write_text(
        "# Projects\n\n## Active\n\n### Cauco\n\nReasoning architecture.\n",
        encoding="utf-8",
    )
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        yield client


def test_reasoning_defaults_false_and_normal_planning_works(
    reasoning_client: TestClient,
) -> None:
    engine = RecordingEngine(
        ReasoningResult(provider="test", model="m", text="unused", reasoning_performed=True)
    )
    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = (
        ReasoningService(engine)
    )

    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={"instruction": "Plan the next Cauco project task"},
    )

    assert response.status_code == 200
    assert response.json()["reasoning_requested"] is False
    assert response.json()["planning"]["status"] == "planned"
    assert engine.calls == 0


def test_reasoning_request_is_non_executing_and_preserves_caller_routing_inputs(
    reasoning_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = ReasoningProposal(
        summary="Use research",
        suggested_steps=(
            ReasoningProposalStep(
                "Research",
                suggested_agent_id="research",
                suggested_intent="provider-intent",
            ),
        ),
    )
    engine = RecordingEngine(
        ReasoningResult(
            provider="test",
            model="m",
            text="advice",
            reasoning_performed=True,
            proposal=proposal,
        )
    )
    orchestration = reasoning_client.app.state.reasoning_orchestration_service
    orchestration.reasoning_service = ReasoningService(engine)
    service = reasoning_client.app.state.reasoning_aware_planning_service
    original_plan = service.plan
    received = []

    def capture(request, **kwargs):
        received.append((request, kwargs))
        return original_plan(request, **kwargs)

    monkeypatch.setattr(service, "plan", capture)
    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={
            "instruction": "Analyze the Cauco project options",
            "intent": "caller-intent",
            "preferred_agent_id": "project",
            "use_reasoning": True,
        },
    )

    assert response.status_code == 200
    assert engine.calls == 1
    assert received[0][0].allow_execution is False
    assert received[0][0].preferred_agent_id == "project"
    assert received[0][0].intent == "caller-intent"
    assert received[0][1] == {"use_reasoning": True}
    payload = response.json()
    assert payload["proposal_validated"] is True
    assert payload["planning_context_enriched"] is True


def test_reasoning_api_rejects_allow_execution(reasoning_client: TestClient) -> None:
    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={"instruction": "Plan work", "allow_execution": True},
    )

    assert response.status_code == 422


def test_default_noop_reasoning_is_safe_when_explicitly_requested(
    reasoning_client: TestClient,
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={
            "instruction": "Analyze the Cauco project options",
            "use_reasoning": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reasoning_requested"] is True
    assert payload["reasoning_invoked"] is True
    assert payload["provider"] == "noop"
    assert payload["proposal_produced"] is False
    assert payload["planning"]["execution_performed"] is False


def test_reasoning_planning_response_is_proposal_only(
    reasoning_client: TestClient,
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={"instruction": "Plan the next Cauco project task"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["planning"]["proposal_only"] is True
    assert payload["planning"]["execution_performed"] is False
    assert payload["planning"]["review_approved"] is False
    assert payload["planning"]["runtime_started"] is False
    for forbidden in (
        "execution_id",
        "mutation_id",
        "review_id",
        "runtime_state",
        "tool_execution_result",
    ):
        assert forbidden not in response.text


def test_provider_failure_falls_back_without_leaking_secrets(
    reasoning_client: TestClient,
) -> None:
    class FailingEngine:
        def reason(self, request: ReasoningRequest) -> ReasoningResult:
            raise RuntimeError("secret-provider-credential")

    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = (
        ReasoningService(FailingEngine())
    )

    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={"instruction": "Analyze the Cauco project options", "use_reasoning": True},
    )

    assert response.status_code == 200
    assert response.json()["reasoning_invoked"] is True
    assert response.json()["planning"]["status"] == "planned"
    assert "secret-provider-credential" not in response.text


def test_reasoning_route_and_service_are_bootstrapped(reasoning_client: TestClient) -> None:
    paths = reasoning_client.get("/openapi.json").json()["paths"]

    assert "/api/reasoning/plan" in paths
    assert reasoning_client.app.state.reasoning_aware_planning_service is not None


def test_conversation_uses_deterministic_plan_without_reasoning(
    reasoning_client: TestClient,
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "Plan the next Cauco project task", "use_reasoning": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_status"] == "planned"
    assert payload["reasoning_invoked"] is False
    assert payload["plan"]["objective"] in payload["message"]
    assert payload["proposal_only"] is True
    assert payload["execution_performed"] is False
    assert payload["review_approved"] is False
    assert payload["runtime_started"] is False


@pytest.mark.parametrize(
    "instruction",
    [
        "What you can do",
        "WHAT DO YOU DO!",
        "What can Cauco do?",
        "How can you help me?",
        "  what can you help me with...  ",
    ],
)
def test_conversation_meta_variants_use_deterministic_fallback_without_provider(
    reasoning_client: TestClient,
    instruction: str,
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": instruction, "use_reasoning": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "advisory" in payload["message"]
    assert payload["planning_status"] == "no_match"
    assert payload["reasoning_invoked"] is False
    assert payload["proposal_only"] is True
    assert payload["execution_performed"] is False
    assert payload["review_approved"] is False
    assert payload["runtime_started"] is False


@pytest.mark.parametrize(
    "instruction",
    ["¿Qué puedes hacer?", "¿Qué sabes hacer?", "¿Cuáles son tus capacidades?", "Dime qué puedes hacer", "What can you do?", "What are your capabilities?"],
)
def test_conversation_capability_inquiry_uses_summary_without_reasoning_or_ai(
    reasoning_client: TestClient, instruction: str
) -> None:
    class FailingEngine:
        def reason(self, request: ReasoningRequest) -> ReasoningResult:
            raise AssertionError("Reasoning must not run for capability inquiry")

    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = ReasoningService(FailingEngine())
    ai_service = RecordingAIService(response="must not be used")
    reasoning_client.app.state.ai_service = ai_service

    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": instruction, "use_reasoning": True},
    )
    assert response.status_code == 200
    assert response.json()["planning_status"] == "capability_summary"
    assert response.json()["reasoning_invoked"] is False
    assert ai_service.calls == 0


@pytest.mark.parametrize(
    "instruction",
    ["Check what I can do on my calendar tomorrow", "What can you do with my calendar tomorrow?"],
)
def test_operational_requests_do_not_use_meta_fallback(
    reasoning_client: TestClient, instruction: str
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": instruction, "use_reasoning": False},
    )
    assert response.status_code == 200
    assert response.json()["planning_status"] == "planned"
    assert response.json()["message"] != "Cauco can help plan and explain tasks in an advisory way. It does not execute actions or change your system from this conversation."


def test_conversation_capability_inquiry_does_not_use_advisory_reasoning(
    reasoning_client: TestClient,
) -> None:
    engine = RecordingEngine(
        ReasoningResult(
            provider="test", model="test-model", text="I can explain Cauco's capabilities.", reasoning_performed=True
        )
    )
    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = ReasoningService(engine)
    ai_service = RecordingAIService(response="AI fallback should not run")
    reasoning_client.app.state.ai_service = ai_service
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "What can you do?", "use_reasoning": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_status"] == "capability_summary"
    assert payload["reasoning_invoked"] is False
    assert payload["plan"] is None
    assert payload["execution_performed"] is False
    assert payload["review_approved"] is False
    assert payload["runtime_started"] is False
    assert engine.calls == 0
    assert ai_service.calls == 0


def test_conversation_noop_uses_existing_ai_service_fallback(
    reasoning_client: TestClient,
) -> None:
    ai_service = RecordingAIService(response="Local AI advisory response.")
    reasoning_client.app.state.ai_service = ai_service

    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "Tell me a short joke", "use_reasoning": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Local AI advisory response."
    assert payload["planning_status"] == "no_match"
    assert payload["plan"] is None
    assert payload["reasoning_invoked"] is True
    assert payload["execution_performed"] is False
    assert ai_service.calls == 1


def test_conversation_empty_reasoning_and_unavailable_ai_returns_503(
    reasoning_client: TestClient,
) -> None:
    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = ReasoningService(
        RecordingEngine(ReasoningResult(provider="test", model="m", text="", reasoning_performed=True))
    )
    ai_service = RecordingAIService(error=ProviderUnavailableError("offline"))
    reasoning_client.app.state.ai_service = ai_service

    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "Tell me a short joke", "use_reasoning": True},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Advisory conversation is unavailable; no action was taken."
    assert ai_service.calls == 1


def test_capability_inquiry_does_not_depend_on_reasoning_or_ai_availability(
    reasoning_client: TestClient,
) -> None:
    class FailingEngine:
        def reason(self, request: ReasoningRequest) -> ReasoningResult:
            raise RuntimeError("provider secret")

    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = ReasoningService(FailingEngine())
    reasoning_client.app.state.ai_service = RecordingAIService(
        error=ProviderUnavailableError("offline")
    )
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "What can you do?", "use_reasoning": True},
    )
    assert response.status_code == 200
    assert response.json()["planning_status"] == "capability_summary"
    assert "provider secret" not in response.text
