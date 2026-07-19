from cauco_tools.builtin.common import operation, permission
from cauco_tools.models import ToolCategory, ToolDefinition

EMAIL_TOOL = ToolDefinition(
    id="email",
    display_name="Email",
    description="Email capability contracts.",
    category=ToolCategory.EMAIL,
    version="1.0.0",
    enabled=True,
    operations=(
        operation("draft", "Prepare an email draft.", confirmation=True),
        operation("send", "Send an email.", confirmation=True),
    ),
    permissions=(
        permission("email_draft", "Prepare email content."),
        permission("email_send", "Send email."),
    ),
    requires_confirmation=True,
)
