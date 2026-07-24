import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    subprocess.run(
        ["git", "init", "-q", str(workspace)],
        check=True,
    )

    (workspace / "README.md").write_text(
        "# Cauco memory candidate API test\n",
        encoding="utf-8",
    )

    settings = Settings(
        brain_dir=brain,
        workspace_dir=workspace,
        database_path=tmp_path / "runtime" / "cauco.db",
    )

    with TestClient(create_app(settings)) as test_client:
        yield test_client


def create_experience(client: TestClient) -> dict[str, object]:
    review = client.post(
        "/api/agents/plan-reviews",
        json={"instruction": "Inspect git status"},
    )
    assert review.status_code == 201

    approved = client.post(
        (f"/api/agents/plan-reviews/{review.json()['review_id']}/approve"),
        json={},
    )
    assert approved.status_code == 200

    execution = client.post(
        "/api/executions",
        json={"review_id": approved.json()["review_id"]},
    )
    assert execution.status_code == 201

    current = execution.json()
    for step in current["step_records"]:
        if step["status"] != "pending":
            continue

        response = client.post(
            (f"/api/executions/{current['execution_id']}/steps/{step['step_index']}/execute"),
            json={},
        )
        assert response.status_code == 200
        current = response.json()

    verification = client.post(
        (f"/api/verifications/reviews/{approved.json()['review_id']}"),
    )
    assert verification.status_code == 201

    experience = client.post(
        (f"/api/experiences/verifications/{verification.json()['verification_id']}"),
    )
    assert experience.status_code == 201

    return experience.json()


def create_candidate(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object]]:
    experience = create_experience(client)

    response = client.post(
        (f"/api/memory-candidates/experiences/{experience['experience_id']}"),
    )
    assert response.status_code == 201
    assert response.json()["count"] >= 1

    return experience, response.json()["candidates"][0]


def test_create_and_get_candidate(client: TestClient) -> None:
    experience, created = create_candidate(client)

    response = client.get(
        f"/api/memory-candidates/{created['candidate_id']}",
    )

    assert response.status_code == 200
    assert response.json() == created
    assert created["experience_id"] == experience["experience_id"]
    assert created["status"] == "pending_review"
    assert created["target"] == "learning"
    assert created["disposition"] is None
    assert created["reviewed_at"] is None
    assert created["method"] == ("deterministic_experience_memory_candidate_v1")
    assert isinstance(created["lesson"], dict)


def test_repeat_creation_is_idempotent(client: TestClient) -> None:
    experience, first = create_candidate(client)

    repeated = client.post(
        (f"/api/memory-candidates/experiences/{experience['experience_id']}"),
    )

    assert repeated.status_code == 201
    assert repeated.json()["candidates"][0] == first


def test_get_candidates_by_experience(client: TestClient) -> None:
    experience, created = create_candidate(client)

    response = client.get(
        (f"/api/memory-candidates/experiences/{experience['experience_id']}"),
    )

    assert response.status_code == 200
    assert created in response.json()["candidates"]


def test_list_filters(client: TestClient) -> None:
    experience, created = create_candidate(client)

    response = client.get(
        "/api/memory-candidates",
        params={
            "experience_id": experience["experience_id"],
            "review_id": created["review_id"],
            "status": "pending_review",
            "target": "learning",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "candidates": [created],
        "count": 1,
    }


def test_approve_candidate(client: TestClient) -> None:
    _, created = create_candidate(client)

    response = client.post(
        (f"/api/memory-candidates/{created['candidate_id']}/approve"),
        json={"review_note": "  Approved manually.  "},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["disposition"] == "promote_to_memory"
    assert payload["review_note"] == "Approved manually."
    assert payload["reviewed_at"] is not None


@pytest.mark.parametrize(
    "disposition",
    [
        "retain_as_experience_only",
        "discard",
    ],
)
def test_reject_candidate(
    client: TestClient,
    disposition: str,
) -> None:
    _, created = create_candidate(client)

    response = client.post(
        (f"/api/memory-candidates/{created['candidate_id']}/reject"),
        json={
            "disposition": disposition,
            "review_note": "Rejected manually.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["disposition"] == disposition
    assert payload["reviewed_at"] is not None


def test_duplicate_review_returns_conflict(
    client: TestClient,
) -> None:
    _, created = create_candidate(client)

    first = client.post(
        (f"/api/memory-candidates/{created['candidate_id']}/approve"),
        json={},
    )
    assert first.status_code == 200

    repeated = client.post(
        (f"/api/memory-candidates/{created['candidate_id']}/reject"),
        json={"disposition": "discard"},
    )

    assert repeated.status_code == 409


def test_invalid_rejection_disposition_returns_422(
    client: TestClient,
) -> None:
    _, created = create_candidate(client)

    response = client.post(
        (f"/api/memory-candidates/{created['candidate_id']}/reject"),
        json={"disposition": "promote_to_memory"},
    )

    assert response.status_code == 422


def test_unknown_experience_returns_404(
    client: TestClient,
) -> None:
    response = client.post(
        ("/api/memory-candidates/experiences/experience_abcdefghijklmnopqrstuvwx"),
    )

    assert response.status_code == 404


def test_unknown_candidate_returns_404(
    client: TestClient,
) -> None:
    response = client.get(
        ("/api/memory-candidates/memory_candidate_abcdefghijklmnopqrstuvwx"),
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "post",
            ("/api/memory-candidates/memory_candidate_abcdefghijklmnopqrstuvwx/approve"),
            {"unknown": True},
        ),
        (
            "post",
            ("/api/memory-candidates/memory_candidate_abcdefghijklmnopqrstuvwx/reject"),
            {"disposition": "unknown"},
        ),
    ],
)
def test_invalid_request_body_returns_422(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, object],
) -> None:
    response = getattr(client, method)(path, json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"status": "unknown"},
        {"target": "unknown"},
        {"experience_id": "x" * 101},
        {"review_id": "x" * 101},
    ],
)
def test_invalid_list_query_returns_422(
    client: TestClient,
    params: dict[str, object],
) -> None:
    response = client.get(
        "/api/memory-candidates",
        params=params,
    )

    assert response.status_code == 422
