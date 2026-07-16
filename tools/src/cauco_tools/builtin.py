from pathlib import Path

from cauco_tools.base import BaseTool, RiskLevel, ToolMetadata


class ListBrainFilesTool(BaseTool[Path, list[str]]):
    metadata = ToolMetadata(
        tool_id="list_brain_files",
        name="List brain files",
        description="Lists Markdown file paths inside a configured brain directory.",
        read_only=True,
        risk=RiskLevel.LOW,
    )

    def execute(self, input_data: Path) -> list[str]:
        root = input_data.resolve()
        if not root.is_dir():
            return []
        result: list[str] = []
        for candidate in root.rglob("*"):
            if not candidate.is_file() or candidate.suffix.lower() != ".md":
                continue
            try:
                relative = candidate.resolve().relative_to(root)
            except ValueError:
                continue
            result.append(relative.as_posix())
        return sorted(result, key=str.casefold)


class ReadProjectStatusTool(BaseTool[str, dict[str, str]]):
    metadata = ToolMetadata(
        tool_id="read_project_status",
        name="Read project status",
        description="Reserved read-only project status interface.",
        read_only=True,
        risk=RiskLevel.LOW,
    )

    def execute(self, input_data: str) -> dict[str, str]:
        return {"project": input_data, "status": "not configured"}


class GitStatusTool(BaseTool[None, dict[str, str]]):
    metadata = ToolMetadata(
        tool_id="git_status",
        name="Git status",
        description="Reserved read-only Git status interface; does not invoke Git yet.",
        read_only=True,
        risk=RiskLevel.LOW,
    )

    def execute(self, input_data: None = None) -> dict[str, str]:
        return {"status": "not configured"}
