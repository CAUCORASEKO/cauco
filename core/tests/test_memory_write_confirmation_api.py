from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


def api_brain(tmp_path: Path) -> Path:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Tasks.md").write_text(
        "# Tasks\n\n## Today\n\n## This Week\n\n## Backlog\n",
        encoding="utf-8",
    )
    return brain


def create_task(client: TestClient, instruction: str = "Tomorrow I need to finish the plugin"):
    response = client.post("/api/memory/write-proposals", json={"instruction": instruction})
    assert response.status_code == 200
    return response.json()


def test_created_proposal_is_stored_pending_and_can_be_confirmed(tmp_path: Path) -> None:
    brain = api_brain(tmp_path)
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        proposal = create_task(client)
        detail = client.get(f"/api/memory/write-proposals/{proposal['proposal_id']}")
        confirmation = client.post(
            f"/api/memory/write-proposals/{proposal['proposal_id']}/confirm",
            json={"confirm": True},
        )
        applied_detail = client.get(
            f"/api/memory/write-proposals/{proposal['proposal_id']}"
        )

    assert detail.status_code == 200
    assert detail.json()["state"] == "pending"
    assert detail.json()["proposal"] == proposal
    assert confirmation.status_code == 200
    assert confirmation.json()["state"] == "applied"
    assert confirmation.json()["memory_refreshed"] is True
    assert applied_detail.json()["state"] == "applied"
    assert isinstance(applied_detail.json()["applied_at"], str)
    assert proposal["markdown_preview"] in (brain / "Tasks.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("payload", [{"confirm": False}, {}, {"confirm": "true"}])
def test_confirmation_must_be_exact_boolean_true(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    brain = api_brain(tmp_path)
    original = (brain / "Tasks.md").read_bytes()
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        proposal = create_task(client)
        response = client.post(
            f"/api/memory/write-proposals/{proposal['proposal_id']}/confirm",
            json=payload,
        )
    assert response.status_code == 400
    assert (brain / "Tasks.md").read_bytes() == original


def test_unknown_expired_and_already_applied_status_codes(tmp_path: Path) -> None:
    brain = api_brain(tmp_path)
    app = create_app(Settings(brain_dir=brain))
    with TestClient(app) as client:
        unknown = client.post(
            "/api/memory/write-proposals/proposal_unknown/confirm",
            json={"confirm": True},
        )
        proposal = create_task(client)
        first = client.post(
            f"/api/memory/write-proposals/{proposal['proposal_id']}/confirm",
            json={"confirm": True},
        )
        second = client.post(
            f"/api/memory/write-proposals/{proposal['proposal_id']}/confirm",
            json={"confirm": True},
        )
        expiring = create_task(client, "Today I need to test expiration")
        store = app.state.memory_write_proposal_store
        expires_at = store.get(expiring["proposal_id"]).expires_at
        store.clock = lambda: expires_at + timedelta(seconds=1)
        expired = client.post(
            f"/api/memory/write-proposals/{expiring['proposal_id']}/confirm",
            json={"confirm": True},
        )
    assert unknown.status_code == 404
    assert first.status_code == 200
    assert second.status_code == 409
    assert expired.status_code == 410


def test_client_cannot_override_stored_proposal_data(tmp_path: Path) -> None:
    brain = api_brain(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        proposal = create_task(client)
        response = client.post(
            f"/api/memory/write-proposals/{proposal['proposal_id']}/confirm",
            json={
                "confirm": True,
                "target_file": "../outside.md",
                "markdown_preview": "forged",
            },
        )
    assert response.status_code == 422
    assert outside.read_text(encoding="utf-8") == "outside"
    assert proposal["markdown_preview"] not in (brain / "Tasks.md").read_text(encoding="utf-8")


def test_confirmation_response_exposes_no_absolute_paths(tmp_path: Path) -> None:
    brain = api_brain(tmp_path)
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        proposal = create_task(client)
        response = client.post(
            f"/api/memory/write-proposals/{proposal['proposal_id']}/confirm",
            json={"confirm": True},
        )
    assert response.status_code == 200
    assert str(brain) not in response.text
    assert response.json()["target_file"] == "Tasks.md"
