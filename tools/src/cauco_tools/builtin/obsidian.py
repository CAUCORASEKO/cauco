from cauco_tools.builtin.common import operation, permission
from cauco_tools.models import ToolCategory, ToolDefinition

OBSIDIAN_TOOL = ToolDefinition(
    id="obsidian",
    display_name="Obsidian",
    description="Obsidian integration capability contracts.",
    category=ToolCategory.OBSIDIAN,
    version="1.0.0",
    enabled=True,
    operations=(
        operation("open_note", "Open an allowlisted note."),
        operation("create_note", "Create a note.", confirmation=True),
    ),
    permissions=(
        permission("obsidian_read", "Inspect Obsidian note references."),
        permission("obsidian_write", "Create Obsidian notes."),
    ),
    requires_confirmation=True,
)
