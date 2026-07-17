from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


@pytest.fixture
def bounded_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    brain = tmp_path / "brain"
    brain.mkdir()
    settings = Settings(brain_dir=brain, memory_max_file_size=1024)
    with TestClient(create_app(settings)) as client:
        yield client, brain


def test_file_endpoint_returns_safe_utf8_content(
    bounded_client: tuple[TestClient, Path],
) -> None:
    client, brain = bounded_client
    (brain / "projects.md").write_text("# Projects\nAtlas 👋", encoding="utf-8")
    response = client.get("/api/memory/file", params={"path": "projects.md"})
    assert response.status_code == 200
    assert response.json()["relative_path"] == "projects.md"
    assert response.json()["title"] == "Projects"
    assert response.json()["content"] == "# Projects\nAtlas 👋"


@pytest.mark.parametrize(
    ("path", "expected_status"),
    [("../outside.md", 400), ("missing.md", 404), ("note.txt", 400)],
)
def test_file_endpoint_rejects_unsafe_or_missing_paths(
    bounded_client: tuple[TestClient, Path], path: str, expected_status: int
) -> None:
    client, _ = bounded_client
    response = client.get("/api/memory/file", params={"path": path})
    assert response.status_code == expected_status


def test_file_endpoint_rejects_oversized_file(
    bounded_client: tuple[TestClient, Path],
) -> None:
    client, brain = bounded_client
    (brain / "large.md").write_text("x" * 1025, encoding="utf-8")
    response = client.get("/api/memory/file", params={"path": "large.md"})
    assert response.status_code == 413
    assert "1024-byte" in response.json()["detail"]


def test_search_endpoint_is_deterministic_and_limited(
    bounded_client: tuple[TestClient, Path],
) -> None:
    client, brain = bounded_client
    (brain / "b.md").write_text("project", encoding="utf-8")
    (brain / "a.md").write_text("project", encoding="utf-8")
    response = client.get("/api/memory/search", params={"q": "project", "limit": 1})
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["relative_path"] == "a.md"


@pytest.mark.parametrize(
    "params",
    [
        {"q": ""},
        {"q": "x" * 201},
        {"q": "project", "limit": 0},
        {"q": "project", "limit": 21},
    ],
)
def test_search_endpoint_validates_query_and_limit(
    bounded_client: tuple[TestClient, Path], params: dict[str, str | int]
) -> None:
    client, _ = bounded_client
    assert client.get("/api/memory/search", params=params).status_code == 422
