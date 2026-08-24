import sys
import types
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from cauco_reasoning import DeepAgentsReasoningEngine
from cauco_reasoning.providers.deepagents import (
    _EXCLUDED_TOOLS,
    _INITIALIZED_MODELS,
    initialize_deepagents_harness,
)
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app

MODEL = "openai:offline-integration-model"
INSTRUCTION = "Analyze the best next step for the Cauco project"


@contextmanager
def client_with_runtime(
    tmp_path: Path,
    runtime: Callable[..., Any],
) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Tasks.md").write_text(
        "# Tasks\n\n## Current Priorities\n\n- Validate advisory reasoning.\n",
        encoding="utf-8",
    )
    (brain / "Projects.md").write_text(
        "# Projects\n\n## Active\n\n### Cauco\n\nReasoning integration.\n",
        encoding="utf-8",
    )
    app = create_app(
        Settings(
            brain_dir=brain,
            reasoning_enabled=True,
            reasoning_provider="deepagents",
            reasoning_model=MODEL,
        )
    )
    configured = app.state.reasoning_service.engine
    assert isinstance(configured, DeepAgentsReasoningEngine)
    app.state.reasoning_service.engine = replace(configured, runtime=runtime)
    with TestClient(app) as client:
        yield client


def test_deepagents_advisory_pipeline_reaches_existing_planner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_calls = []

    def runtime(**kwargs):
        runtime_calls.append(kwargs)
        return {
            "messages": [{"content": "Use the validated advisory proposal."}],
            "structured_response": {
                "reasoning_proposal": {
                    "summary": "Prioritize the current Cauco integration task.",
                    "rationale": ["It is the active project priority."],
                    "suggested_steps": [
                        {
                            "description": "Research unrelated alternatives.",
                            "suggested_agent_id": "research",
                            "suggested_intent": "provider-controlled-intent",
                        }
                    ],
                    "confidence": 0.8,
                }
            },
        }

    with client_with_runtime(tmp_path, runtime) as client:
        service = client.app.state.agent_planning_service
        original_plan = service.plan
        planner_requests = []

        def capture(request, **kwargs):
            planner_requests.append((request, kwargs))
            return original_plan(request, **kwargs)

        monkeypatch.setattr(service, "plan", capture)
        response = client.post(
            "/api/reasoning/plan",
            json={
                "instruction": INSTRUCTION,
                "preferred_agent_id": "project",
                "use_reasoning": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reasoning_requested"] is True
    assert payload["reasoning_invoked"] is True
    assert payload["proposal_produced"] is True
    assert payload["proposal_validated"] is True
    assert payload["planning_context_enriched"] is True
    assert payload["provider"] == "deepagents"
    assert payload["model"] == MODEL
    assert payload["planning"]["proposal_only"] is True
    assert payload["planning"]["execution_performed"] is False
    assert payload["planning"]["review_approved"] is False
    assert payload["planning"]["runtime_started"] is False
    assert payload["planning"]["routing"]["selected_agent"]["id"] == "project"
    assert planner_requests[0][0].preferred_agent_id == "project"
    assert planner_requests[0][0].intent is None
    assert planner_requests[0][0].allow_execution is False
    assert planner_requests[0][1]["required_agent_id"] is None
    assert runtime_calls[0]["model"] == MODEL
    assert runtime_calls[0]["tools"] == []


def test_malformed_deepagents_proposal_falls_back_to_safe_planning(
    tmp_path: Path,
) -> None:
    def runtime(**kwargs):
        return {
            "messages": [{"content": "Malformed advisory data."}],
            "structured_response": {
                "reasoning_proposal": {
                    "summary": "",
                    "suggested_steps": [{"description": object()}],
                }
            },
        }

    with client_with_runtime(tmp_path, runtime) as client:
        response = client.post(
            "/api/reasoning/plan",
            json={
                "instruction": INSTRUCTION,
                "preferred_agent_id": "project",
                "use_reasoning": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["proposal_produced"] is False
    assert payload["proposal_validated"] is False
    assert payload["planning_context_enriched"] is False
    assert payload["planning"]["status"] == "planned"
    assert payload["planning"]["execution_performed"] is False
    assert "object at" not in response.text


def test_deepagents_runtime_failure_is_secret_safe_and_non_executing(
    tmp_path: Path,
) -> None:
    def runtime(**kwargs):
        raise RuntimeError("secret-provider-token-123")

    with client_with_runtime(tmp_path, runtime) as client:
        response = client.post(
            "/api/reasoning/plan",
            json={
                "instruction": INSTRUCTION,
                "preferred_agent_id": "project",
                "use_reasoning": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reasoning_invoked"] is True
    assert payload["proposal_validated"] is False
    assert payload["planning"]["status"] == "planned"
    assert payload["planning"]["execution_performed"] is False
    assert "secret-provider-token-123" not in response.text


def test_restricted_harness_excludes_all_execution_capable_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    model = "openai:harness-integration-model"
    _INITIALIZED_MODELS.discard(model)

    initialize_deepagents_harness(model)

    assert len(registered) == 1
    assert registered[0][1].excluded_tools is _EXCLUDED_TOOLS
    assert registered[0][1].excluded_tools == {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
        "execute",
        "task",
    }
    assert registered[0][1].general_purpose_subagent.enabled is False
