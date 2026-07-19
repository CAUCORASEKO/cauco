from cauco_core.schemas import (
    AgentStatus,
    MemoryStatus,
    RuntimeStatus,
    SchedulerStatus,
    SystemStatusResponse,
    ToolStatus,
)
from cauco_core.services.memory_service import MemoryService


class StatusService:
    def __init__(
        self, memory_service: MemoryService, registered_agents: int = 1, registered_tools: int = 0
    ) -> None:
        self.memory_service = memory_service
        self.registered_agents = registered_agents
        self.registered_tools = registered_tools

    def get_status(self) -> SystemStatusResponse:
        file_count = len(self.memory_service.list_markdown_files())
        return SystemStatusResponse(
            runtime=RuntimeStatus(),
            memory=MemoryStatus(files=file_count),
            agents=AgentStatus(registered=self.registered_agents),
            tools=ToolStatus(registered=self.registered_tools),
            scheduler=SchedulerStatus(),
        )
