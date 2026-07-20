import os
import shutil
import subprocess
import hashlib
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from threading import Lock
from typing import Any

from cauco_tools.adapters.filesystem import bounded_text, is_sensitive_path
from cauco_tools.execution import (
    ToolExecutionError,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutionTimeoutError,
)


class GitStatusAdapter:
    tool_id = "git"
    operations = frozenset({"status"})

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve(strict=True)
        executable = shutil.which("git", path=os.defpath)
        if executable is None:
            raise ToolExecutionError("git_unavailable", "Git is not available.")
        self.executable = executable

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        if (
            request.tool_id != "git"
            or request.operation_id != "status"
            or request.arguments
        ):
            raise ToolExecutionError(
                "invalid_arguments", "git.status accepts no operation arguments."
            )
        if not (self.workspace / ".git").exists():
            raise ToolExecutionError(
                "not_git_repository",
                "The configured workspace is not a Git repository.",
            )
        started_at = datetime.now(tz=UTC)
        started = monotonic()
        try:
            completed = subprocess.run(
                [
                    self.executable,
                    "--no-optional-locks",
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "color.status=false",
                    "status",
                    "--short",
                    "--branch",
                ],
                cwd=self.workspace,
                env={
                    "PATH": os.defpath,
                    "LANG": "C",
                    "LC_ALL": "C",
                    "GIT_PAGER": "cat",
                    "PAGER": "cat",
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_SYSTEM": os.devnull,
                },
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=request.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ToolExecutionTimeoutError() from error
        raw = completed.stdout if completed.returncode == 0 else completed.stderr
        safe_lines: list[str] = []
        changed: list[dict[str, str]] = []
        branch = None
        for line in raw.splitlines():
            if line.startswith("## "):
                branch = line[3:]
                safe_lines.append(line)
                continue
            path_text = line[3:].strip() if len(line) > 3 else ""
            if path_text and git_path_sensitive(path_text):
                safe_lines.append(f"{line[:2]} [sensitive path redacted]")
                changed.append(
                    {"status": line[:2], "path": "[sensitive path redacted]"}
                )
                continue
            safe_lines.append(line)
            if path_text:
                changed.append({"status": line[:2], "path": path_text})
        output, truncated = bounded_text(
            "\n".join(safe_lines), request.max_output_chars
        )
        structured_limit = max(1, min(1000, request.max_output_chars // 20))
        if len(changed) > structured_limit:
            changed = changed[:structured_limit]
            truncated = True
        completed_at = datetime.now(tz=UTC)
        return ToolExecutionResult(
            tool_id="git",
            operation_id="status",
            success=completed.returncode == 0,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, round((monotonic() - started) * 1000)),
            output=output,
            structured_data={
                "branch": branch,
                "changed_entries": changed,
                "clean": not changed,
            },
            error_code=None if completed.returncode == 0 else "git_status_failed",
            error_message=None
            if completed.returncode == 0
            else "Git status could not be completed.",
            truncated=truncated,
        )


def git_path_sensitive(path_text: str) -> bool:
    candidates = path_text.strip('"').split(" -> ")
    return any(
        is_sensitive_path(Path(candidate.strip('"'))) for candidate in candidates
    )


class GitAddAdapter:
    """Stages only validated paths using one fixed git-add argument vector."""

    tool_id = "git"
    operations = frozenset({"add"})

    def __init__(
        self,
        workspace: Path,
        *,
        max_paths: int = 20,
        max_file_bytes: int = 1_000_000,
        max_aggregate_bytes: int = 5_000_000,
    ) -> None:
        self.workspace = workspace.resolve(strict=True)
        self.max_paths = max_paths
        self.max_file_bytes = max_file_bytes
        self.max_aggregate_bytes = max_aggregate_bytes
        self._lock = Lock()
        executable = shutil.which("git", path=os.defpath)
        if executable is None:
            raise ToolExecutionError("git_unavailable", "Git is not available.")
        self.executable = executable

    def inspect(self, paths: tuple[str, ...]) -> dict[str, Any]:
        """Capture a bounded inert preview state for exact approved paths."""
        self._validate_repository()
        self._validate_operation_state()
        normalized = self._validate_paths(paths)
        before_index = self.index_digest()
        staged_paths = self._staged_paths()
        states: list[dict[str, Any]] = []
        total = 0
        diffs: list[str] = []
        for relative in normalized:
            state = self._path_state(relative, staged_paths)
            total += int(state["size"])
            if total > self.max_aggregate_bytes:
                raise ToolExecutionError(
                    "oversized_target",
                    "Approved files exceed the aggregate staging limit.",
                )
            states.append(state)
            diffs.append(self._diff(relative, state))
        worktree_digest = digest_json(states)
        return {
            "repository_label": self.workspace.name,
            "repository_id": hashlib.sha256(
                self.workspace.as_posix().encode("utf-8")
            ).hexdigest(),
            "paths": normalized,
            "path_count": len(normalized),
            "before_index_digest": before_index,
            "before_staged_paths": tuple(sorted(staged_paths)),
            "before_staged_state_digest": self._staged_state_digest(),
            "before_worktree_state_digest": worktree_digest,
            "path_states": tuple(states),
            "diff_preview": bounded_text("\n".join(diffs), 20_000)[0],
        }

    def verify_preview(self, arguments: Any) -> None:
        paths = self._argument_paths(arguments)
        if self.index_digest() != arguments.get("expected_index_digest"):
            raise ToolExecutionError(
                "index_stale", "The Git index changed after preview creation."
            )
        current = self.inspect(paths)
        if current["before_worktree_state_digest"] != arguments.get(
            "expected_worktree_digest"
        ):
            raise ToolExecutionError(
                "worktree_stale", "An approved file changed after preview creation."
            )
        if current["before_staged_state_digest"] != arguments.get(
            "expected_staged_state_digest"
        ):
            raise ToolExecutionError(
                "index_stale",
                "The staged repository state changed after preview creation.",
            )

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        if request.tool_id != "git" or request.operation_id != "add":
            raise ToolExecutionError(
                "unsupported_operation", "The Git mutation is not supported."
            )
        paths = self._argument_paths(request.arguments)
        started_at = datetime.now(tz=UTC)
        started = monotonic()
        with self._lock:
            self.verify_preview(request.arguments)
            before_index = self.index_digest()
            before_staged = self._staged_paths()
            before_worktree = self._worktree_content_digest(paths)
            backup, index_existed = self._backup_index()
            recovery_attempted = False
            recovery_succeeded = False
            try:
                completed = self._run(
                    ["add", "--", *paths],
                    timeout=request.timeout_seconds,
                    optional_locks=True,
                )
                if completed.returncode != 0:
                    raise ToolExecutionError(
                        "git_add_failed", self._safe_git_error(completed.stderr)
                    )
                after_index = self.index_digest()
                after_staged = self._staged_paths()
                expected = before_staged | set(paths)
                if after_staged != expected:
                    raise ToolExecutionError(
                        "verification_failed",
                        "Post-staging verification found an unexpected staged path.",
                    )
                for relative in paths:
                    self._verify_staged_matches_worktree(relative)
                if self._worktree_content_digest(paths) != before_worktree:
                    raise ToolExecutionError(
                        "verification_failed",
                        "A worktree file changed during Git staging.",
                    )
                self._validate_repository()
            except Exception as error:
                recovery_attempted = True
                recovery_succeeded = self._restore_index(backup, index_existed)
                setattr(error, "recovery_attempted", True)
                setattr(error, "recovery_succeeded", recovery_succeeded)
                raise
            finally:
                backup.unlink(missing_ok=True)
            completed_at = datetime.now(tz=UTC)
            changed = before_index != after_index
            return ToolExecutionResult(
                tool_id="git",
                operation_id="add",
                success=True,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=max(0, round((monotonic() - started) * 1000)),
                output=f"Staged and verified {len(paths)} exact approved file(s).",
                structured_data={
                    "repository_label": self.workspace.name,
                    "requested_paths": paths,
                    "staged_paths": paths,
                    "already_staged_paths": tuple(sorted(before_staged)),
                    "path_count": len(paths),
                    "before_index_digest": before_index,
                    "after_index_digest": after_index,
                    "index_changed": changed,
                    "verification_passed": True,
                    "backup_created": True,
                    "fixed_git_add_invoked": True,
                    "recovery_attempted": recovery_attempted,
                    "recovery_succeeded": recovery_succeeded,
                },
                mutation_performed=changed,
            )

    def index_digest(self) -> str:
        index = self._git_path("index")
        return hashlib.sha256(index.read_bytes() if index.exists() else b"").hexdigest()

    def _argument_paths(self, arguments: Any) -> tuple[str, ...]:
        allowed = {
            "paths",
            "expected_index_digest",
            "expected_worktree_digest",
            "expected_staged_state_digest",
        }
        if set(arguments) != allowed:
            raise ToolExecutionError(
                "invalid_arguments",
                "git.add accepts only its typed preview-bound input.",
            )
        raw = arguments.get("paths")
        if not isinstance(raw, tuple) or not all(isinstance(item, str) for item in raw):
            raise ToolExecutionError(
                "invalid_arguments", "git.add requires immutable exact paths."
            )
        for name in allowed - {"paths"}:
            value = arguments.get(name)
            if not isinstance(value, str) or len(value) != 64:
                raise ToolExecutionError(
                    "invalid_arguments", "git.add preview state is invalid."
                )
        return self._validate_paths(raw)

    def _validate_paths(self, paths: tuple[str, ...]) -> tuple[str, ...]:
        from cauco_tools.git_mutation import GitAddInput

        try:
            normalized = GitAddInput(paths).paths
        except ValueError as error:
            raise ToolExecutionError("invalid_paths", str(error)) from error
        if len(normalized) > self.max_paths:
            raise ToolExecutionError(
                "too_many_paths", "Too many files were approved for staging."
            )
        return normalized

    def _path_state(self, relative: str, staged_paths: set[str]) -> dict[str, Any]:
        path = self.workspace / relative
        current = self.workspace
        for part in Path(relative).parts[:-1]:
            current /= part
            if current.is_symlink() or (current / ".git").exists():
                raise ToolExecutionError(
                    "forbidden_path",
                    "Nested repositories and symlink paths are forbidden.",
                    forbidden=True,
                )
        if is_sensitive_path(Path(relative)) or self._internal_path(relative):
            raise ToolExecutionError(
                "sensitive_path",
                "An approved staging path is sensitive.",
                forbidden=True,
            )
        if path.is_symlink():
            raise ToolExecutionError(
                "symlink_target",
                "Symbolic-link staging targets are forbidden.",
                forbidden=True,
            )
        if not path.exists():
            raise ToolExecutionError(
                "deleted_target", "Deleted-file staging is not supported in Phase 7B."
            )
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode):
            raise ToolExecutionError(
                "invalid_target", "Only regular files may be staged."
            )
        resolved = path.resolve(strict=True)
        try:
            resolved.relative_to(self.workspace)
        except ValueError as error:
            raise ToolExecutionError(
                "forbidden_path",
                "A staging path escapes the workspace.",
                forbidden=True,
            ) from error
        data = path.read_bytes()
        if len(data) > self.max_file_bytes:
            raise ToolExecutionError(
                "oversized_target", "An approved file exceeds the staging size limit."
            )
        if b"\x00" in data:
            raise ToolExecutionError(
                "binary_target", "Binary-file staging is not supported in Phase 7B."
            )
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ToolExecutionError(
                "binary_target", "Only UTF-8 text files may be staged."
            ) from error
        ignored = self._run(
            ["check-ignore", "-q", "--", relative], optional_locks=False
        )
        if ignored.returncode == 0:
            raise ToolExecutionError(
                "ignored_target", "Ignored files cannot be staged.", forbidden=True
            )
        attributes = self._run(
            ["check-attr", "-z", "filter", "working-tree-encoding", "--", relative],
            optional_locks=False,
        )
        values = [item for item in attributes.stdout.split("\x00") if item]
        if attributes.returncode != 0 or len(values) % 3:
            raise ToolExecutionError(
                "unsupported_attributes",
                "Git attributes could not be validated safely.",
            )
        if any(value not in {"unspecified", "unset"} for value in values[2::3]):
            raise ToolExecutionError(
                "unsupported_attributes",
                "Files with Git content filters or worktree encoding are not supported.",
            )
        tracked = (
            self._run(
                ["ls-files", "--error-unmatch", "--", relative], optional_locks=False
            ).returncode
            == 0
        )
        status = self._porcelain_status(relative)
        if relative in staged_paths or (status and status[0] not in {" ", "?"}):
            raise ToolExecutionError(
                "partial_staging",
                "Approved paths with existing staged changes are not supported.",
            )
        if tracked and (not status or status[1] == " "):
            raise ToolExecutionError(
                "no_changes", "An approved tracked file has no unstaged change."
            )
        if not tracked and not status.startswith("??"):
            raise ToolExecutionError(
                "unsupported_state", "The approved file has an unsupported Git state."
            )
        return {
            "path": relative,
            "kind": "modified" if tracked else "new",
            "status": status,
            "size": len(data),
            "content_digest": hashlib.sha256(data).hexdigest(),
        }

    def _porcelain_status(self, relative: str) -> str:
        completed = self._run(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", relative],
            optional_locks=False,
        )
        if completed.returncode != 0:
            raise ToolExecutionError(
                "git_status_failed", "Git status could not validate an approved path."
            )
        raw = completed.stdout
        if not raw:
            return ""
        records = [item for item in raw.split("\x00") if item]
        if len(records) != 1 or len(records[0]) < 3 or records[0][3:] != relative:
            raise ToolExecutionError(
                "unsupported_state", "The approved file has a complex Git state."
            )
        return records[0][:2]

    def _diff(self, relative: str, state: dict[str, Any]) -> str:
        if state["kind"] == "new":
            lines = (self.workspace / relative).read_text(encoding="utf-8").splitlines()
            body = "\n".join(f"+{line}" for line in lines)
            return f"--- /dev/null\n+++ b/{relative}\n{body}\n"
        completed = self._run(
            ["diff", "--no-ext-diff", "--no-color", "--", relative],
            optional_locks=False,
        )
        if completed.returncode not in {0, 1}:
            raise ToolExecutionError(
                "git_diff_failed", "A bounded staging diff could not be created."
            )
        return completed.stdout

    def _staged_paths(self) -> set[str]:
        completed = self._run(
            ["diff", "--cached", "--name-only", "-z"], optional_locks=False
        )
        if completed.returncode != 0:
            raise ToolExecutionError(
                "git_status_failed", "The staged path set could not be read."
            )
        return {item for item in completed.stdout.split("\x00") if item}

    def _staged_state_digest(self) -> str:
        completed = self._run(
            ["diff", "--cached", "--binary", "--no-ext-diff", "--no-color"],
            optional_locks=False,
        )
        if completed.returncode != 0:
            raise ToolExecutionError(
                "git_status_failed", "The staged state could not be read."
            )
        return hashlib.sha256(
            completed.stdout.encode("utf-8", errors="surrogateescape")
        ).hexdigest()

    def _verify_staged_matches_worktree(self, relative: str) -> None:
        staged = self._run(["show", f":{relative}"], optional_locks=False)
        if (
            staged.returncode != 0
            or staged.stdout.encode("utf-8", errors="surrogateescape")
            != (self.workspace / relative).read_bytes()
        ):
            raise ToolExecutionError(
                "verification_failed",
                "Staged content did not match an approved worktree file.",
            )

    def _worktree_content_digest(self, paths: tuple[str, ...]) -> str:
        values: list[dict[str, object]] = []
        for relative in paths:
            target = self.workspace / relative
            if target.is_symlink() or not target.is_file():
                raise ToolExecutionError(
                    "worktree_stale", "An approved file changed during Git staging."
                )
            values.append(
                {
                    "path": relative,
                    "mode": stat.S_IMODE(target.stat().st_mode),
                    "digest": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
        return digest_json(values)

    def _validate_repository(self) -> None:
        if (
            self.workspace in {Path("/"), Path.home().resolve()}
            or not self.workspace.is_dir()
        ):
            raise ToolExecutionError(
                "invalid_repository", "The configured Git workspace is invalid."
            )
        inside = self._run(["rev-parse", "--is-inside-work-tree"], optional_locks=False)
        bare = self._run(["rev-parse", "--is-bare-repository"], optional_locks=False)
        top = self._run(["rev-parse", "--show-toplevel"], optional_locks=False)
        if (
            inside.stdout.strip() != "true"
            or bare.stdout.strip() != "false"
            or top.returncode != 0
        ):
            raise ToolExecutionError(
                "not_git_repository",
                "The configured workspace is not a non-bare Git worktree.",
            )
        try:
            discovered = Path(top.stdout.strip()).resolve(strict=True)
        except OSError as error:
            raise ToolExecutionError(
                "not_git_repository", "The configured Git worktree is unavailable."
            ) from error
        if discovered != self.workspace:
            raise ToolExecutionError(
                "repository_mismatch",
                "Repository discovery does not match the configured workspace.",
            )

    def _validate_operation_state(self) -> None:
        if self._git_path("index.lock").exists():
            raise ToolExecutionError(
                "index_locked", "The Git index is locked by another operation."
            )
        if self._run(["ls-files", "-u", "-z"], optional_locks=False).stdout:
            raise ToolExecutionError(
                "unmerged_state", "Git staging is blocked while unmerged entries exist."
            )
        for marker in (
            "MERGE_HEAD",
            "REBASE_HEAD",
            "rebase-merge",
            "rebase-apply",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "BISECT_LOG",
        ):
            if self._git_path(marker).exists():
                raise ToolExecutionError(
                    "blocked_git_state",
                    "Git staging is blocked during an active repository operation.",
                )

    def _git_path(self, name: str) -> Path:
        completed = self._run(["rev-parse", "--git-path", name], optional_locks=False)
        if completed.returncode != 0:
            raise ToolExecutionError(
                "not_git_repository", "Git repository metadata is unavailable."
            )
        value = Path(completed.stdout.strip())
        return value if value.is_absolute() else self.workspace / value

    def _backup_index(self) -> tuple[Path, bool]:
        index = self._git_path("index")
        existed = index.exists()
        try:
            descriptor, raw = tempfile.mkstemp(prefix="cauco-git-index-", suffix=".bak")
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(index.read_bytes() if index.exists() else b"")
                handle.flush()
                os.fsync(handle.fileno())
            return Path(raw), existed
        except OSError as error:
            raise ToolExecutionError(
                "backup_failed", "The Git index backup could not be created."
            ) from error

    def _restore_index(self, backup: Path, existed: bool) -> bool:
        index = self._git_path("index")
        try:
            if existed:
                shutil.copyfile(backup, index)
                return (
                    hashlib.sha256(index.read_bytes()).digest()
                    == hashlib.sha256(backup.read_bytes()).digest()
                )
            else:
                index.unlink(missing_ok=True)
                return not index.exists()
        except OSError:
            return False

    def _run(
        self, arguments: list[str], *, timeout: float = 5.0, optional_locks: bool
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [
                    self.executable,
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.hooksPath=/dev/null",
                    *arguments,
                ],
                cwd=self.workspace,
                env={
                    "PATH": os.defpath,
                    "LANG": "C",
                    "LC_ALL": "C",
                    "GIT_PAGER": "cat",
                    "PAGER": "cat",
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_SYSTEM": os.devnull,
                    **({"GIT_OPTIONAL_LOCKS": "0"} if not optional_locks else {}),
                },
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="surrogateescape",
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ToolExecutionTimeoutError() from error

    @staticmethod
    def _internal_path(relative: str) -> bool:
        name = Path(relative).name.casefold()
        blocked = {
            "agents.md",
            "pyproject.toml",
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "uv.lock",
            "poetry.lock",
            "dockerfile",
        }
        return (
            relative.casefold().startswith(".cauco-backups/")
            or name.startswith((".env", "credentials", "private_key", "password"))
            or "secret" in name
            or "token" in name
            or name in blocked
            or name.startswith("docker-compose")
            or name.endswith(("~", ".swp", ".swo", ".tmp"))
            or name in {".ds_store", "thumbs.db"}
        )

    @staticmethod
    def _safe_git_error(stderr: str) -> str:
        folded = stderr.casefold()
        if "index.lock" in folded or "another git process" in folded:
            return "The Git index is locked by another operation."
        return "Git could not stage the approved paths."


def digest_json(value: Any) -> str:
    import json

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
