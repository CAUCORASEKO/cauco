from pathlib import Path

import pytest

from cauco_tools import GitStatusTool, ListBrainFilesTool, ReadProjectStatusTool, ToolRegistry


def test_registry_and_permission_metadata() -> None:
    tools = (ListBrainFilesTool(), ReadProjectStatusTool(), GitStatusTool())
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    assert len(registry) == 3
    assert all(metadata.read_only for metadata in registry.list_metadata())


def test_registry_prevents_duplicates() -> None:
    registry = ToolRegistry()
    tool = GitStatusTool()
    registry.register(tool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_list_brain_files_is_bounded(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "memory.md").write_text("# Memory", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    (brain / "outside.md").symlink_to(outside)
    assert ListBrainFilesTool().execute(brain) == ["memory.md"]


def test_placeholders_do_not_execute_external_commands() -> None:
    assert GitStatusTool().execute() == {"status": "not configured"}
    assert ReadProjectStatusTool().execute("alpha") == {
        "project": "alpha",
        "status": "not configured",
    }
