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
    push = registry.validate("git", "push")
    dangerous = registry.validate("git", "reset_hard")
    missing = registry.validate("missing", "run")
    assert status.valid and status.safe and not status.confirmation_required
    assert (
        commit.valid
        and commit.confirmation_required
        and commit.runtime_execution_allowed
    )
    assert push.valid and push.confirmation_required and push.runtime_execution_allowed
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
        ("calendar", "list_events"),
        ("calendar", "create_event"),
        ("email", "draft"),
        ("email", "list_accounts"),
        ("email", "list_mailboxes"),
        ("email", "list_messages"),
        ("filesystem", "list_directory"),
        ("filesystem", "read_file"),
        ("filesystem", "write_text_file"),
        ("git", "status"),
        ("git", "add"),
        ("git", "commit"),
        ("git", "push"),
        ("memory", "create_proposal"),
        ("memory", "confirm_proposal"),
    }
    assert registry.validate("git", "commit").runtime_execution_allowed
    assert registry.validate("git", "push").runtime_execution_allowed
    email_list = registry.validate("email", "list_messages")
    assert email_list.runtime_execution_allowed
    assert not email_list.mutation
    assert not email_list.preview_required
    for operation_id in ("list_accounts", "list_mailboxes"):
        email_discovery = registry.validate("email", operation_id)
        assert email_discovery.runtime_execution_allowed
        assert not email_discovery.mutation
        assert not email_discovery.preview_required

    email_draft = registry.validate("email", "draft")
    assert email_draft.runtime_execution_allowed
    assert email_draft.mutation
    assert email_draft.preview_required
    assert email_draft.confirmation_required
    assert not registry.validate("email", "send").runtime_execution_allowed

    calendar_mutation = registry.validate("calendar", "create_event")
    assert calendar_mutation.runtime_execution_allowed
    assert calendar_mutation.preview_required
    memory_mutation = registry.validate("memory", "create_proposal")
    assert memory_mutation.runtime_execution_allowed
    assert memory_mutation.mutation and memory_mutation.preview_required
