from cauco_tools.base import BaseTool, ToolMetadata


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool[object, object]] = {}

    def register(self, tool: BaseTool[object, object]) -> None:
        tool_id = tool.metadata.tool_id
        if tool_id in self._tools:
            raise ValueError(f"Tool '{tool_id}' is already registered.")
        self._tools[tool_id] = tool

    def get(self, tool_id: str) -> BaseTool[object, object]:
        try:
            return self._tools[tool_id]
        except KeyError as error:
            raise KeyError(f"Unknown tool '{tool_id}'.") from error

    def list_metadata(self) -> tuple[ToolMetadata, ...]:
        return tuple(tool.metadata for tool in self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
