from cauco_tools.models import ToolOperation, ToolPermission


def operation(
    operation_id: str,
    description: str,
    *,
    safe: bool = True,
    confirmation: bool = False,
    enabled: bool = True,
) -> ToolOperation:
    return ToolOperation(operation_id, description, safe, confirmation, enabled)


def permission(name: str, description: str) -> ToolPermission:
    return ToolPermission(name, description)
