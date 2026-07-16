from pathlib import Path

from fastapi.testclient import TestClient


def test_status_is_deterministic(client: TestClient, brain_dir: Path) -> None:
    (brain_dir / "memory.md").write_text("# Memory\n", encoding="utf-8")
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {
        "runtime": {"status": "online", "version": "0.1.0"},
        "memory": {"status": "ready", "files": 1},
        "agents": {"status": "idle", "registered": 1, "active": 0},
        "tools": {"status": "ready", "registered": 3},
        "scheduler": {"status": "idle", "jobs": 0},
    }
