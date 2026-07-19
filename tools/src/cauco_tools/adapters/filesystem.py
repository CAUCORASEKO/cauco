from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from cauco_tools.execution import (
    ToolExecutionError,
    ToolExecutionRequest,
    ToolExecutionResult,
)

SENSITIVE_NAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "known_hosts",
}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".crt"}


def is_sensitive_path(path: Path) -> bool:
    lowered = {part.casefold() for part in path.parts}
    return (
        bool(lowered & {".git", ".ssh", ".aws", ".gnupg", "secrets"})
        or path.name.casefold() in SENSITIVE_NAMES
        or path.suffix.casefold() in SENSITIVE_SUFFIXES
        or "token" in path.name.casefold()
    )


class FilesystemAdapter:
    tool_id = "filesystem"
    operations = frozenset({"list_directory", "read_file"})

    def __init__(self, workspace: Path, *, max_file_bytes: int = 1_000_000) -> None:
        self.workspace = workspace.resolve(strict=True)
        self.max_file_bytes = max_file_bytes

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        if (
            request.tool_id != self.tool_id
            or request.operation_id not in self.operations
        ):
            raise ToolExecutionError(
                "unsupported_operation", "The operation is not supported."
            )
        started_at = datetime.now(tz=UTC)
        started = monotonic()
        if request.operation_id == "list_directory":
            output, data, truncated = self._list_directory(request)
        else:
            output, data, truncated = self._read_file(request)
        completed_at = datetime.now(tz=UTC)
        return ToolExecutionResult(
            tool_id=self.tool_id,
            operation_id=request.operation_id,
            success=True,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, round((monotonic() - started) * 1000)),
            output=output,
            structured_data=data,
            truncated=truncated,
        )

    def _path(self, raw: object, *, allow_root: bool) -> tuple[Path, str]:
        if not isinstance(raw, str) or not raw.strip():
            raise ToolExecutionError(
                "invalid_path", "A relative workspace path is required."
            )
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts:
            raise ToolExecutionError(
                "forbidden_path", "The path is outside the workspace.", forbidden=True
            )
        if is_sensitive_path(relative):
            raise ToolExecutionError(
                "sensitive_path",
                "Access to the requested path is forbidden.",
                forbidden=True,
            )
        try:
            resolved = (self.workspace / relative).resolve(strict=True)
            normalized = resolved.relative_to(self.workspace).as_posix()
        except (OSError, ValueError) as error:
            raise ToolExecutionError(
                "forbidden_path",
                "The path is unavailable or outside the workspace.",
                forbidden=True,
            ) from error
        if not allow_root and resolved == self.workspace:
            raise ToolExecutionError("invalid_path", "A file path is required.")
        return resolved, normalized or "."

    def _list_directory(
        self, request: ToolExecutionRequest
    ) -> tuple[str, dict[str, object], bool]:
        path, relative = self._path(
            request.arguments.get("relative_path", "."), allow_root=True
        )
        if not path.is_dir():
            raise ToolExecutionError(
                "not_directory", "The requested path is not a directory."
            )
        maximum = request.arguments.get("max_entries", 200)
        if (
            not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or not 1 <= maximum <= 1000
        ):
            raise ToolExecutionError(
                "invalid_arguments", "max_entries must be between 1 and 1000."
            )
        entries: list[dict[str, object]] = []
        for child in sorted(
            path.iterdir(), key=lambda item: (item.name.casefold(), item.name)
        ):
            child_relative = Path(child.relative_to(self.workspace).as_posix())
            if (
                child.name.startswith(".")
                or is_sensitive_path(child_relative)
                or child.is_symlink()
            ):
                continue
            kind = (
                "directory"
                if child.is_dir()
                else "file"
                if child.is_file()
                else "other"
            )
            entry: dict[str, object] = {"path": child_relative.as_posix(), "type": kind}
            if kind == "file":
                entry["size"] = min(child.stat().st_size, self.max_file_bytes + 1)
            entries.append(entry)
        truncated = len(entries) > maximum
        entries = entries[:maximum]
        lines = [f"{item['type']}\t{item['path']}" for item in entries]
        output, output_truncated = bounded_text(
            "\n".join(lines), request.max_output_chars
        )
        return (
            output,
            {"path": relative, "entries": entries},
            truncated or output_truncated,
        )

    def _read_file(
        self, request: ToolExecutionRequest
    ) -> tuple[str, dict[str, object], bool]:
        path, relative = self._path(
            request.arguments.get("relative_path"), allow_root=False
        )
        if not path.is_file() or path.is_symlink():
            raise ToolExecutionError(
                "not_file", "The requested path is not a regular file."
            )
        size = path.stat().st_size
        if size > self.max_file_bytes:
            raise ToolExecutionError(
                "file_too_large", "The requested file exceeds the read limit."
            )
        content = path.read_bytes()
        if b"\x00" in content:
            raise ToolExecutionError("binary_file", "Binary files cannot be read.")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ToolExecutionError(
                "binary_file", "The file is not valid UTF-8 text."
            ) from error
        maximum = request.arguments.get("max_chars", 20_000)
        if (
            not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or not 1 <= maximum <= 100_000
        ):
            raise ToolExecutionError(
                "invalid_arguments", "max_chars must be between 1 and 100000."
            )
        limit = min(maximum, request.max_output_chars)
        output, truncated = bounded_text(text, limit)
        return output, {"path": relative, "size": size}, truncated


def bounded_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit], True
