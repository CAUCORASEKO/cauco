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

from cauco_core.config import Settings
from cauco_core.main import create_app


class RecordingEngine:
    def __init__(self, result: ReasoningResult) -> None:
        self.result = result
        self.calls = 0

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.calls += 1
        return self.result


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
