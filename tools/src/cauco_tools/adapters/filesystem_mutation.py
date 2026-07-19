import hashlib
import os
import re
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from time import monotonic

from cauco_tools.execution import (
    ToolExecutionError,
    ToolExecutionRequest,
    ToolExecutionResult,
)

ALLOWED_EXTENSIONS = frozenset({".md", ".txt", ".json", ".yaml", ".yml", ".toml"})
BLOCKED_NAMES = frozenset(
    {
        "agents.md",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        "poetry.lock",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    }
)
SENSITIVE_PARTS = frozenset({".git", ".ssh", ".aws", ".gnupg", "secrets", "tokens"})
SENSITIVE_SUFFIXES = frozenset(
    {".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".keystore"}
)


class FilesystemTextMutationAdapter:
    tool_id = "filesystem"
    operations = frozenset({"write_text_file"})

    def __init__(self, workspace: Path, *, max_content_chars: int = 100_000) -> None:
        self.workspace = workspace.resolve(strict=True)
        self.max_content_chars = max_content_chars
        self._lock = Lock()

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        if request.tool_id != self.tool_id or request.operation_id != "write_text_file":
            raise ToolExecutionError(
                "unsupported_operation", "The mutation is not supported."
            )
        relative = request.arguments.get("relative_path")
        content = request.arguments.get("content")
        policy = request.arguments.get("overwrite_policy")
        expected = request.arguments.get("expected_before_digest")
        if not isinstance(relative, str) or not isinstance(content, str):
            raise ToolExecutionError(
                "invalid_arguments", "Typed text-write arguments are required."
            )
        if policy not in {"create_only", "replace_existing"}:
            raise ToolExecutionError(
                "invalid_arguments", "The overwrite policy is invalid."
            )
        if expected is not None and not isinstance(expected, str):
            raise ToolExecutionError(
                "invalid_arguments", "The before-state digest is invalid."
            )
        if len(content) > self.max_content_chars or "\x00" in content:
            raise ToolExecutionError(
                "invalid_content", "Text content exceeds the safe write limit."
            )
        target, normalized = self.resolve_target(relative)
        started_at = datetime.now(tz=UTC)
        started = monotonic()
        with self._lock:
            result = self._write(target, normalized, content, policy, expected)
        completed_at = datetime.now(tz=UTC)
        return ToolExecutionResult(
            tool_id=self.tool_id,
            operation_id="write_text_file",
            success=True,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, round((monotonic() - started) * 1000)),
            output=f"Workspace text file {'created' if result['created'] else 'replaced'} and verified.",
            structured_data=result,
            mutation_performed=True,
        )

    def resolve_target(self, raw: str) -> tuple[Path, str]:
        path = Path(raw)
        folded_parts = {part.casefold() for part in path.parts}
        name = path.name.casefold()
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", raw):
            raise ToolExecutionError(
                "forbidden_path", "The path is outside the workspace.", forbidden=True
            )
        if (
            not path.parts
            or folded_parts & SENSITIVE_PARTS
            or any(part.startswith(".") for part in path.parts)
            or name in BLOCKED_NAMES
            or name.startswith("docker-compose")
            or name.startswith(".env")
            or name.startswith(("id_rsa", "id_ed25519", "private_key", "credentials"))
            or "secret" in name
            or "token" in name
            or path.suffix.casefold() in SENSITIVE_SUFFIXES
            or path.suffix.casefold() not in ALLOWED_EXTENSIONS
            or name.endswith(("~", ".swp", ".swo", ".tmp"))
            or re.fullmatch(r"requirements[^/]*\.txt", name) is not None
        ):
            raise ToolExecutionError(
                "forbidden_path",
                "The target is not allowed for text mutation.",
                forbidden=True,
            )
        lexical_parent = self.workspace / path.parent
        current = self.workspace
        for part in path.parent.parts:
            current = current / part
            if current.is_symlink():
                raise ToolExecutionError(
                    "forbidden_path",
                    "Symlink parent directories are forbidden.",
                    forbidden=True,
                )
        try:
            parent = lexical_parent.resolve(strict=True)
        except OSError as error:
            raise ToolExecutionError(
                "invalid_path", "The target parent must be an existing directory."
            ) from error
        try:
            parent.relative_to(self.workspace)
        except ValueError as error:
            raise ToolExecutionError(
                "forbidden_path", "The path is outside the workspace.", forbidden=True
            ) from error
        if not parent.is_dir() or parent.is_symlink():
            raise ToolExecutionError(
                "invalid_path", "The target parent must be an existing directory."
            )
        target = parent / path.name
        if target.is_symlink():
            raise ToolExecutionError(
                "forbidden_path", "Symlink targets are forbidden.", forbidden=True
            )
        if target.exists() and not target.is_file():
            raise ToolExecutionError(
                "invalid_path", "Existing targets must be regular files."
            )
        return target, target.relative_to(self.workspace).as_posix()

    def _write(
        self,
        target: Path,
        relative: str,
        content: str,
        policy: str,
        expected: str | None,
    ) -> dict[str, object]:
        exists = target.exists()
        if policy == "create_only" and exists:
            raise ToolExecutionError(
                "target_exists", "The create-only target already exists."
            )
        if policy == "replace_existing" and not exists:
            raise ToolExecutionError(
                "target_missing", "The replacement target does not exist."
            )
        before_bytes = target.read_bytes() if exists else None
        before_digest = digest(before_bytes) if before_bytes is not None else None
        if before_digest != expected:
            raise ToolExecutionError(
                "stale_before_state", "The target changed after preview creation."
            )
        mode = stat.S_IMODE(target.stat().st_mode) if exists else 0o600
        data = content.encode("utf-8")
        after_digest = digest(data)
        backup_created = False
        backup: Path | None = None
        temporary = write_temp(target.parent, target.name, data, mode)
        try:
            if exists:
                backup_root = self.workspace / ".cauco-backups"
                if backup_root.is_symlink() or (
                    backup_root.exists() and not backup_root.is_dir()
                ):
                    raise ToolExecutionError(
                        "backup_failed", "The controlled backup location is unavailable."
                    )
                backup_root.mkdir(mode=0o700, exist_ok=True)
                if backup_root.is_symlink() or backup_root.resolve() != backup_root:
                    raise ToolExecutionError(
                        "backup_failed", "The controlled backup location is unavailable."
                    )
                backup_base = f"{hashlib.sha256(relative.encode()).hexdigest()[:16]}-{target.name}"
                for slot in range(3, 1, -1):
                    older = backup_root / f"{backup_base}.{slot - 1}.bak"
                    newer = backup_root / f"{backup_base}.{slot}.bak"
                    if older.exists():
                        os.replace(older, newer)
                backup = backup_root / f"{backup_base}.1.bak"
                backup_temp = write_temp(
                    backup_root, backup.name, before_bytes or b"", mode
                )
                try:
                    os.replace(backup_temp, backup)
                    fsync_directory(backup_root)
                    backup_created = True
                finally:
                    backup_temp.unlink(missing_ok=True)
                os.replace(temporary, target)
            else:
                try:
                    os.link(temporary, target)
                except FileExistsError as error:
                    raise ToolExecutionError(
                        "target_exists", "The create-only target already exists."
                    ) from error
            fsync_directory(target.parent)
        finally:
            temporary.unlink(missing_ok=True)
        if digest(target.read_bytes()) != after_digest:
            if exists and backup is not None and backup.exists():
                os.replace(backup, target)
                fsync_directory(target.parent)
            elif not exists:
                target.unlink(missing_ok=True)
            raise ToolExecutionError(
                "verification_failed", "Post-write verification failed."
            )
        return {
            "relative_path": relative,
            "created": not exists,
            "replaced": exists,
            "characters_written": len(content),
            "bytes_written": len(data),
            "before_digest": before_digest,
            "after_digest": after_digest,
            "backup_created": backup_created,
            "verification_passed": True,
            "mutation_performed": True,
            "execution_performed": True,
        }


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_temp(directory: Path, name: str, content: bytes, mode: int) -> Path:
    descriptor, raw = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=directory)
    path = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, mode)
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
