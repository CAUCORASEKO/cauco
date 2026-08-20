from cauco_tools.builtin.common import operation, permission
from cauco_tools.models import ToolCategory, ToolDefinition

CALENDAR_TOOL = ToolDefinition(
    id="calendar",
    display_name="Calendar",
    description="Calendar capability contracts.",
    category=ToolCategory.CALENDAR,
    version="1.0.0",
    enabled=True,
    operations=(
        operation(
            "list_events",
            "List calendar event metadata.",
            runtime_allowed=True,
        ),
        operation(
            "create_event",
            "Create a calendar event.",
            confirmation=True,
            runtime_allowed=True,
            mutation=True,
        ),
        operation(
            "delete_event",
            "Delete a calendar event.",
            safe=False,
            confirmation=True,
            enabled=False,
        ),
    ),
    permissions=(
        permission("calendar_read", "Read calendar event metadata."),
        permission("calendar_write", "Change calendar events."),
    ),
    requires_confirmation=True,
)
