from fastapi.testclient import TestClient


def _review(client: TestClient) -> str:
    response = client.post("/api/agents/plan-reviews", json={"instruction": "Plan Cauco"})
    assert response.status_code == 201
    return response.json()["review_id"]


def test_unknown_review_is_not_found(client: TestClient) -> None:
    assert client.get("/api/cognitive-cycles/reviews/missing").status_code == 404


def test_pending_review_is_observed_without_transition(client: TestClient) -> None:
    review_id = _review(client)
    response = client.get(f"/api/cognitive-cycles/reviews/{review_id}")
    assert response.status_code == 200
    assert response.json()["current_stage"] == "awaiting_plan_approval"
    assert client.get(f"/api/agents/plan-reviews/{review_id}").json()["status"] == "pending_review"


def test_approved_review_without_execution_is_ready(client: TestClient) -> None:
    review_id = _review(client)
    assert client.post(f"/api/agents/plan-reviews/{review_id}/approve", json={}).status_code == 200
    payload = client.get(f"/api/cognitive-cycles/reviews/{review_id}").json()
    assert payload["current_stage"] == "ready_for_execution"
    assert payload["next_permitted_action"] == "create_execution"


def test_snapshot_is_immutable(client: TestClient) -> None:
    review_id = _review(client)
    snapshot = client.app.state.cognitive_cycle_resolver.resolve(review_id)
    try:
        snapshot.candidate_counts["pending_review"] = 99
    except TypeError:
        pass
    else:
        raise AssertionError("snapshot mappings must be immutable")
