from cauco_tools.builtin.calendar import CALENDAR_TOOL
from cauco_tools.builtin.email import EMAIL_TOOL
from cauco_tools.builtin.filesystem import FILESYSTEM_TOOL
from cauco_tools.builtin.git import GIT_TOOL
from cauco_tools.builtin.memory import MEMORY_TOOL
from cauco_tools.builtin.obsidian import OBSIDIAN_TOOL
from cauco_tools.builtin.ollama import OLLAMA_TOOL

BUILTIN_TOOLS = (
    CALENDAR_TOOL,
    EMAIL_TOOL,
    FILESYSTEM_TOOL,
    GIT_TOOL,
    MEMORY_TOOL,
    OBSIDIAN_TOOL,
    OLLAMA_TOOL,
)

__all__ = [
    "BUILTIN_TOOLS",
    "CALENDAR_TOOL",
    "EMAIL_TOOL",
    "FILESYSTEM_TOOL",
    "GIT_TOOL",
    "MEMORY_TOOL",
    "OBSIDIAN_TOOL",
    "OLLAMA_TOOL",
]
