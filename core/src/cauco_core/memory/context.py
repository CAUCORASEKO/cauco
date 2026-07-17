from cauco_core.memory.exceptions import (
    InvalidSearchQueryError,
    MemoryFileNotFoundError,
    MemoryFileTooLargeError,
    MemoryFileUnreadableError,
)
from cauco_core.memory.models import MemoryContext
from cauco_core.memory.search import MemorySearch
from cauco_core.memory.service import MemoryService

CONTEXT_OPEN = "<CAUCO_MEMORY_CONTEXT>"
CONTEXT_CLOSE = "</CAUCO_MEMORY_CONTEXT>"


class MemoryContextBuilder:
    def __init__(
        self,
        memory_service: MemoryService,
        memory_search: MemorySearch,
        *,
        max_files: int = 3,
        max_total_characters: int = 6000,
    ) -> None:
        self.memory_service = memory_service
        self.memory_search = memory_search
        self.max_files = max_files
        self.max_total_characters = max_total_characters

    def build(self, query: str) -> MemoryContext:
        try:
            results = self.memory_search.search(query, limit=self.max_files)
        except InvalidSearchQueryError:
            return MemoryContext(text="", sources=[])
        if not results:
            return MemoryContext(text="", sources=[])

        prefix = f"{CONTEXT_OPEN}\n"
        suffix = f"\n{CONTEXT_CLOSE}"
        remaining = self.max_total_characters - len(prefix) - len(suffix)
        blocks: list[str] = []
        sources: list[str] = []
        for result in results:
            try:
                memory_file = self.memory_service.read_file(result.relative_path)
            except (
                MemoryFileNotFoundError,
                MemoryFileTooLargeError,
                MemoryFileUnreadableError,
            ):
                continue
            safe_label = self._safe_source_label(memory_file.relative_path)
            label = f"[Memory source: {safe_label}]\n"
            separator_cost = 2 if blocks else 0
            available = remaining - len(label) - separator_cost
            if available <= 0:
                break
            content = self._escape_delimiters(memory_file.content)
            if len(content) > available:
                if available <= 1:
                    break
                content = f"{content[: available - 1]}…"
            block = f"{label}{content}"
            blocks.append(block)
            sources.append(memory_file.relative_path)
            remaining -= len(block) + separator_cost
            if remaining <= 0:
                break
        if not blocks:
            return MemoryContext(text="", sources=[])
        joined_blocks = "\n\n".join(blocks)
        return MemoryContext(text=f"{prefix}{joined_blocks}{suffix}", sources=sources)

    @staticmethod
    def _escape_delimiters(content: str) -> str:
        return content.replace(CONTEXT_OPEN, "[memory delimiter removed]").replace(
            CONTEXT_CLOSE, "[memory delimiter removed]"
        )

    @staticmethod
    def _safe_source_label(relative_path: str) -> str:
        return relative_path.replace("\r", " ").replace("\n", " ").replace("]", "_")
