from pathlib import Path

from cauco_core.schemas import MemoryFile


class MemoryDirectoryError(RuntimeError):
    """Raised when the configured memory directory cannot be inspected safely."""


class MemoryService:
    def __init__(self, brain_dir: Path) -> None:
        self.brain_dir = brain_dir.resolve()

    def list_markdown_files(self) -> list[MemoryFile]:
        if not self.brain_dir.exists():
            return []
        if not self.brain_dir.is_dir():
            raise MemoryDirectoryError("The configured brain path is not a directory.")

        files: list[MemoryFile] = []
        try:
            candidates = self.brain_dir.rglob("*")
            for candidate in candidates:
                if not candidate.is_file() or candidate.suffix.lower() != ".md":
                    continue
                resolved = candidate.resolve()
                try:
                    relative = resolved.relative_to(self.brain_dir)
                except ValueError:
                    # A symlink may point outside the configured directory; never expose it.
                    continue
                files.append(
                    MemoryFile(
                        path=relative.as_posix(),
                        name=resolved.name,
                        size=resolved.stat().st_size,
                    )
                )
        except OSError as error:
            message = "The configured brain directory could not be read."
            raise MemoryDirectoryError(message) from error
        return sorted(files, key=lambda item: item.path.casefold())
