from cauco_agents.skills.adapter import SkillAdapter
from cauco_agents.skills.email import (
    EmailInspectInboxInput,
    EmailInspectInboxSkill,
    EmailPrepareDraftInput,
    EmailPrepareDraftSkill,
)
from cauco_agents.skills.calendar import (
    CalendarInspectScheduleInput,
    CalendarInspectScheduleSkill,
    CalendarPrepareEventInput,
    CalendarPrepareEventSkill,
)
from cauco_agents.skills.git import GitInspectRepositoryInput, GitInspectRepositorySkill
from cauco_agents.skills.models import SkillCompilation, SkillDefinition
from cauco_agents.skills.registry import SkillRegistry


def create_default_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(CalendarInspectScheduleSkill())
    registry.register(EmailInspectInboxSkill())
    registry.register(EmailPrepareDraftSkill())
    registry.register(CalendarPrepareEventSkill())
    registry.register(GitInspectRepositorySkill())
    return registry


__all__ = [
    "GitInspectRepositoryInput",
    "GitInspectRepositorySkill",
    "CalendarInspectScheduleInput",
    "CalendarInspectScheduleSkill",
    "CalendarPrepareEventInput",
    "CalendarPrepareEventSkill",
    "EmailInspectInboxInput",
    "EmailInspectInboxSkill",
    "EmailPrepareDraftInput",
    "EmailPrepareDraftSkill",
    "SkillAdapter",
    "SkillCompilation",
    "SkillDefinition",
    "SkillRegistry",
    "create_default_skill_registry",
]
