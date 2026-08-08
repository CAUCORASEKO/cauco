from cauco_core.connectors.models import PermissionDefinition, PermissionState

CALENDAR_PERMISSION_ID = "macos.calendar.read"

def permission_definition(state: PermissionState) -> PermissionDefinition:
    return PermissionDefinition(CALENDAR_PERMISSION_ID, "calendar", state, "macos_calendar", True, True,
        "apple_calendar.permission_explanation", ("Permission is never requested automatically.",))
