from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


@pytest.fixture
def review_client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Tasks.md").write_text(
        "# Tasks\n\n## Current Priorities\n\n- Finish Phase 5C\n", encoding="utf-8"
    )
    (brain / "Projects.md").write_text(
        "# Projects\n\n## Active\n\n### Cauco\n\nStatus: plan review.\n",
        encoding="utf-8",
    )
    (brain / "Decisions.md").write_text(
        "# Decisions\n\nApproval is not execution.\n", encoding="utf-8"
    )
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        yield client


def create_review(client: TestClient, instruction: str = "Plan the Cauco project"):
    response = client.post("/api/agents/plan-reviews", json={"instruction": instruction})
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize(
    ("instruction", "agent_id"),
    [
        ("What should I work on next in Cauco?", "project"),
        ("Commit my latest Cauco changes.", "git"),
        ("Research MCP support for Cauco.", "research"),
    ],
)
def test_create_review_for_each_planning_agent(
    review_client: TestClient, instruction: str, agent_id: str
) -> None:
    response = review_client.post(
        "/api/agents/plan-reviews",
        json={"instruction": instruction, "allow_execution": True},
    )
    payload = response.json()

    assert response.status_code == 201
    assert payload["status"] == "pending_review"
    assert payload["selected_agent_id"] == agent_id
    assert payload["routing"]["selected_agent"]["id"] == agent_id
    assert payload["context"]["agent_id"] == agent_id
    assert payload["plan"]["agent_id"] == agent_id
    assert payload["execution_authorized"] is False
    assert payload["execution_performed"] is False
    assert len(payload["snapshot_digest"]) == 64


def test_create_stores_exact_planning_context_and_plan(review_client: TestClient) -> None:
    request = {"instruction": "Plan the Cauco project", "max_context_items": 2}
    planned = review_client.post("/api/agents/plan", json=request).json()
    reviewed = review_client.post("/api/agents/plan-reviews", json=request).json()
    retrieved = review_client.get(
        f"/api/agents/plan-reviews/{reviewed['review_id']}"
    ).json()

    assert reviewed["context"] == planned["context"]
    assert reviewed["plan"] == planned["plan"]
    assert retrieved == reviewed


def test_approve_reject_cancel_and_conflict_statuses(review_client: TestClient) -> None:
    approved_pending = create_review(review_client)
    approved = review_client.post(
        f"/api/agents/plan-reviews/{approved_pending['review_id']}/approve",
        json={"reviewer_note": "Reviewed for possible future execution."},
    )
    repeated = review_client.post(
        f"/api/agents/plan-reviews/{approved_pending['review_id']}/approve", json={}
    )
    rejected_pending = create_review(review_client)
    rejected = review_client.post(
        f"/api/agents/plan-reviews/{rejected_pending['review_id']}/reject",
        json={"reason": "The scope is too broad.", "reviewer_note": "Make it smaller."},
    )
    cancelled_pending = create_review(review_client)
    cancelled = review_client.post(
        f"/api/agents/plan-reviews/{cancelled_pending['review_id']}/cancel",
        json={"reason": "No longer needed."},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["execution_authorized"] is True
    assert approved.json()["execution_performed"] is False
    assert "No action was executed" in approved.json()["approval_warning"]
    assert approved.json()["plan"] == approved_pending["plan"]
    assert approved.json()["snapshot_digest"] == approved_pending["snapshot_digest"]
    assert repeated.status_code == 409
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "The scope is too broad."
    assert cancelled.json()["status"] == "cancelled"


def test_expired_get_is_visible_but_transitions_conflict(review_client: TestClient) -> None:
    pending = create_review(review_client)
    store = review_client.app.state.agent_plan_review_store
    after_expiry = store.get(pending["review_id"]).expires_at + timedelta(seconds=1)
    store.clock = lambda: after_expiry
    expired = review_client.get(f"/api/agents/plan-reviews/{pending['review_id']}")
    approve = review_client.post(
        f"/api/agents/plan-reviews/{pending['review_id']}/approve", json={}
    )

    assert expired.status_code == 200
    assert expired.json()["status"] == "expired"
    assert approve.status_code == 409


def test_no_match_unknown_and_invalid_inputs(review_client: TestClient) -> None:
    no_match = review_client.post(
        "/api/agents/plan-reviews", json={"instruction": "Tell me a joke."}
    )
    unknown_get = review_client.get("/api/agents/plan-reviews/planrev_unknown")
    unknown_action = review_client.post(
        "/api/agents/plan-reviews/planrev_unknown/approve", json={}
    )
    missing_reason = review_client.post(
        f"/api/agents/plan-reviews/{create_review(review_client)['review_id']}/reject",
        json={},
    )
    short_ttl = review_client.post(
        "/api/agents/plan-reviews",
        json={"instruction": "Plan the Cauco project", "ttl_seconds": 59},
    )
    long_note = review_client.post(
        f"/api/agents/plan-reviews/{create_review(review_client)['review_id']}/approve",
        json={"reviewer_note": "x" * 2001},
    )

    assert no_match.status_code == 409
    assert unknown_get.status_code == 404
    assert unknown_action.status_code == 404
    assert missing_reason.status_code == 422
    assert short_ttl.status_code == 422
    assert long_note.status_code == 422


def test_listing_filters_newest_first_and_exposes_no_absolute_paths(
    review_client: TestClient, tmp_path: Path
) -> None:
    project = create_review(review_client, "Plan the Cauco project")
    git = create_review(review_client, "Review the Git diff")
    response = review_client.get(
        "/api/agents/plan-reviews", params={"status": "pending_review", "agent_id": "git"}
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["reviews"][0]["review_id"] == git["review_id"]
    assert project["review_id"] != git["review_id"]
    assert str(tmp_path) not in response.text
    assert str(Path.cwd()) not in response.text
