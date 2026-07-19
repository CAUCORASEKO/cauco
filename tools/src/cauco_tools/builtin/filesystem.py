from cauco_tools.builtin.common import operation, permission
from cauco_tools.models import ToolCategory, ToolDefinition

FILESYSTEM_TOOL = ToolDefinition(
    id="filesystem",
    display_name="Filesystem",
    description="Bounded filesystem capability contracts.",
    category=ToolCategory.FILESYSTEM,
    version="1.0.0",
    enabled=True,
    operations=(
        operation("read_file", "Read an allowlisted file.", runtime_allowed=True),
        operation(
            "list_directory",
            "List an allowlisted directory.",
            runtime_allowed=True,
        ),
        operation("write_file", "Write an allowlisted file.", confirmation=True),
        operation(
            "delete_file",
            "Delete an allowlisted file.",
            safe=False,
            confirmation=True,
            enabled=False,
        ),
    ),
    permissions=(
        permission("filesystem_read", "Read allowlisted files."),
        permission("filesystem_write", "Modify allowlisted files."),
    ),
    requires_confirmation=True,
)
