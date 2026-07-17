from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.context.models import ContextIntent
from cauco_core.main import create_app


def test_context_analysis_api_is_inspectable_and_content_free(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Projects.md").write_text("# Projects\nCauco", encoding="utf-8")
    (brain / "Tasks.md").write_text("# Tasks\nShip it", encoding="utf-8")

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        response = client.post(
            "/api/context/analyze",
            json={"question": "What should I work on today?"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["question"] == "What should I work on today?"
    assert payload["intent"] == "planning"
    assert payload["layers"] == ["working", "long_term"]
    assert payload["kinds"] == ["tasks", "projects"]
    assert [item["relative_path"] for item in payload["memory_objects"]] == [
        "Projects.md",
        "Tasks.md",
    ]
    assert all("content" not in item for item in payload["memory_objects"])
    assert payload["reasoning"]
    assert isinstance(payload["generated_at"], str)


def test_context_intents_api_lists_supported_intents(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        response = client.get("/api/context/intents")
    assert response.status_code == 200
    assert response.json() == {"intents": [intent.value for intent in ContextIntent]}


def test_context_analysis_api_validates_question(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        assert client.post("/api/context/analyze", json={"question": " "}).status_code == 422
        assert client.post("/api/context/analyze", json={"question": "x" * 8001}).status_code == 422
