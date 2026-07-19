import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

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
                changed.append({"status": line[:2], "path": "[sensitive path redacted]"})
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
