import re
from pathlib import Path

from cauco_core.execution.models import ExecutionForbiddenError, ExecutionValidationError

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
    "authorized_keys",
    "secrets",
    "tokens",
    "private_key",
}
SENSITIVE_PARTS = {".git", ".ssh", ".aws", ".gnupg", "secrets", "tokens"}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".crt", ".cer", ".keystore"}


class WorkspacePolicy:
    def __init__(self, workspace_dir: Path) -> None:
        root = workspace_dir.expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Configured workspace must be a directory.")
        broad = {Path("/"), Path("/Users"), Path("/private"), Path("/etc"), Path("/var")}
        home = Path.home().resolve()
        if root in broad or root == home:
            raise ValueError("Configured workspace root is too broad.")
        self.root = root

    def validate_relative(
        self, relative_path: str, *, expect: str | None = None, allow_root: bool = False
    ) -> str:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ExecutionValidationError("A workspace-relative path is required.")
        raw = relative_path.strip()
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", raw):
            raise ExecutionForbiddenError("The requested path is outside the workspace.")
        if self.is_sensitive(path):
            raise ExecutionForbiddenError("Access to the requested path is forbidden.")
        try:
            resolved = (self.root / path).resolve(strict=True)
            normalized = resolved.relative_to(self.root).as_posix()
        except (OSError, ValueError) as error:
            raise ExecutionForbiddenError(
                "The requested path is unavailable or outside the workspace."
            ) from error
        if not allow_root and resolved == self.root:
            raise ExecutionValidationError("A non-root workspace path is required.")
        if expect == "file" and not resolved.is_file():
            raise ExecutionValidationError("The requested path is not a file.")
        if expect == "directory" and not resolved.is_dir():
            raise ExecutionValidationError("The requested path is not a directory.")
        return normalized or "."

    def validate_write_target(self, relative_path: str) -> str:
        """Validate containment for a target that may not exist yet."""
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ExecutionValidationError("A workspace-relative path is required.")
        raw = relative_path.strip()
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", raw):
            raise ExecutionForbiddenError("The requested path is outside the workspace.")
        if self.is_sensitive(path):
            raise ExecutionForbiddenError("Access to the requested path is forbidden.")
        current = self.root
        for part in path.parent.parts:
            current = current / part
            if current.is_symlink():
                raise ExecutionForbiddenError("Symbolic-link parent paths are forbidden.")
        try:
            parent = (self.root / path.parent).resolve(strict=True)
            parent.relative_to(self.root)
        except (OSError, ValueError) as error:
            raise ExecutionForbiddenError(
                "The requested path is unavailable or outside the workspace."
            ) from error
        if not parent.is_dir():
            raise ExecutionValidationError("The target parent must be an existing directory.")
        target = parent / path.name
        if target.is_symlink():
            raise ExecutionForbiddenError("Symbolic-link targets are forbidden.")
        if target.exists() and not target.is_file():
            raise ExecutionValidationError("Existing targets must be regular files.")
        return target.relative_to(self.root).as_posix()

    @staticmethod
    def is_sensitive(path: Path) -> bool:
        parts = {part.casefold() for part in path.parts}
        name = path.name.casefold()
        return (
            bool(parts & SENSITIVE_PARTS)
            or name in SENSITIVE_NAMES
            or path.suffix.casefold() in SENSITIVE_SUFFIXES
            or "token" in name
        )
