import json
from pathlib import Path

from totalrecall.generation.models import Framework, Language
from totalrecall.skills.models import SkillDefinition, SkillStatus


class SkillNotFoundError(Exception):
    pass


class SkillLoadError(Exception):
    pass


class SkillRegistry:
    """File-backed registry that loads skill definitions from a directory of JSON files.

    Governance overrides (from Postgres) can override the file-based status at runtime.
    Call apply_governance_overrides() after loading DB records on startup.
    """

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        self._skills: dict[str, SkillDefinition] = {}
        self._governance_overrides: dict[str, SkillStatus] = {}

    def load(self) -> None:
        """Load and validate all skill definitions from the skills directory."""
        if not self._skills_dir.exists():
            raise SkillLoadError(f"Skills directory does not exist: {self._skills_dir}")

        loaded: dict[str, SkillDefinition] = {}
        for path in sorted(self._skills_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                skill = SkillDefinition.model_validate(raw)
            except Exception as exc:
                raise SkillLoadError(f"Failed to load skill from {path.name}: {exc}") from exc

            if skill.skill_id in loaded:
                raise SkillLoadError(
                    f"Duplicate skill_id '{skill.skill_id}' found in {path.name}"
                )
            loaded[skill.skill_id] = skill

        self._skills = loaded

    def get(self, skill_id: str) -> SkillDefinition:
        """Return the skill definition for the given skill_id."""
        skill = self._skills.get(skill_id)
        if skill is None:
            raise SkillNotFoundError(f"Skill '{skill_id}' not found in registry")
        return skill

    def apply_governance_overrides(self, overrides: dict[str, SkillStatus]) -> None:
        """Set governance status overrides (skill_id → SkillStatus).

        Overrides take precedence over the status field in the JSON definition.
        Pass an empty dict to clear all overrides.
        """
        self._governance_overrides = dict(overrides)

    def _effective_status(self, skill: SkillDefinition) -> SkillStatus:
        return self._governance_overrides.get(skill.skill_id, skill.status)

    def select(self, language: Language, framework: Framework) -> SkillDefinition | None:
        """Return the active skill matching language and framework, or None."""
        for skill in self._skills.values():
            if (
                skill.language == language
                and skill.framework == framework
                and self._effective_status(skill) == SkillStatus.ACTIVE
            ):
                return skill
        return None

    def all_active(self) -> list[SkillDefinition]:
        """Return all skills with ACTIVE status (respecting governance overrides)."""
        return [s for s in self._skills.values() if self._effective_status(s) == SkillStatus.ACTIVE]

    def all(self) -> list[SkillDefinition]:
        """Return all loaded skills regardless of status."""
        return list(self._skills.values())

    @property
    def loaded_count(self) -> int:
        return len(self._skills)
