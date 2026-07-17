from pydantic import BaseModel, ConfigDict, Field


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictResponse):
    status: str = "ok"
    service: str = "cauco-core"
    version: str = "0.1.0"


class RuntimeStatus(StrictResponse):
    status: str = "online"
    version: str = "0.1.0"


class MemoryStatus(StrictResponse):
    status: str = "ready"
    files: int = Field(ge=0)


class AgentStatus(StrictResponse):
    status: str = "idle"
    registered: int = Field(default=1, ge=0)
    active: int = Field(default=0, ge=0)


class ToolStatus(StrictResponse):
    status: str = "ready"
    registered: int = Field(default=3, ge=0)


class SchedulerStatus(StrictResponse):
    status: str = "idle"
    jobs: int = Field(default=0, ge=0)


class SystemStatusResponse(StrictResponse):
    runtime: RuntimeStatus
    memory: MemoryStatus
    agents: AgentStatus
    tools: ToolStatus
    scheduler: SchedulerStatus
