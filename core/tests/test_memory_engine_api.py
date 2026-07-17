from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


def test_engine_summary_listing_filtering_detail_and_refresh(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Projects.md").write_text("# Projects\nAtlas", encoding="utf-8")
    (brain / "Tasks.md").write_text("# Tasks\n- [ ] Ship", encoding="utf-8")

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        status_response = client.get("/api/memory/engine")
        assert status_response.status_code == 200
        assert status_response.json()["summary"]["total"] == 2

        list_response = client.get("/api/memory/objects")
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 2
        assert "content" not in list_response.json()["objects"][0]

        filtered = client.get(
            "/api/memory/objects", params={"kind": "tasks", "layer": "working"}
        )
        assert filtered.status_code == 200
        assert filtered.json()["count"] == 1
        task = filtered.json()["objects"][0]
        assert task["relative_path"] == "Tasks.md"

        detail = client.get(f"/api/memory/objects/{task['id']}")
        assert detail.status_code == 200
        assert detail.json()["content"] == "# Tasks\n- [ ] Ship"
        assert detail.json()["path"] == "Tasks.md"

        assert client.get("/api/memory/objects/memory_missing").status_code == 404

        (brain / "Decisions.md").write_text("# Decisions", encoding="utf-8")
        assert client.get("/api/memory/objects").json()["count"] == 2
        refreshed = client.post("/api/memory/refresh")
        assert refreshed.status_code == 200
        assert refreshed.json()["summary"]["total"] == 3
        assert client.get("/api/memory/objects").json()["count"] == 3


def test_engine_api_rejects_invalid_filters(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        assert client.get("/api/memory/objects", params={"kind": "private"}).status_code == 422
        assert client.get("/api/memory/objects", params={"layer": "private"}).status_code == 422
