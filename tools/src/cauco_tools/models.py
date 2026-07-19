import re
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeAlias

ToolMetadataValue: TypeAlias = str | int | float | bool | None


class ToolCategory(StrEnum):
    CALENDAR = "calendar"
    EMAIL = "email"
    FILESYSTEM = "filesystem"
    GIT = "git"
    MEMORY = "memory"
    MODEL = "model"
    OBSIDIAN = "obsidian"


def validate_identifier(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", value):
        raise ValueError(f"{label} must use lowercase snake_case.")


@dataclass(frozen=True, slots=True)
class ToolPermission:
    name: str
    description: str

    def __post_init__(self) -> None:
        validate_identifier(self.name, "Permission name")
        if not self.description.strip():
            raise ValueError("Permission description cannot be empty.")


@dataclass(frozen=True, slots=True)
class ToolOperation:
    id: str
    description: str
    safe: bool
    confirmation_required: bool
    enabled: bool = True
    execution_enabled: bool = False
    runtime_execution_allowed: bool = False
    mutation: bool = False
    preview_required: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.id, "Operation ID")
        if not self.description.strip():
            raise ValueError("Operation description cannot be empty.")
        if self.execution_enabled:
            raise ValueError("Phase 6A tool operation execution must remain disabled.")
        if self.runtime_execution_allowed and (not self.enabled or not self.safe):
            raise ValueError("Runtime-enabled operations must be enabled and safe.")
        if self.mutation != self.preview_required:
            raise ValueError("Mutation operations must require a preview.")
        if self.mutation and not (
            self.runtime_execution_allowed and self.confirmation_required
        ):
            raise ValueError("Mutations require runtime policy and confirmation.")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    id: str
    display_name: str
    description: str
    category: ToolCategory
    version: str
    enabled: bool
    operations: tuple[ToolOperation, ...]
    permissions: tuple[ToolPermission, ...]
    requires_confirmation: bool
    execution_enabled: bool = False
    metadata: Mapping[str, ToolMetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_identifier(self.id, "Tool ID")
        if (
            not self.display_name.strip()
            or not self.description.strip()
            or not self.version.strip()
        ):
            raise ValueError("Tool name, description, and version cannot be empty.")
        operation_ids = tuple(operation.id for operation in self.operations)
        if not operation_ids or len(operation_ids) != len(set(operation_ids)):
            raise ValueError("Tool operations must be non-empty and unique.")
        permission_names = tuple(permission.name for permission in self.permissions)
        if len(permission_names) != len(set(permission_names)):
            raise ValueError("Tool permissions must be unique.")
        if self.execution_enabled or any(
            op.execution_enabled for op in self.operations
        ):
            raise ValueError("Phase 6A tool execution must remain disabled.")
        if self.requires_confirmation != any(
            operation.confirmation_required for operation in self.operations
        ):
            raise ValueError("Tool confirmation metadata must match its operations.")
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "permissions", tuple(self.permissions))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ToolValidationResult:
    tool_id: str
    operation_id: str
    valid: bool
    tool_exists: bool
    operation_exists: bool
    tool_enabled: bool
    operation_enabled: bool
    safe: bool | None
    confirmation_required: bool | None
    execution_enabled: bool
    runtime_execution_allowed: bool = False
    mutation: bool = False
    preview_required: bool = False
    reason: str | None = None
