import re

from cauco_core.memory.exceptions import (
    InvalidSearchQueryError,
    MemoryFileNotFoundError,
    MemoryFileTooLargeError,
    MemoryFileUnreadableError,
)
from cauco_core.memory.models import MemorySearchResult
from cauco_core.memory.service import MemoryService

TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", flags=re.UNICODE)
MAX_QUERY_LENGTH = 200
MAX_SEARCH_LIMIT = 20
EXCERPT_LENGTH = 240
STOP_TERMS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


class MemorySearch:
    def __init__(self, memory_service: MemoryService) -> None:
        self.memory_service = memory_service

    def search(self, query: str, limit: int = 5) -> list[MemorySearchResult]:
        normalized = query.strip()
        if not normalized:
            raise InvalidSearchQueryError("Memory search query cannot be empty.")
        if len(normalized) > MAX_QUERY_LENGTH:
            raise InvalidSearchQueryError(
                f"Memory search query cannot exceed {MAX_QUERY_LENGTH} characters."
            )
        if not 1 <= limit <= MAX_SEARCH_LIMIT:
            raise InvalidSearchQueryError(
                f"Memory search limit must be between 1 and {MAX_SEARCH_LIMIT}."
            )
        terms = list(
            dict.fromkeys(
                match.group(0).casefold()
                for match in TOKEN_PATTERN.finditer(normalized)
                if match.group(0).casefold() not in STOP_TERMS
            )
        )
        if not terms:
            raise InvalidSearchQueryError("Memory search query must contain searchable text.")

        results: list[MemorySearchResult] = []
        for metadata in self.memory_service.list_markdown_files():
            try:
                memory_file = self.memory_service.read_file(metadata.relative_path)
            except (
                MemoryFileNotFoundError,
                MemoryFileTooLargeError,
                MemoryFileUnreadableError,
            ):
                continue
            title_text = memory_file.title.casefold()
            headings = "\n".join(
                line.lstrip("#").strip()
                for line in memory_file.content.splitlines()
                if line.lstrip().startswith("#")
            ).casefold()
            body = "\n".join(
                line
                for line in memory_file.content.splitlines()
                if not line.lstrip().startswith("#")
            ).casefold()
            matched = [
                term for term in terms if term in title_text or term in headings or term in body
            ]
            if not matched:
                continue
            score = sum(
                title_text.count(term) * 10
                + headings.count(term) * 5
                + body.count(term)
                for term in matched
            )
            results.append(
                MemorySearchResult(
                    relative_path=metadata.relative_path,
                    title=memory_file.title,
                    score=score,
                    matched_terms=matched,
                    excerpt=self._excerpt(memory_file.content, matched),
                )
            )
        results.sort(
            key=lambda result: (
                -result.score,
                result.relative_path.casefold(),
                result.relative_path,
            )
        )
        return results[:limit]

    @staticmethod
    def _excerpt(content: str, terms: list[str]) -> str:
        folded = content.casefold()
        positions = [folded.find(term) for term in terms if folded.find(term) >= 0]
        center = min(positions, default=0)
        start = max(0, center - EXCERPT_LENGTH // 3)
        end = min(len(content), start + EXCERPT_LENGTH)
        excerpt = " ".join(content[start:end].split())
        if start > 0:
            excerpt = f"…{excerpt}"
        if end < len(content):
            excerpt = f"{excerpt}…"
        return excerpt
