from cauco_agents import AgentPlanReviewStatus
from fastapi.testclient import TestClient

from cauco_core.execution.models import ExecutionStatus
from cauco_core.executive import ExecutiveState, IntentStatus


def create_pending_review(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/agents/plan-reviews",
        json={"instruction": "Inspect git status"},
    )
    assert response.status_code == 201
    return response.json()


def approve_review(
    client: TestClient,
    pending: dict[str, object],
) -> dict[str, object]:
    response = client.post(
        f"/api/agents/plan-reviews/{pending['review_id']}/approve",
        json={},
    )
    assert response.status_code == 200
    return response.json()


def test_unknown_review_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/executive/reviews/planrev_unknown_review/decision")

    assert response.status_code == 404
    assert response.json() == {"detail": "Plan review not found."}


def test_pending_review_awaits_human_decision(client: TestClient) -> None:
    pending = create_pending_review(client)

    response = client.get(f"/api/executive/reviews/{pending['review_id']}/decision")
    payload = response.json()

    assert response.status_code == 200
    assert payload["next_action"] == "await_human_decision"
    assert payload["requires_human_approval"] is True
    assert payload["transition_permitted"] is False
    assert payload["blocking_reasons"] == ["Plan review is still pending."]


def test_approved_review_without_execution_requests_record_creation(
    client: TestClient,
) -> None:
    approved = approve_review(client, create_pending_review(client))

    response = client.get(f"/api/executive/reviews/{approved['review_id']}/decision")
    payload = response.json()

    assert response.status_code == 200
    assert payload["next_action"] == "create_execution_record"
    assert payload["requires_human_approval"] is True
    assert payload["transition_permitted"] is True
    assert payload["blocking_reasons"] == []


def test_pending_execution_requests_step_approval(
    client: TestClient,
    monkeypatch,
) -> None:
    resolver = client.app.state.executive_state_resolver

    monkeypatch.setattr(
        resolver,
        "resolve",
        lambda review_id: ExecutiveState(
            intent_status=IntentStatus.CLEAR,
            perception_available=True,
            plan_available=True,
            review_status=AgentPlanReviewStatus.APPROVED,
            execution_status=ExecutionStatus.PENDING_EXECUTION,
            execution_record_available=True,
            execution_performed=False,
            outcome_verified=False,
            verification_succeeded=None,
        ),
    )

    response = client.get("/api/executive/reviews/planrev_pending_execution/decision")
    payload = response.json()

    assert response.status_code == 200
    assert payload["next_action"] == "request_step_approval"
    assert payload["requires_human_approval"] is True
    assert payload["transition_permitted"] is True
    assert payload["blocking_reasons"] == []


def test_completed_execution_requests_outcome_verification(
    client: TestClient,
    monkeypatch,
) -> None:
    resolver = client.app.state.executive_state_resolver

    monkeypatch.setattr(
        resolver,
        "resolve",
        lambda review_id: ExecutiveState(
            intent_status=IntentStatus.CLEAR,
            perception_available=True,
            plan_available=True,
            review_status=AgentPlanReviewStatus.APPROVED,
            execution_status=ExecutionStatus.COMPLETED,
            execution_record_available=True,
            execution_performed=True,
            outcome_verified=False,
            verification_succeeded=None,
        ),
    )

    response = client.get("/api/executive/reviews/planrev_completed_execution/decision")
    payload = response.json()

    assert response.status_code == 200
    assert payload["next_action"] == "verify_outcome"
    assert payload["requires_human_approval"] is False
    assert payload["transition_permitted"] is True
    assert payload["blocking_reasons"] == []
