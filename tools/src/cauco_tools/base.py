from cauco_tools.models import ToolDefinition

# Phase 6A tools are immutable definitions only. This compatibility name has no
# execute method and cannot perform work.
BaseTool = ToolDefinition

__all__ = ["BaseTool"]
