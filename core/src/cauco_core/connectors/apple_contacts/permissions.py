"""Contacts permission metadata."""

from cauco_core.connectors.models import PermissionDefinition, PermissionState

CONTACTS_PERMISSION_ID = "macos.contacts.read"


def permission_definition(state: PermissionState) -> PermissionDefinition:
    return PermissionDefinition(
        CONTACTS_PERMISSION_ID,
        "contacts",
        state,
        "macos_contacts",
        True,
        True,
        "apple_contacts.permission_explanation",
        ("Permission is never requested automatically.",),
    )
