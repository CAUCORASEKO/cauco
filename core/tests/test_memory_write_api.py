from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


def test_memory_write_proposal_api_returns_review_only_preview(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    tasks = brain / "Tasks.md"
    tasks.write_text("# Tasks\n", encoding="utf-8")
    original = tasks.read_bytes()

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        response = client.post(
            "/api/memory/write-proposals",
            json={"instruction": "Remember that tomorrow I must finish the plugin."},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["operation"] == "add_task"
    assert payload["target_file"] == "Tasks.md"
    assert payload["target_section"] == "This Week"
    assert payload["markdown_preview"] == "- [ ] Finish the plugin tomorrow"
    assert payload["requires_confirmation"] is True
    assert isinstance(payload["proposal_id"], str)
    assert isinstance(payload["created_at"], str)
    assert tasks.read_bytes() == original


def test_memory_write_operations_api_returns_allowlist(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        response = client.get("/api/memory/write-operations")
    assert response.status_code == 200
    assert response.json() == {
        "operations": [
            {"operation": "add_task", "target_file": "Tasks.md"},
            {"operation": "add_decision", "target_file": "Decisions.md"},
            {
                "operation": "add_relationship_note",
                "target_file": "Relationships.md",
            },
            {"operation": "add_project_note", "target_file": "Projects.md"},
        ]
    }


def test_memory_write_proposal_api_rejects_invalid_requests(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        assert client.post(
            "/api/memory/write-proposals", json={"instruction": " "}
        ).status_code == 422
        assert client.post(
            "/api/memory/write-proposals",
            json={"instruction": "Delete memory", "operation": "delete"},
        ).status_code == 422
        assert client.post(
            "/api/memory/write-proposals",
            json={"instruction": "Add a task", "target_file": "Other.md"},
        ).status_code == 422
        assert client.post(
            "/api/memory/write-proposals",
            json={"instruction": "Write to ../outside.md"},
        ).status_code == 422
