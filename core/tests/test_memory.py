from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.services.memory_service import MemoryService


def test_memory_lists_only_markdown(client: TestClient, brain_dir: Path) -> None:
    nested = brain_dir / "projects"
    nested.mkdir()
    note = nested / "alpha.md"
    note.write_text("# Alpha\n", encoding="utf-8")
    (brain_dir / "ignore.txt").write_text("ignore", encoding="utf-8")

    response = client.get("/api/memory/files")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    memory_file = payload["files"][0]
    modified_at = memory_file.pop("modified_at")
    assert isinstance(modified_at, str)
    assert memory_file == {
        "relative_path": "projects/alpha.md",
        "name": "alpha.md",
        "size": 8,
        "title": "Alpha",
    }


def test_memory_skips_symlinks_outside_brain(brain_dir: Path, tmp_path: Path) -> None:
    outside = tmp_path / "private.md"
    outside.write_text("private", encoding="utf-8")
    (brain_dir / "escape.md").symlink_to(outside)
    assert MemoryService(brain_dir).list_markdown_files() == []
