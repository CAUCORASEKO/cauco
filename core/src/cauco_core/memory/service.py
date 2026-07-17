import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from cauco_core.memory.exceptions import (
    InvalidMemoryPathError,
    MemoryDirectoryError,
    MemoryFileNotFoundError,
    MemoryFileTooLargeError,
    MemoryFileUnreadableError,
    MemoryPathTraversalError,
)
from cauco_core.memory.models import MemoryFileContent, MemoryFileMetadata


class MemoryService:
    def __init__(self, brain_dir: Path, max_file_size: int = 524_288) -> None:
        self.brain_dir = brain_dir.expanduser().resolve()
        self.max_file_size = max_file_size

    def list_markdown_files(self) -> list[MemoryFileMetadata]:
        if not self.brain_dir.exists():
            return []
        if not self.brain_dir.is_dir():
            raise MemoryDirectoryError("The configured brain path is not a directory.")

        files: list[MemoryFileMetadata] = []
        try:
            for directory, directories, names in os.walk(self.brain_dir, followlinks=False):
                directories[:] = sorted(
                    (
                        name
                        for name in directories
                        if not name.startswith(".") and not (Path(directory) / name).is_symlink()
                    ),
                    key=str.casefold,
                )
                for name in sorted(names, key=str.casefold):
                    if name.startswith(".") or Path(name).suffix.lower() != ".md":
                        continue
                    candidate = Path(directory) / name
                    if candidate.is_symlink():
                        continue
                    metadata = self._metadata(candidate)
                    if metadata is not None:
                        files.append(metadata)
        except OSError as error:
            message = "The configured brain directory could not be read."
            raise MemoryDirectoryError(message) from error
        return sorted(files, key=lambda item: (item.relative_path.casefold(), item.relative_path))

    def read_file(self, relative_path: str) -> MemoryFileContent:
        resolved = self._resolve_relative_path(relative_path)
        try:
            stat = resolved.stat()
        except FileNotFoundError as error:
            raise MemoryFileNotFoundError("Memory file not found.") from error
        except OSError as error:
            raise MemoryFileUnreadableError("Memory file could not be inspected.") from error
        if not resolved.is_file():
            raise MemoryFileNotFoundError("Memory file not found.")
        if stat.st_size > self.max_file_size:
            raise MemoryFileTooLargeError(
                f"Memory file exceeds the {self.max_file_size}-byte read limit."
            )
        content = self._read_utf8(resolved)
        safe_relative = resolved.relative_to(self.brain_dir).as_posix()
        return MemoryFileContent(
            relative_path=safe_relative,
            name=resolved.name,
            size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            title=self.extract_title(content, resolved.stem),
            content=content,
        )

    def resolve_approved_write_target(self, relative_path: str) -> Path:
        path = PurePosixPath(relative_path)
        candidate = self.brain_dir.joinpath(*path.parts)
        if candidate.is_symlink():
            raise MemoryPathTraversalError("Approved memory target cannot be a symbolic link.")
        resolved = self._resolve_relative_path(relative_path)
        if not resolved.is_file():
            raise MemoryFileNotFoundError("Approved memory target is not a regular file.")
        return resolved

    @staticmethod
    def extract_title(content: str, fallback: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    return title
        return fallback

    def _metadata(self, candidate: Path) -> MemoryFileMetadata | None:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.brain_dir)
            if not resolved.is_file():
                return None
            stat = resolved.stat()
        except (FileNotFoundError, OSError, ValueError):
            return None

        title = resolved.stem
        if stat.st_size <= self.max_file_size:
            try:
                title = self.extract_title(self._read_utf8(resolved), resolved.stem)
            except MemoryFileUnreadableError:
                return None
        return MemoryFileMetadata(
            relative_path=resolved.relative_to(self.brain_dir).as_posix(),
            name=resolved.name,
            size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            title=title,
        )

    def _resolve_relative_path(self, value: str) -> Path:
        if not value or "\\" in value:
            raise InvalidMemoryPathError("Memory path must be a relative POSIX Markdown path.")
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or path.suffix.lower() != ".md"
            or any(part in {"", ".", ".."} or part.startswith(".") for part in path.parts)
        ):
            raise InvalidMemoryPathError("Memory path must be a visible relative Markdown path.")
        candidate = self.brain_dir.joinpath(*path.parts)
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as error:
            raise MemoryFileNotFoundError("Memory file not found.") from error
        try:
            resolved.relative_to(self.brain_dir)
        except ValueError as error:
            message = "Memory path resolves outside the brain directory."
            raise MemoryPathTraversalError(message) from error
        return resolved

    @staticmethod
    def _read_utf8(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise MemoryFileUnreadableError("Memory file is not readable UTF-8 text.") from error
