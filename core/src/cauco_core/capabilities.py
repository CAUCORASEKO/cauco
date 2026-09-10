"""Read-only, user-facing aggregation of already registered capabilities."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from cauco_tools import ToolAdapterRegistry, ToolRegistry

from cauco_core.connectors.models import ConnectorAvailability, PermissionState


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    AVAILABLE_WITH_CONFIRMATION = "available_with_confirmation"
    PLANNING_ONLY = "planning_only"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class CapabilitySummaryItem:
    name: str
    state: CapabilityState
    confirmation_required: bool = False
    available_operations: tuple[str, ...] = ()
    confirmation_operations: tuple[str, ...] = ()
    planning_only_operations: tuple[str, ...] = ()
    unavailable_operations: tuple[str, ...] = ()


class CapabilitySummaryService:
    """Aggregates runtime facts; it never enables, routes, or executes anything."""

    _TOOL_NAMES: ClassVar[dict[str, str]] = {
        "calendar": "Calendario",
        "email": "Correo",
        "filesystem": "Archivos del workspace",
        "git": "Git",
        "memory": "Memoria local",
        "obsidian": "Notas de Obsidian",
    }
    _PLANNING_TOOL_IDS: ClassVar[frozenset[str]] = frozenset({"calendar", "email", "git"})

    def __init__(
        self,
        tool_registry: ToolRegistry,
        adapter_registry: ToolAdapterRegistry,
        connector_registry,
        agent_registry,
        *,
        native_broker_configured: bool,
        memory_runtime_available: bool = True,
    ) -> None:
        self.tool_registry = tool_registry
        self.adapter_registry = adapter_registry
        self.connector_registry = connector_registry
        self.agent_registry = agent_registry
        self.native_broker_configured = native_broker_configured
        self.memory_runtime_available = memory_runtime_available

    def summarize(self) -> tuple[CapabilitySummaryItem, ...]:
        items = [
            self._tool_item(tool)
            for tool in self.tool_registry.list()
            if tool.id in self._TOOL_NAMES and tool.id != "calendar"
        ]
        calendar = self._calendar_item()
        if calendar is not None:
            items.append(calendar)
        items.extend(self._connector_items())
        items.extend(self._planning_items())
        return tuple(sorted(items, key=lambda item: item.name.casefold()))

    def _tool_item(self, tool) -> CapabilitySummaryItem:
        executable = [
            operation
            for operation in tool.operations
            if operation.enabled
            and operation.runtime_execution_allowed
            and self.adapter_registry.exists(tool.id, operation.id)
        ]
        if tool.id == "email" and not self.native_broker_configured:
            executable = []
        if tool.id == "memory" and self.memory_runtime_available:
            executable.extend(
                operation
                for operation in tool.operations
                if operation.id in {"read", "search"} and operation.enabled
            )
        available_operations = tuple(
            sorted(item.id for item in executable if not item.confirmation_required)
        )
        confirmation_operations = tuple(
            sorted(item.id for item in executable if item.confirmation_required)
        )
        unavailable_operations = tuple(
            sorted(item.id for item in tool.operations if item not in executable)
        )
        if executable:
            requires_confirmation = not available_operations and bool(confirmation_operations)
            return CapabilitySummaryItem(
                self._TOOL_NAMES[tool.id],
                CapabilityState.AVAILABLE_WITH_CONFIRMATION
                if requires_confirmation
                else CapabilityState.AVAILABLE,
                confirmation_required=bool(confirmation_operations),
                available_operations=available_operations,
                confirmation_operations=confirmation_operations,
                unavailable_operations=unavailable_operations,
            )
        return CapabilitySummaryItem(
            self._TOOL_NAMES[tool.id],
            CapabilityState.PLANNING_ONLY
            if tool.id in self._PLANNING_TOOL_IDS and self._has_agent(tool.id)
            else CapabilityState.UNAVAILABLE,
            planning_only_operations=(
                tuple(item.id for item in tool.operations)
                if tool.id in self._PLANNING_TOOL_IDS and self._has_agent(tool.id)
                else ()
            ),
            unavailable_operations=(
                ()
                if tool.id in self._PLANNING_TOOL_IDS and self._has_agent(tool.id)
                else tuple(item.id for item in tool.operations)
            ),
        )

    def _connector_items(self) -> list[CapabilitySummaryItem]:
        items: list[CapabilitySummaryItem] = []
        for metadata in self.connector_registry.list():
            if metadata.provider_id == "apple_calendar":
                continue
            name = {
                "apple_calendar": "Calendario Apple",
                "apple_contacts": "Contactos Apple",
            }.get(
                metadata.provider_id, metadata.provider_id.replace("_", " ").title()
            )
            connector = self.connector_registry._get_connector(metadata.connector_id)
            permissions = {item.permission_id: item for item in connector.permissions()}
            definitions = connector.capabilities()
            available = self._connector_is_ready(metadata, permissions, definitions)
            confirmation = any(item.confirmation_required for item in definitions)
            available_operations = tuple(
                sorted(item.capability_id for item in definitions if not item.confirmation_required)
            )
            confirmation_operations = tuple(
                sorted(item.capability_id for item in definitions if item.confirmation_required)
            )
            state = (
                CapabilityState.AVAILABLE_WITH_CONFIRMATION
                if confirmation
                else CapabilityState.AVAILABLE
            )
            items.append(
                CapabilitySummaryItem(
                    name,
                    state if available else CapabilityState.UNAVAILABLE,
                    confirmation_required=confirmation and available,
                    available_operations=available_operations if available else (),
                    confirmation_operations=confirmation_operations if available else (),
                    unavailable_operations=(
                        ()
                        if available
                        else tuple(sorted(item.capability_id for item in definitions))
                    ),
                )
            )
        return items

    def _calendar_item(self) -> CapabilitySummaryItem | None:
        try:
            tool = self.tool_registry.get("calendar")
            metadata = self.connector_registry.get_metadata("apple_calendar.local")
            connector = self.connector_registry._get_connector(metadata.connector_id)
        except KeyError:
            return None
        definitions = connector.capabilities()
        permissions = {item.permission_id: item for item in connector.permissions()}
        connector_ready = self._connector_is_ready(metadata, permissions, definitions)
        executable = [
            operation
            for operation in tool.operations
            if connector_ready
            and operation.enabled
            and operation.runtime_execution_allowed
            and self.adapter_registry.exists(tool.id, operation.id)
        ]
        available_operations = tuple(
            sorted(item.id for item in executable if not item.confirmation_required)
        )
        confirmation_operations = tuple(
            sorted(item.id for item in executable if item.confirmation_required)
        )
        if executable:
            return CapabilitySummaryItem(
                "Calendario",
                CapabilityState.AVAILABLE_WITH_CONFIRMATION
                if not available_operations
                else CapabilityState.AVAILABLE,
                confirmation_required=bool(confirmation_operations),
                available_operations=available_operations,
                confirmation_operations=confirmation_operations,
                unavailable_operations=tuple(
                    sorted(item.id for item in tool.operations if item not in executable)
                ),
            )
        return CapabilitySummaryItem(
            "Calendario",
            (
                CapabilityState.PLANNING_ONLY
                if self._has_agent("calendar")
                else CapabilityState.UNAVAILABLE
            ),
            planning_only_operations=(
                tuple(item.id for item in tool.operations) if self._has_agent("calendar") else ()
            ),
            unavailable_operations=(
                () if self._has_agent("calendar") else tuple(item.id for item in tool.operations)
            ),
        )

    @staticmethod
    def _connector_is_ready(metadata, permissions, definitions) -> bool:
        permissions_ready = all(
            permissions.get(permission_id) is not None
            and permissions[permission_id].state is PermissionState.GRANTED
            for definition in definitions
            for permission_id in definition.required_permission_ids
        )
        return metadata.availability in (
            ConnectorAvailability.AVAILABLE,
            ConnectorAvailability.DEGRADED,
        ) and permissions_ready

    def _planning_items(self) -> list[CapabilitySummaryItem]:
        names = {item.agent_id for item in self.agent_registry.list_metadata()}
        items = []
        if "project" in names:
            items.append(
                CapabilitySummaryItem("Planificación de proyectos", CapabilityState.PLANNING_ONLY)
            )
        if "research" in names:
            items.append(
                CapabilitySummaryItem(
                    "Planificación de investigación", CapabilityState.PLANNING_ONLY
                )
            )
        return items

    def _has_agent(self, agent_id: str) -> bool:
        return agent_id in {item.agent_id for item in self.agent_registry.list_metadata()}

    def response(self, instruction: str) -> str:
        spanish = _is_spanish(instruction)
        items = self.summarize()
        available = [
            _display_name(item.name, spanish)
            for item in items
            if item.state is CapabilityState.AVAILABLE
        ]
        confirmed = [
            _display_name(item.name, spanish)
            for item in items
            if item.state is CapabilityState.AVAILABLE_WITH_CONFIRMATION
        ]
        mixed_confirmation = [
            _display_name(item.name, spanish)
            for item in items
            if item.state is CapabilityState.AVAILABLE and item.confirmation_operations
        ]
        planning = [
            _display_name(item.name, spanish)
            for item in items
            if item.state is CapabilityState.PLANNING_ONLY
        ]
        unavailable = [
            _display_name(item.name, spanish)
            for item in items
            if item.state is CapabilityState.UNAVAILABLE
        ]
        if spanish:
            sections = ["Puedo conversar y trabajar con memoria local."]
            sections.extend(_section("En esta instalación también tengo disponibles", available))
            sections.extend(_section("Estas acciones requieren confirmación", confirmed))
            sections.extend(_section("Algunas acciones requieren confirmación", mixed_confirmation))
            sections.extend(
                _section(
                    "Puedo preparar planes, pero no ejecutarlos desde esta conversación",
                    planning,
                )
            )
            sections.extend(_section("Todavía no tengo acceso operativo a", unavailable))
            return "\n\n".join(sections)
        sections = ["I can converse and work with local memory."]
        sections.extend(_section("Also available in this installation", available))
        sections.extend(_section("These actions require confirmation", confirmed))
        sections.extend(_section("Some actions require confirmation", mixed_confirmation))
        sections.extend(
            _section(
                "I can prepare plans, but cannot execute them from this conversation",
                planning,
            )
        )
        sections.extend(_section("I do not currently have operational access to", unavailable))
        return "\n\n".join(sections)


def _section(title: str, values: list[str]) -> list[str]:
    return [f"{title}:\n" + "\n".join(f"- {value}" for value in values)] if values else []


def _is_spanish(instruction: str) -> bool:
    value = instruction.casefold()
    return any(word in value for word in ("qué", "que ", "cuáles", "cuales", "puedes", "sabes"))


def _display_name(name: str, spanish: bool) -> str:
    if spanish:
        return name
    return {
        "Calendario": "Calendar",
        "Calendario Apple": "Apple Calendar",
        "Correo": "Email",
        "Archivos del workspace": "Workspace files",
        "Memoria local": "Local memory",
        "Notas de Obsidian": "Obsidian notes",
        "Contactos Apple": "Apple Contacts",
        "Planificación de proyectos": "Project planning",
        "Planificación de investigación": "Research planning",
    }.get(name, name)
