from typing import Any, Protocol

from cauco_agents.skills.models import SkillCompilation, SkillDefinition


class SkillAdapter(Protocol):
    @property
    def definition(self) -> SkillDefinition: ...

    def compile(self, input_data: Any) -> SkillCompilation: ...
