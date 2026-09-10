from cauco_agents import AgentRegistry, create_default_registry
from cauco_tools import (
    ToolAdapterRegistry,
    ToolCategory,
    ToolDefinition,
    ToolPermission,
    ToolRegistry,
)
from cauco_tools.builtin.common import operation

from cauco_core.capabilities import CapabilityState, CapabilitySummaryService
from cauco_core.capability_inquiry import is_capability_inquiry
from cauco_core.connectors import ConnectorRegistry


class FakeAdapter:
    def __init__(self, tool_id: str, operations: frozenset[str]) -> None:
        self.tool_id = tool_id
        self.operations = operations


def service(
    tool: ToolDefinition, adapters: ToolAdapterRegistry | None = None
) -> CapabilitySummaryService:
    tools = ToolRegistry()
    tools.register(tool)
    return CapabilitySummaryService(
        tools,
        adapters or ToolAdapterRegistry(),
        ConnectorRegistry(),
        AgentRegistry(),
        native_broker_configured=False,
    )


def tool(*, confirmation: bool = False, mixed: bool = False) -> ToolDefinition:
    return ToolDefinition(
        id="filesystem",
        display_name="Filesystem",
        description="Test capability.",
        category=ToolCategory.FILESYSTEM,
        version="1",
        enabled=True,
        operations=(
            operation(
                "write_text_file" if confirmation else "read_file",
                "Test operation.",
                confirmation=confirmation,
                runtime_allowed=True,
                mutation=confirmation,
            ),
        ) + (
            (
                operation(
                    "write_text_file",
                    "Write operation.",
                    confirmation=True,
                    runtime_allowed=True,
                    mutation=True,
                ),
            )
            if mixed
            else ()
        ),
        permissions=(ToolPermission("filesystem_read", "Read files."),),
        requires_confirmation=confirmation or mixed,
    )


def test_capability_inquiry_detects_exact_spanish_and_english_forms() -> None:
    for text in (
        "¿Qué puedes hacer?",
        "Qué sabes hacer",
        "¿Cuáles son tus capacidades?",
        "Dime qué puedes hacer",
        "What can you do?",
        "What are your capabilities?",
    ):
        assert is_capability_inquiry(text)


def test_capability_inquiry_rejects_operational_questions() -> None:
    for text in (
        "¿Qué puedes hacer con este archivo?",
        "¿Qué puedes hacer mañana?",
        "¿Puedes hacer un calendario?",
        "What can you do with Python?",
        "Can you send an email?",
    ):
        assert not is_capability_inquiry(text)


def test_tool_definition_without_adapter_is_unavailable() -> None:
    item = service(tool()).summarize()[0]
    assert item.state is CapabilityState.UNAVAILABLE


def test_tool_with_runtime_adapter_is_available() -> None:
    adapters = ToolAdapterRegistry()
    adapters.register(FakeAdapter("filesystem", frozenset({"read_file"})))
    item = service(tool(), adapters).summarize()[0]
    assert item.state is CapabilityState.AVAILABLE


def test_runtime_tool_that_requires_confirmation_is_labeled() -> None:
    adapters = ToolAdapterRegistry()
    adapters.register(FakeAdapter("filesystem", frozenset({"write_text_file"})))
    item = service(tool(confirmation=True), adapters).summarize()[0]
    assert item.state is CapabilityState.AVAILABLE_WITH_CONFIRMATION
    assert item.confirmation_required is True


def test_mixed_operations_remain_available_and_identify_confirmed_mutations() -> None:
    adapters = ToolAdapterRegistry()
    adapters.register(FakeAdapter("filesystem", frozenset({"read_file", "write_text_file"})))
    item = service(tool(mixed=True), adapters).summarize()[0]
    assert item.state is CapabilityState.AVAILABLE
    assert item.available_operations == ("read_file",)
    assert item.confirmation_operations == ("write_text_file",)
    assert item.confirmation_required is True


def test_memory_read_and_search_are_available_while_writes_require_confirmation() -> None:
    from cauco_tools.builtin.memory import MEMORY_TOOL

    adapters = ToolAdapterRegistry()
    adapters.register(
        FakeAdapter("memory", frozenset({"create_proposal", "confirm_proposal"}))
    )
    item = service(MEMORY_TOOL, adapters).summarize()[0]
    assert item.state is CapabilityState.AVAILABLE
    assert item.available_operations == ("read", "search")
    assert item.confirmation_operations == ("confirm_proposal", "create_proposal")


def test_unavailable_connector_is_not_reported_as_operational() -> None:
    from cauco_core.connectors.apple_contacts import AppleContactsConnector

    registry = ConnectorRegistry()
    registry.register(AppleContactsConnector())
    summary = CapabilitySummaryService(
        ToolRegistry(),
        ToolAdapterRegistry(),
        registry,
        create_default_registry(),
        native_broker_configured=False,
    ).summarize()
    contacts = next(item for item in summary if item.name == "Contactos Apple")
    assert contacts.state is CapabilityState.UNAVAILABLE


def test_calendar_tool_and_apple_connector_are_one_human_capability() -> None:
    from cauco_tools.builtin.calendar import CALENDAR_TOOL

    from cauco_core.connectors.apple_calendar import AppleCalendarConnector

    adapters = ToolAdapterRegistry()
    adapters.register(FakeAdapter("calendar", frozenset({"list_events", "create_event"})))
    connectors = ConnectorRegistry()
    connectors.register(AppleCalendarConnector())
    summary = CapabilitySummaryService(
        ToolRegistry(),
        adapters,
        connectors,
        create_default_registry(),
        native_broker_configured=False,
    )
    summary.tool_registry.register(CALENDAR_TOOL)

    items = summary.summarize()
    calendar = next(item for item in items if item.name == "Calendario")
    assert calendar.state is CapabilityState.PLANNING_ONLY
    assert "Calendario Apple" not in {item.name for item in items}
