from cauco_tools.builtin.common import operation, permission
from cauco_tools.models import ToolCategory, ToolDefinition

MEMORY_TOOL = ToolDefinition(
    id="memory",
    display_name="Memory",
    description="Registered Cauco memory contracts.",
    category=ToolCategory.MEMORY,
    version="1.0.0",
    enabled=True,
    operations=(
        operation("read", "Read registered bounded memory."),
        operation("search", "Search registered memory."),
        operation(
            "create_proposal",
            "Create a controlled memory-write proposal.",
            confirmation=True,
            runtime_allowed=True,
            mutation=True,
        ),
        operation(
            "confirm_proposal",
            "Confirm a stored memory-write proposal.",
            confirmation=True,
            runtime_allowed=True,
            mutation=True,
        ),
    ),
    permissions=(
        permission("memory_read", "Read registered memory."),
        permission("memory_propose", "Propose a memory addition."),
        permission("memory_confirm", "Confirm a separately reviewed memory proposal."),
    ),
    requires_confirmation=True,
)
