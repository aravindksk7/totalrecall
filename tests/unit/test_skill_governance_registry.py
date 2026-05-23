"""Unit tests for SkillRegistry governance override behaviour."""

from pathlib import Path

import pytest

from totalrecall.skills.models import SkillStatus
from totalrecall.skills.registry import SkillRegistry, SkillNotFoundError


def _make_registry(skills_dir: Path) -> SkillRegistry:
    r = SkillRegistry(skills_dir)
    r.load()
    return r


@pytest.fixture()
def registry(tmp_path: Path) -> SkillRegistry:
    skill_json = {
        "skill_id": "playwright_ts",
        "version": "1.0.0",
        "language": "typescript",
        "framework": "playwright",
        "pattern": "pom",
        "supported_locator_strategies": ["page_file"],
        "output_files": [
            {
                "artifact_type": "page_object",
                "path_template": "pages/{name}.ts",
                "template_ref": "pom_page",
            }
        ],
        "generation_rules": [],
        "validators": [],
        "status": "draft",
    }
    (tmp_path / "playwright_ts.json").write_text(
        __import__("json").dumps(skill_json), encoding="utf-8"
    )
    return _make_registry(tmp_path)


def test_no_override_uses_file_status(registry: SkillRegistry) -> None:
    skill = registry.get("playwright_ts")
    assert registry._effective_status(skill) == SkillStatus.DRAFT


def test_governance_override_promotes_draft_to_active(registry: SkillRegistry) -> None:
    from totalrecall.generation.models import Language, Framework
    assert registry.select(Language.TYPESCRIPT, Framework.PLAYWRIGHT) is None

    registry.apply_governance_overrides({"playwright_ts": SkillStatus.ACTIVE})

    result = registry.select(Language.TYPESCRIPT, Framework.PLAYWRIGHT)
    assert result is not None
    assert result.skill_id == "playwright_ts"


def test_governance_override_deprecates_active_skill(tmp_path: Path) -> None:
    import json
    skill_json = {
        "skill_id": "pytest_py",
        "version": "1.0.0",
        "language": "python",
        "framework": "pytest",
        "pattern": "pom",
        "supported_locator_strategies": ["page_file"],
        "output_files": [
            {
                "artifact_type": "page_object",
                "path_template": "pages/{name}.py",
                "template_ref": "pom_page",
            }
        ],
        "status": "active",
    }
    (tmp_path / "pytest_py.json").write_text(json.dumps(skill_json), encoding="utf-8")
    r = _make_registry(tmp_path)

    from totalrecall.generation.models import Language, Framework
    assert r.select(Language.PYTHON, Framework.PYTEST) is not None

    r.apply_governance_overrides({"pytest_py": SkillStatus.DEPRECATED})
    assert r.select(Language.PYTHON, Framework.PYTEST) is None


def test_all_active_respects_governance_overrides(registry: SkillRegistry) -> None:
    assert registry.all_active() == []
    registry.apply_governance_overrides({"playwright_ts": SkillStatus.ACTIVE})
    assert len(registry.all_active()) == 1


def test_governance_override_applies_to_effective_status(registry: SkillRegistry) -> None:
    registry.apply_governance_overrides({"playwright_ts": SkillStatus.ACTIVE})
    skill = registry.get("playwright_ts")
    assert registry._effective_status(skill) == SkillStatus.ACTIVE


def test_apply_governance_overrides_clears_previous(registry: SkillRegistry) -> None:
    registry.apply_governance_overrides({"playwright_ts": SkillStatus.ACTIVE})
    registry.apply_governance_overrides({})
    skill = registry.get("playwright_ts")
    assert registry._effective_status(skill) == SkillStatus.DRAFT


def test_unknown_skill_in_override_is_ignored(registry: SkillRegistry) -> None:
    registry.apply_governance_overrides({"unknown_skill": SkillStatus.ACTIVE})
    assert registry.all_active() == []
