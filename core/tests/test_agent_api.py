from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_agent_list_exposes_registered_metadata(client: TestClient) -> None:
    response = client.get("/api/agents")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert [agent["id"] for agent in payload["agents"]] == ["git", "project", "research"]
    assert all(agent["version"] == "1.0.0" for agent in payload["agents"])
    assert all(agent["capabilities"] for agent in payload["agents"])


def test_agent_detail_and_unknown_agent(client: TestClient) -> None:
    detail = client.get("/api/agents/git")
    missing = client.get("/api/agents/missing")

    assert detail.status_code == 200
    assert detail.json()["name"] == "Git Agent"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Unknown agent 'missing'."


@pytest.mark.parametrize(
    ("instruction", "agent_id", "signal"),
    [
        ("What should I work on next in Cauco?", "project", "work on"),
        ("Commit my latest changes.", "git", "commit"),
        ("Research MCP support for local assistants.", "research", "research"),
    ],
)
def test_route_api_selects_builtin_agents(
    client: TestClient, instruction: str, agent_id: str, signal: str
) -> None:
    response = client.post("/api/agents/route", json={"instruction": instruction})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "matched"
    assert payload["routing_threshold"] == 40
    assert payload["selected_agent"]["id"] == agent_id
    assert signal in payload["match"]["matched_signals"]
    assert payload["result"]["execution_performed"] is False
    assert payload["result"]["status"] == "proposal_only"


def test_route_api_returns_explicit_no_match(client: TestClient) -> None:
    response = client.post("/api/agents/route", json={"instruction": "Tell me a joke."})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "no_match"
    assert payload["selected_agent"] is None
    assert payload["match"] is None
    assert payload["result"] is None
    assert len(payload["matches"]) == 3


def test_route_api_normalizes_request_and_ignores_execution(client: TestClient) -> None:
    response = client.post(
        "/api/agents/route",
        json={
            "instruction": "  Commit   my\nchanges. ",
            "allow_execution": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request"]["instruction"] == "Commit my changes."
    assert payload["request"]["allow_execution"] is True
    assert payload["result"]["execution_performed"] is False
    assert any("ignored" in warning for warning in payload["result"]["warnings"])


def test_route_api_rejects_empty_and_structurally_invalid_requests(client: TestClient) -> None:
    empty = client.post("/api/agents/route", json={"instruction": " \n "})
    missing = client.post("/api/agents/route", json={})
    extra = client.post(
        "/api/agents/route",
        json={"instruction": "Plan work", "routing_score": 100},
    )

    assert empty.status_code == 400
    assert missing.status_code == 422
    assert extra.status_code == 422


def test_route_api_handles_preferred_agents(client: TestClient) -> None:
    unrelated = client.post(
        "/api/agents/route",
        json={"instruction": "Research MCP", "preferred_agent_id": "git"},
    )
    unknown = client.post(
        "/api/agents/route",
        json={"instruction": "Research MCP", "preferred_agent_id": "unknown"},
    )

    assert unrelated.status_code == 200
    assert unrelated.json()["selected_agent"]["id"] == "research"
    assert unrelated.json()["preferred_agent_rejected"] is True
    assert unknown.status_code == 404


def test_agent_responses_expose_no_absolute_paths(
    client: TestClient, brain_dir: Path
) -> None:
    listed = client.get("/api/agents")
    routed = client.post(
        "/api/agents/route", json={"instruction": "Review repository status"}
    )

    assert str(brain_dir) not in listed.text
    assert str(brain_dir) not in routed.text
    assert str(Path.cwd()) not in routed.text
