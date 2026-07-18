from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


@pytest.fixture
def planning_client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Tasks.md").write_text(
        "# Tasks\n\nIntroductory guidance.\n\n"
        "## Current Priorities\n\n- Finish Phase 5B\n\n"
        "## Current Sprint\n\n### Cauco\n\n- Improve context quality.\n",
        encoding="utf-8",
    )
    (brain / "Projects.md").write_text(
        "# Projects\n\nProject index guidance.\n\n"
        "## Active\n\n### Cauco\n\nStatus: Agent context and planning.\n",
        encoding="utf-8",
    )
    (brain / "Decisions.md").write_text(
        "# Decisions\n\nPlanning stays deterministic.\n",
        encoding="utf-8",
    )
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        yield client


@pytest.mark.parametrize(
    ("instruction", "agent_id"),
    [
        ("What should I work on next in Cauco?", "project"),
        ("Commit my latest Cauco changes.", "git"),
        ("Research MCP support for Cauco.", "research"),
    ],
)
def test_planning_api_selects_agent_and_returns_grounded_plan(
    planning_client: TestClient, instruction: str, agent_id: str
) -> None:
    response = planning_client.post("/api/agents/plan", json={"instruction": instruction})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planned"
    assert payload["routing"]["selected_agent"]["id"] == agent_id
    assert payload["context"]["agent_id"] == agent_id
    assert payload["context"]["memory_references"]
    assert payload["plan"]["agent_id"] == agent_id
    assert payload["plan"]["execution_performed"] is False
    assert all(step["execution_available"] is False for step in payload["plan"]["steps"])


def test_project_plan_exposes_memory_provenance(planning_client: TestClient) -> None:
    response = planning_client.post(
        "/api/agents/plan",
        json={"instruction": "Plan the next Cauco project task"},
    )
    payload = response.json()
    references = payload["context"]["memory_references"]
    source_ids = {
        source_id
        for step in payload["plan"]["steps"]
        for source_id in step["source_memory_ids"]
    }

    assert references[0]["name"] == "Tasks.md"
    assert all(reference["reason_selected"] for reference in references)
    assert {reference["memory_id"] for reference in references} & source_ids
    assert "Current Priorities" in references[0]["selected_headings"]
    assert references[0]["excerpt_strategy"] == "project_heading"
    actions = [step["proposed_action"] for step in payload["plan"]["steps"]]
    assert any("Current Priorities" in action for action in actions)
    assert any("Cauco" in action for action in actions)
    assert payload["plan"]["open_questions"]


def test_planning_api_returns_no_match(planning_client: TestClient) -> None:
    response = planning_client.post(
        "/api/agents/plan", json={"instruction": "Tell me a joke."}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_match"
    assert response.json()["context"] is None
    assert response.json()["plan"] is None


def test_planning_api_context_disabled_performs_no_reads(
    planning_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads = 0

    def count_read(memory_id: str):
        nonlocal reads
        reads += 1
        return None

    monkeypatch.setattr(planning_client.app.state.memory_engine, "read_object", count_read)
    response = planning_client.post(
        "/api/agents/plan",
        json={"instruction": "Plan the Cauco project", "include_context": False},
    )
    payload = response.json()
    assert response.status_code == 200
    assert reads == 0
    assert payload["context"]["memory_references"] == []
    assert payload["plan"]["context_used"] is False
    assert any("disabled" in item for item in payload["context"]["limitations"])


def test_planning_api_allow_execution_remains_inert(planning_client: TestClient) -> None:
    response = planning_client.post(
        "/api/agents/plan",
        json={"instruction": "Push the latest commit", "allow_execution": True},
    )
    plan = response.json()["plan"]
    assert response.status_code == 200
    assert plan["execution_performed"] is False
    assert any("allow_execution was ignored" in warning for warning in plan["warnings"])


def test_explicit_agent_planning_is_inspectable_but_not_forced(
    planning_client: TestClient,
) -> None:
    planned = planning_client.post(
        "/api/agents/git/plan", json={"instruction": "Review the Git diff"}
    )
    unrelated = planning_client.post(
        "/api/agents/git/plan", json={"instruction": "Research MCP"}
    )
    missing = planning_client.post(
        "/api/agents/missing/plan", json={"instruction": "Plan work"}
    )

    assert planned.status_code == 200
    assert planned.json()["plan"]["agent_id"] == "git"
    assert unrelated.status_code == 400
    assert missing.status_code == 404


def test_planning_request_validation_rejects_paths_and_bad_limits(
    planning_client: TestClient,
) -> None:
    arbitrary_path = planning_client.post(
        "/api/agents/plan",
        json={"instruction": "Plan work", "path": "/etc/passwd"},
    )
    too_many = planning_client.post(
        "/api/agents/plan",
        json={"instruction": "Plan work", "max_context_items": 9},
    )
    short_excerpt = planning_client.post(
        "/api/agents/plan",
        json={"instruction": "Plan work", "max_excerpt_chars": 99},
    )
    empty = planning_client.post("/api/agents/plan", json={"instruction": " \n "})

    assert arbitrary_path.status_code == 422
    assert too_many.status_code == 422
    assert short_excerpt.status_code == 422
    assert empty.status_code == 400


def test_planning_api_exposes_no_absolute_paths(
    planning_client: TestClient, tmp_path: Path
) -> None:
    response = planning_client.post(
        "/api/agents/plan", json={"instruction": "Plan the Cauco project"}
    )
    assert response.status_code == 200
    assert str(tmp_path) not in response.text
    assert str(Path.cwd()) not in response.text
