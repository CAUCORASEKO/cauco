from dataclasses import dataclass

from cauco_agents.base import Agent, AgentMetadata


@dataclass(frozen=True, slots=True)
class OperationsInput:
    runtime_state: str
    memory_file_count: int
    registered_agents: int
    registered_tools: int
    scheduler_job_count: int

    def __post_init__(self) -> None:
        counts = (
            self.memory_file_count,
            self.registered_agents,
            self.registered_tools,
            self.scheduler_job_count,
        )
        if any(count < 0 for count in counts):
            raise ValueError("Operation counts cannot be negative.")


class OperationsAgent(Agent[OperationsInput, str]):
    metadata = AgentMetadata(
        agent_id="operations",
        name="Operations Agent",
        description="Produces a deterministic summary of observable Cauco state.",
        uses_model=False,
    )

    def run(self, input_data: OperationsInput) -> str:
        return "\n".join(
            (
                f"Runtime: {input_data.runtime_state}",
                f"Memory files: {input_data.memory_file_count}",
                f"Registered agents: {input_data.registered_agents}",
                f"Registered tools: {input_data.registered_tools}",
                f"Scheduler jobs: {input_data.scheduler_job_count}",
            )
        )
