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
        operation(
            "list_accounts",
            "List bounded Apple Mail account metadata.",
            runtime_allowed=True,
        ),
        operation(
            "list_mailboxes",
            "List bounded mailbox metadata for an explicit account reference.",
            runtime_allowed=True,
        ),
        operation(
            "list_messages",
            "List bounded message metadata for an explicit mailbox reference.",
            runtime_allowed=True,
        ),
        operation(
            "draft",
            "Prepare an email draft.",
            confirmation=True,
            runtime_allowed=True,
            mutation=True,
        ),
        operation("send", "Send an email.", confirmation=True),
    ),
    permissions=(
        permission("email_read", "Read bounded email metadata."),
        permission("email_draft", "Prepare email content."),
        permission("email_send", "Send email."),
    ),
    requires_confirmation=True,
)
