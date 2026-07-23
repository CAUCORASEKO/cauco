from fastapi.testclient import TestClient


def base_payload() -> dict[str, object]:
    return {
        "intent_status": "clear",
        "perception_available": False,
        "plan_available": False,
        "review_status": None,
        "execution_status": None,
        "execution_record_available": False,
        "execution_performed": False,
        "outcome_verified": False,
        "verification_succeeded": None,
    }


def test_executive_api_observes_when_perception_is_missing(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/executive/decide",
        json=base_payload(),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["next_action"] == "observe"
    assert payload["requires_human_approval"] is False
    assert payload["transition_permitted"] is True
    assert payload["reason"]
    assert payload["blocking_reasons"] == []


def test_executive_api_waits_for_human_plan_review(
    client: TestClient,
) -> None:
    payload = base_payload()
    payload.update(
        {
            "perception_available": True,
            "plan_available": True,
            "review_status": "pending_review",
        }
    )

    response = client.post(
        "/api/executive/decide",
        json=payload,
    )

    assert response.status_code == 200
    decision = response.json()

    assert decision["next_action"] == "await_human_decision"
    assert decision["requires_human_approval"] is True
    assert decision["transition_permitted"] is False
    assert decision["blocking_reasons"]


def test_executive_api_creates_execution_record_after_approval(
    client: TestClient,
) -> None:
    payload = base_payload()
    payload.update(
        {
            "perception_available": True,
            "plan_available": True,
            "review_status": "approved",
        }
    )

    response = client.post(
        "/api/executive/decide",
        json=payload,
    )

    assert response.status_code == 200
    decision = response.json()

    assert decision["next_action"] == "create_execution_record"
    assert decision["requires_human_approval"] is True
    assert decision["transition_permitted"] is True


def test_executive_api_rejects_inconsistent_state(
    client: TestClient,
) -> None:
    payload = base_payload()
    payload.update(
        {
            "execution_record_available": True,
            "execution_status": "pending_execution",
        }
    )

    response = client.post(
        "/api/executive/decide",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["detail"]


def test_executive_api_rejects_unknown_fields(
    client: TestClient,
) -> None:
    payload = base_payload()
    payload["unknown"] = True

    response = client.post(
        "/api/executive/decide",
        json=payload,
    )

    assert response.status_code == 422


def test_executive_api_rejects_non_strict_booleans(
    client: TestClient,
) -> None:
    payload = base_payload()
    payload["perception_available"] = 1

    response = client.post(
        "/api/executive/decide",
        json=payload,
    )

    assert response.status_code == 422
