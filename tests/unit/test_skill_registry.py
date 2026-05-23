import json
from pathlib import Path

import pytest

from totalrecall.generation.models import Framework, Language
from totalrecall.skills.models import SkillStatus
from totalrecall.skills.registry import SkillLoadError, SkillNotFoundError, SkillRegistry

_PLAYWRIGHT_SKILL = {
    "skill_id": "playwright-typescript-pom",
    "version": "1.0.0",
    "language": "typescript",
    "framework": "playwright",
    "pattern": "pom",
    "supported_locator_strategies": ["page_file"],
    "output_files": [
        {
            "artifact_type": "page_object",
            "path_template": "pages/{domain}/{route}.page.ts",
            "template_ref": "playwright/page_object.ts",
        }
    ],
    "generation_rules": ["Use POM"],
    "status": "active",
}

_PYTEST_SKILL = {
    "skill_id": "pytest-python-pom",
    "version": "1.0.0",
    "language": "python",
    "framework": "pytest",
    "pattern": "pom",
    "supported_locator_strategies": ["page_file"],
    "output_files": [
        {
            "artifact_type": "test_spec",
            "path_template": "tests/{domain}/test_{route}.py",
            "template_ref": "pytest/test_spec.py",
        }
    ],
    "generation_rules": ["Use POM"],
    "status": "active",
}


def _write_skill(directory: Path, filename: str, payload: dict) -> None:
    (directory / filename).write_text(json.dumps(payload), encoding="utf-8")


def test_registry_loads_skills_from_directory(tmp_path: Path) -> None:
    _write_skill(tmp_path, "playwright.json", _PLAYWRIGHT_SKILL)
    _write_skill(tmp_path, "pytest.json", _PYTEST_SKILL)

    registry = SkillRegistry(tmp_path)
    registry.load()

    assert registry.loaded_count == 2


def test_registry_get_returns_correct_skill(tmp_path: Path) -> None:
    _write_skill(tmp_path, "playwright.json", _PLAYWRIGHT_SKILL)

    registry = SkillRegistry(tmp_path)
    registry.load()

    skill = registry.get("playwright-typescript-pom")
    assert skill.version == "1.0.0"
    assert skill.language == Language.TYPESCRIPT
    assert skill.framework == Framework.PLAYWRIGHT


def test_registry_get_raises_for_unknown_skill(tmp_path: Path) -> None:
    _write_skill(tmp_path, "playwright.json", _PLAYWRIGHT_SKILL)

    registry = SkillRegistry(tmp_path)
    registry.load()

    with pytest.raises(SkillNotFoundError):
        registry.get("does-not-exist")


def test_registry_select_returns_active_skill_by_language_and_framework(tmp_path: Path) -> None:
    _write_skill(tmp_path, "playwright.json", _PLAYWRIGHT_SKILL)
    _write_skill(tmp_path, "pytest.json", _PYTEST_SKILL)

    registry = SkillRegistry(tmp_path)
    registry.load()

    skill = registry.select(Language.TYPESCRIPT, Framework.PLAYWRIGHT)
    assert skill is not None
    assert skill.skill_id == "playwright-typescript-pom"


def test_registry_select_returns_none_when_no_match(tmp_path: Path) -> None:
    _write_skill(tmp_path, "playwright.json", _PLAYWRIGHT_SKILL)

    registry = SkillRegistry(tmp_path)
    registry.load()

    assert registry.select(Language.JAVA, Framework.JUNIT) is None


def test_registry_select_excludes_non_active_skills(tmp_path: Path) -> None:
    disabled = {**_PLAYWRIGHT_SKILL, "status": "disabled"}
    _write_skill(tmp_path, "playwright.json", disabled)

    registry = SkillRegistry(tmp_path)
    registry.load()

    assert registry.select(Language.TYPESCRIPT, Framework.PLAYWRIGHT) is None


def test_registry_raises_on_missing_directory() -> None:
    registry = SkillRegistry(Path("/nonexistent/skills"))
    with pytest.raises(SkillLoadError, match="does not exist"):
        registry.load()


def test_registry_raises_on_duplicate_skill_id(tmp_path: Path) -> None:
    _write_skill(tmp_path, "a.json", _PLAYWRIGHT_SKILL)
    _write_skill(tmp_path, "b.json", _PLAYWRIGHT_SKILL)

    registry = SkillRegistry(tmp_path)
    with pytest.raises(SkillLoadError, match="Duplicate"):
        registry.load()


def test_registry_raises_on_invalid_skill_json(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text('{"skill_id": "x"}', encoding="utf-8")

    registry = SkillRegistry(tmp_path)
    with pytest.raises(SkillLoadError, match="bad.json"):
        registry.load()


def test_registry_all_active_filters_by_status(tmp_path: Path) -> None:
    _write_skill(tmp_path, "active.json", _PLAYWRIGHT_SKILL)
    draft = {**_PYTEST_SKILL, "status": "draft"}
    _write_skill(tmp_path, "draft.json", draft)

    registry = SkillRegistry(tmp_path)
    registry.load()

    assert len(registry.all_active()) == 1
    assert registry.all_active()[0].status == SkillStatus.ACTIVE
