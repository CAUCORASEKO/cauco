import re
from dataclasses import dataclass

from cauco_agents.models import AgentPlanStep


_SKILL_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_AGENT_ID = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    skill_id: str
    version: int
    description: str
    supported_agent_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _SKILL_ID.fullmatch(self.skill_id):
            raise ValueError("Skill IDs must use stable lowercase dotted identifiers.")
        if self.version != 1:
            raise ValueError("Only SkillDefinition version 1 is supported.")
        description = " ".join(self.description.split())
        if not description or len(description) > 500:
            raise ValueError("Skill descriptions must contain 1 to 500 characters.")
        if not self.supported_agent_ids or any(
            not _AGENT_ID.fullmatch(agent_id) for agent_id in self.supported_agent_ids
        ):
            raise ValueError("Skills require valid supported agent IDs.")
        if len(set(self.supported_agent_ids)) != len(self.supported_agent_ids):
            raise ValueError("Supported agent IDs must be unique.")
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "supported_agent_ids", tuple(self.supported_agent_ids))


@dataclass(frozen=True, slots=True)
class SkillCompilation:
    skill_id: str
    skill_version: int
    steps: tuple[AgentPlanStep, ...]
    warnings: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _SKILL_ID.fullmatch(self.skill_id):
            raise ValueError("Skill compilation requires a valid skill ID.")
        if self.skill_version != 1:
            raise ValueError("Only skill compilation version 1 is supported.")
        if tuple(step.order for step in self.steps) != tuple(range(1, len(self.steps) + 1)):
            raise ValueError("Compiled skill steps must use contiguous one-based ordering.")
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "open_questions", tuple(self.open_questions))
