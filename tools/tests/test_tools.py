from dataclasses import FrozenInstanceError, replace

import pytest

from cauco_tools import (
    ToolCategory,
    ToolDefinition,
    ToolOperation,
    ToolPermission,
    ToolRegistry,
    create_default_registry,
)


def definition(tool_id: str = "example") -> ToolDefinition:
    return ToolDefinition(
        id=tool_id,
        display_name="Example",
        description="Metadata-only example tool.",
        category=ToolCategory.FILESYSTEM,
        version="1.0.0",
        enabled=True,
        operations=(ToolOperation("read", "Read metadata.", True, False),),
        permissions=(ToolPermission("example_read", "Read example metadata."),),
        requires_confirmation=False,
    )


def test_models_are_immutable_and_execution_is_disabled() -> None:
    tool = definition()
    with pytest.raises(FrozenInstanceError):
        tool.enabled = False  # type: ignore[misc]
    with pytest.raises(ValueError, match="execution"):
        replace(tool, execution_enabled=True)
    with pytest.raises(ValueError, match="execution"):
        replace(tool.operations[0], execution_enabled=True)
    assert not hasattr(tool, "execute")


def test_registry_is_duplicate_safe_sorted_and_thread_safe_contract() -> None:
    registry = ToolRegistry()
    registry.register(definition("zeta"))
    registry.register(definition("alpha"))
    assert [tool.id for tool in registry.list()] == ["alpha", "zeta"]
    assert registry.exists("alpha")
    assert registry.get("alpha").id == "alpha"
    assert registry.categories() == (ToolCategory.FILESYSTEM,)
    assert registry.operations("alpha")[0].id == "read"
    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition("alpha"))
    with pytest.raises(KeyError, match="Unknown tool"):
        registry.get("missing")


def test_default_registry_contracts_and_validation() -> None:
    registry = create_default_registry()
    assert [tool.id for tool in registry.list()] == [
        "calendar",
        "email",
        "filesystem",
        "git",
        "memory",
        "obsidian",
        "ollama",
    ]
    assert all(not tool.execution_enabled for tool in registry.list())
    assert all(
        not operation.execution_enabled
        for tool in registry.list()
        for operation in tool.operations
    )
    status = registry.validate("git", "status")
    commit = registry.validate("git", "commit")
    dangerous = registry.validate("git", "reset_hard")
    missing = registry.validate("missing", "run")
    assert status.valid and status.safe and not status.confirmation_required
    assert commit.valid and commit.confirmation_required
    assert (
        not dangerous.valid
        and dangerous.operation_exists
        and not dangerous.operation_enabled
    )
    assert not missing.valid and not missing.tool_exists
    assert not status.execution_enabled
    runtime_allowed = {
        (tool.id, operation.id)
        for tool in registry.list()
        for operation in tool.operations
        if operation.runtime_execution_allowed
    }
    assert runtime_allowed == {
        ("git", "status"),
        ("filesystem", "list_directory"),
        ("filesystem", "read_file"),
        ("filesystem", "write_text_file"),
        ("memory", "create_proposal"),
        ("memory", "confirm_proposal"),
    }
    assert not registry.validate("git", "commit").runtime_execution_allowed
    assert not registry.validate("email", "send").runtime_execution_allowed
    assert not registry.validate("calendar", "create_event").runtime_execution_allowed
    memory_mutation = registry.validate("memory", "create_proposal")
    assert memory_mutation.runtime_execution_allowed
    assert memory_mutation.mutation and memory_mutation.preview_required
