from threading import RLock

from cauco_agents.skills.adapter import SkillAdapter
from cauco_agents.skills.models import SkillDefinition


class SkillRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SkillAdapter] = {}
        self._lock = RLock()

    def register(self, adapter: SkillAdapter) -> None:
        skill_id = adapter.definition.skill_id
        with self._lock:
            if skill_id in self._adapters:
                raise ValueError(f"Skill '{skill_id}' is already registered.")
            self._adapters[skill_id] = adapter

    def get(self, skill_id: str) -> SkillAdapter:
        with self._lock:
            try:
                return self._adapters[skill_id]
            except KeyError as error:
                raise KeyError(f"Unknown skill '{skill_id}'.") from error

    def exists(self, skill_id: str) -> bool:
        with self._lock:
            return skill_id in self._adapters

    def list(self) -> tuple[SkillAdapter, ...]:
        with self._lock:
            return tuple(self._adapters[key] for key in sorted(self._adapters))

    def list_definitions(self) -> tuple[SkillDefinition, ...]:
        return tuple(adapter.definition for adapter in self.list())

    def __len__(self) -> int:
        with self._lock:
            return len(self._adapters)
