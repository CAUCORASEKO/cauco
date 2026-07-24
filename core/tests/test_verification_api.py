import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


@pytest.fixture
def verification_client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    subprocess.run(
        ["git", "init", "-q", str(workspace)],
        check=True,
    )
    (workspace / "README.md").write_text(
        "# Cauco verification test\n",
        encoding="utf-8",
    )

    settings = Settings(
        brain_dir=brain,
        workspace_dir=workspace,
        database_path=tmp_path / "runtime" / "cauco.db",
    )

    with TestClient(create_app(settings)) as client:
        yield client


def create_approved_review(
    client: TestClient,
    instruction: str = "Inspect git status",
) -> dict[str, object]:
    created = client.post(
        "/api/agents/plan-reviews",
        json={"instruction": instruction},
    )
    assert created.status_code == 201

    approved = client.post(
        (f"/api/agents/plan-reviews/{created.json()['review_id']}/approve"),
        json={},
    )
    assert approved.status_code == 200
    return approved.json()


def create_execution(
    client: TestClient,
    review: dict[str, object],
) -> dict[str, object]:
    response = client.post(
        "/api/executions",
        json={"review_id": review["review_id"]},
    )
    assert response.status_code == 201
    return response.json()


def complete_execution(
    client: TestClient,
    execution: dict[str, object],
) -> dict[str, object]:
    current = execution

    for step in execution["step_records"]:
        if step["status"] != "pending":
            continue

        response = client.post(
            (f"/api/executions/{execution['execution_id']}/steps/{step['step_index']}/execute"),
            json={},
        )
        assert response.status_code == 200
        current = response.json()

    assert current["status"] in {"completed", "failed"}
    assert current["execution_performed"] is True
    return current


def create_verification(
    client: TestClient,
    review_id: str,
) -> dict[str, object]:
    response = client.post(
        f"/api/verifications/reviews/{review_id}",
    )
    assert response.status_code == 201
    return response.json()


def terminal_execution_with_verification(
    client: TestClient,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    review = create_approved_review(client)
    execution = create_execution(client, review)
    completed = complete_execution(client, execution)
    verification = create_verification(
        client,
        str(review["review_id"]),
    )
    return review, completed, verification


def test_create_and_get_verification(
    verification_client: TestClient,
) -> None:
    review, execution, created = terminal_execution_with_verification(
        verification_client,
    )

    response = verification_client.get(
        f"/api/verifications/{created['verification_id']}",
    )

    assert response.status_code == 200

    restored = response.json()

    assert restored == created
    assert restored["review_id"] == review["review_id"]
    assert restored["execution_id"] == execution["execution_id"]
    assert restored["snapshot_digest"] == review["snapshot_digest"]
    assert restored["method"] == ("approved_plan_execution_evidence_v1")
    assert restored["step_results"]
    assert restored["outcome"] in {
        "succeeded",
        "partial_success",
        "failed",
        "insufficient_evidence",
    }
    assert restored["recommendation"] in {
        "complete",
        "request_review",
        "stop",
    }


def test_get_verification_by_execution(
    verification_client: TestClient,
) -> None:
    _, execution, created = terminal_execution_with_verification(
        verification_client,
    )

    response = verification_client.get(
        (f"/api/verifications/executions/{execution['execution_id']}"),
    )

    assert response.status_code == 200
    assert response.json() == created


def test_list_filters_and_limit(
    verification_client: TestClient,
) -> None:
    review, _, created = terminal_execution_with_verification(
        verification_client,
    )

    listed = verification_client.get(
        "/api/verifications",
        params={
            "review_id": review["review_id"],
            "outcome": created["outcome"],
            "limit": 1,
        },
    )

    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["verifications"] == [created]

    unmatched = verification_client.get(
        "/api/verifications",
        params={"review_id": "planrev_unknown"},
    )

    assert unmatched.status_code == 200
    assert unmatched.json() == {
        "verifications": [],
        "count": 0,
    }


def test_duplicate_verification_returns_conflict(
    verification_client: TestClient,
) -> None:
    review, _, created = terminal_execution_with_verification(
        verification_client,
    )

    repeated = verification_client.post(
        f"/api/verifications/reviews/{review['review_id']}",
    )

    assert created["verification_id"]
    assert repeated.status_code == 409
    assert "already exists" in repeated.json()["detail"].lower()


def test_unknown_review_returns_not_found(
    verification_client: TestClient,
) -> None:
    response = verification_client.post(
        "/api/verifications/reviews/planrev_unknown",
    )

    assert response.status_code == 404


def test_review_without_execution_returns_validation_error(
    verification_client: TestClient,
) -> None:
    review = create_approved_review(verification_client)

    response = verification_client.post(
        f"/api/verifications/reviews/{review['review_id']}",
    )

    assert response.status_code == 422
    assert "no execution record" in response.json()["detail"].lower()


def test_pending_execution_cannot_be_verified(
    verification_client: TestClient,
) -> None:
    review = create_approved_review(verification_client)
    create_execution(verification_client, review)

    response = verification_client.post(
        f"/api/verifications/reviews/{review['review_id']}",
    )

    assert response.status_code == 409
    assert "terminal performed executions" in response.json()["detail"].lower()


def test_unknown_verification_and_execution_return_not_found(
    verification_client: TestClient,
) -> None:
    unknown_verification = verification_client.get(
        "/api/verifications/verify_unknown",
    )
    unknown_execution = verification_client.get(
        "/api/verifications/executions/exec_unknown",
    )

    assert unknown_verification.status_code == 404
    assert unknown_execution.status_code == 404


@pytest.mark.parametrize(
    ("params", "expected_status"),
    [
        ({"limit": 0}, 422),
        ({"limit": 101}, 422),
        ({"outcome": "unknown"}, 422),
        ({"review_id": "x" * 101}, 422),
    ],
)
def test_list_query_validation(
    verification_client: TestClient,
    params: dict[str, object],
    expected_status: int,
) -> None:
    response = verification_client.get(
        "/api/verifications",
        params=params,
    )

    assert response.status_code == expected_status
