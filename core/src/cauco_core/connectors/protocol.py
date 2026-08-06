"""Metadata-only connector protocol."""

from typing import Protocol

from .models import CapabilityDefinition, ConnectorIdentity, PermissionDefinition


class Connector(Protocol):
    @property
    def metadata(self) -> ConnectorIdentity: ...

    def capabilities(self) -> tuple[CapabilityDefinition, ...]: ...

    def permissions(self) -> tuple[PermissionDefinition, ...]: ...
