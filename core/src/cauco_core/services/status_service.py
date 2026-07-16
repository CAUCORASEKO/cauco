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
    def __init__(self, memory_service: MemoryService) -> None:
        self.memory_service = memory_service

    def get_status(self) -> SystemStatusResponse:
        file_count = len(self.memory_service.list_markdown_files())
        return SystemStatusResponse(
            runtime=RuntimeStatus(),
            memory=MemoryStatus(files=file_count),
            agents=AgentStatus(),
            tools=ToolStatus(),
            scheduler=SchedulerStatus(),
        )
