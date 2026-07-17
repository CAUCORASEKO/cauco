class MemoryError(RuntimeError):
    """Base class for bounded memory access failures."""


class MemoryDirectoryError(MemoryError):
    """Raised when the configured brain directory is invalid or unreadable."""


class InvalidMemoryPathError(MemoryError):
    """Raised when a requested path is not a safe relative Markdown path."""


class MemoryPathTraversalError(InvalidMemoryPathError):
    """Raised when a path resolves outside the configured brain root."""


class MemoryFileNotFoundError(MemoryError):
    """Raised when a requested memory file does not exist."""


class MemoryFileTooLargeError(MemoryError):
    """Raised when a memory file exceeds the configured read limit."""


class MemoryFileUnreadableError(MemoryError):
    """Raised when a memory file cannot be read as UTF-8."""


class InvalidSearchQueryError(MemoryError):
    """Raised when a deterministic search query is invalid."""
