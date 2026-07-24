import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


@pytest.fixture
def experience_client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    subprocess.run(
        ["git", "init", "-q", str(workspace)],
        check=True,
    )

    (workspace / "README.md").write_text(
        "# Cauco experience test\n",
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
) -> dict[str, object]:
    created = client.post(
        "/api/agents/plan-reviews",
        json={"instruction": "Inspect git status"},
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


def create_experience(
    client: TestClient,
    verification_id: str,
) -> dict[str, object]:
    response = client.post(
        f"/api/experiences/verifications/{verification_id}",
    )
    assert response.status_code == 201
    return response.json()


def complete_cycle(
    client: TestClient,
) -> tuple[
    dict[str, object],
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
    experience = create_experience(
        client,
        str(verification["verification_id"]),
    )
    return review, completed, verification, experience


def test_create_and_get_experience(
    experience_client: TestClient,
) -> None:
    review, execution, verification, created = complete_cycle(experience_client)

    response = experience_client.get(
        f"/api/experiences/{created['experience_id']}",
    )

    assert response.status_code == 200
    assert response.json() == created

    assert created["review_id"] == review["review_id"]
    assert created["execution_id"] == execution["execution_id"]
    assert created["verification_id"] == verification["verification_id"]
    assert created["snapshot_digest"] == review["snapshot_digest"]
    assert created["method"] == ("deterministic_verification_consolidation_v1")
    assert created["outcome"] in {
        "success",
        "partial",
        "failure",
        "inconclusive",
    }
    assert isinstance(created["lesson_candidates"], list)
    assert isinstance(created["memory_candidate"], bool)


def test_get_experience_by_verification(
    experience_client: TestClient,
) -> None:
    _, _, verification, created = complete_cycle(experience_client)

    response = experience_client.get(
        (f"/api/experiences/verifications/{verification['verification_id']}"),
    )

    assert response.status_code == 200
    assert response.json() == created


def test_list_filters_and_limit(
    experience_client: TestClient,
) -> None:
    review, _, _, created = complete_cycle(experience_client)

    listed = experience_client.get(
        "/api/experiences",
        params={
            "review_id": review["review_id"],
            "outcome": created["outcome"],
            "memory_candidate": created["memory_candidate"],
            "limit": 1,
        },
    )

    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["experiences"] == [created]

    unmatched = experience_client.get(
        "/api/experiences",
        params={"review_id": "planrev_unknown"},
    )

    assert unmatched.status_code == 200
    assert unmatched.json() == {
        "experiences": [],
        "count": 0,
    }


def test_duplicate_consolidation_returns_conflict(
    experience_client: TestClient,
) -> None:
    _, _, verification, created = complete_cycle(experience_client)

    repeated = experience_client.post(
        (f"/api/experiences/verifications/{verification['verification_id']}"),
    )

    assert created["experience_id"]
    assert repeated.status_code == 409
    assert "already exists" in repeated.json()["detail"].lower()


def test_unknown_verification_returns_not_found(
    experience_client: TestClient,
) -> None:
    response = experience_client.post(
        "/api/experiences/verifications/verify_unknown",
    )

    assert response.status_code == 404


def test_unknown_experience_resources_return_not_found(
    experience_client: TestClient,
) -> None:
    by_id = experience_client.get(
        "/api/experiences/experience_unknown",
    )
    by_verification = experience_client.get(
        "/api/experiences/verifications/verify_unknown",
    )

    assert by_id.status_code == 404
    assert by_verification.status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"outcome": "unknown"},
        {"review_id": "x" * 101},
        {"memory_candidate": "not-a-boolean"},
    ],
)
def test_list_query_validation(
    experience_client: TestClient,
    params: dict[str, object],
) -> None:
    response = experience_client.get(
        "/api/experiences",
        params=params,
    )

    assert response.status_code == 422
