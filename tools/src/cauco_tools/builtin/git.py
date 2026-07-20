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
        operation(
            "status", "Inspect repository status metadata.", runtime_allowed=True
        ),
        operation("diff", "Inspect a repository diff."),
        operation(
            "add",
            "Stage an exact approved set of regular text files.",
            confirmation=True,
            runtime_allowed=True,
            mutation=True,
        ),
        operation(
            "add_all", "Stage all repository changes.", enabled=False, confirmation=True
        ),
        operation(
            "commit", "Create one local commit from an exact approved staged tree.",
            confirmation=True, runtime_allowed=True, mutation=True,
        ),
        operation(
            "push",
            "Publish one exact approved commit with a fast-forward-only push.",
            confirmation=True, runtime_allowed=True, mutation=True,
        ),
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
