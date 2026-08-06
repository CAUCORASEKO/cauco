"""Optional native gateway boundary; no subprocess or database fallback."""

from __future__ import annotations

import platform
from typing import Protocol

from cauco_core.connectors.models import PermissionState


class ContactsGateway(Protocol):
    def authorization_state(self) -> PermissionState: ...
    def request_permission(self) -> PermissionState: ...
    def search(self, query, keys: tuple[str, ...], limit: int): ...
    def get(self, reference: str, keys: tuple[str, ...]): ...


class UnavailableContactsGateway:
    def authorization_state(self) -> PermissionState:
        if platform.system() != "Darwin":
            return PermissionState.UNAVAILABLE
        return PermissionState.UNAVAILABLE

    def request_permission(self) -> PermissionState:
        return self.authorization_state()

    def search(self, query, keys, limit):
        return ()

    def get(self, reference, keys):
        return None
