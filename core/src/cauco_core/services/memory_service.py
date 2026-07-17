"""Compatibility imports for the memory service's original module path."""

from cauco_core.memory.exceptions import MemoryDirectoryError
from cauco_core.memory.service import MemoryService

__all__ = ["MemoryDirectoryError", "MemoryService"]
