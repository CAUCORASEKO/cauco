from cauco_tools.builtin.common import operation, permission
from cauco_tools.models import ToolCategory, ToolDefinition

GIT_TOOL = ToolDefinition(
    id="git",
    display_name="Git",
    description="Version-control capability contracts.",
    category=ToolCategory.GIT,
    version="1.0.0",
    enabled=True,
    operations=(
        operation("status", "Inspect repository status metadata.", runtime_allowed=True),
        operation("diff", "Inspect a repository diff."),
        operation("commit", "Create a commit.", confirmation=True),
        operation("push", "Push commits to a remote.", safe=False, confirmation=True),
        operation(
            "reset_hard",
            "Discard repository changes.",
            safe=False,
            confirmation=True,
            enabled=False,
        ),
    ),
    permissions=(
        permission("repository_read", "Read repository metadata."),
        permission("repository_write", "Change repository state."),
    ),
    requires_confirmation=True,
)
