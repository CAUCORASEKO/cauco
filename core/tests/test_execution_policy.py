from pathlib import Path

import pytest

from cauco_core.execution.models import ExecutionForbiddenError
from cauco_core.execution.policy import WorkspacePolicy


def test_workspace_policy_rejects_traversal_sensitive_and_symlink_escape(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "safe.txt").write_text("safe", encoding="utf-8")
    (workspace / ".env").write_text("secret", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (workspace / "escape.txt").symlink_to(outside)
    policy = WorkspacePolicy(workspace)

    assert policy.validate_relative("safe.txt", expect="file") == "safe.txt"
    for path in ("../outside.txt", "/etc/passwd", ".env", ".ssh/id_rsa", "escape.txt"):
        with pytest.raises(ExecutionForbiddenError):
            policy.validate_relative(path, expect="file")
