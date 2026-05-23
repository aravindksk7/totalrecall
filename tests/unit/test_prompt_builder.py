import json
from pathlib import Path

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.context.models import ContextPlan, SelectedMemory, SelectedSkill, TokenBudget
from totalrecall.generation.models import (
    AutomationPattern,
    Framework,
    GenerationOptions,
    GenerationRequest,
    GenerationScope,
    GenerationTarget,
    Language,
    LocatorStrategy,
)
from totalrecall.memory.adapters.null import NullMemoryAdapter
from totalrecall.memory.adapters.stub import StubMemoryAdapter
from totalrecall.memory.models import MemoryEntry
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.prompts.builder import PromptBuilder
from totalrecall.providers.models import ProviderRole
from totalrecall.skills.registry import SkillRegistry

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
    "generation_rules": ["Use POM", "Async/await for all actions"],
    "status": "active",
}


def _make_registry(tmp_path: Path) -> SkillRegistry:
    (tmp_path / "skill.json").write_text(json.dumps(_PLAYWRIGHT_SKILL), encoding="utf-8")
    reg = SkillRegistry(tmp_path)
    reg.load()
    return reg


def _make_memory_wrapper(entries: list[MemoryEntry] | None = None) -> MemoryWrapper:
    entries = entries or []
    return MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        adapters={
            "stub": StubMemoryAdapter(entries),
            "null": NullMemoryAdapter(),
        },
    )


def _make_request() -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_test",
        application_id="app_test",
        prompt="Generate a page object for the checkout page",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="checkout", route="checkout"),
        options=GenerationOptions(validate=True, max_input_tokens=12_000),
    )


def _make_plan(
    skill_ids: list[str] | None = None, memory_ids: list[str] | None = None
) -> ContextPlan:
    skills = [SelectedSkill(skill_id=sid, version="1.0.0") for sid in (skill_ids or [])]
    memories = [SelectedMemory(memory_id=mid) for mid in (memory_ids or [])]
    return ContextPlan(
        context_plan_id="plan_001",
        tenant_id="tenant_test",
        application_id="app_test",
        request_id="req_001",
        selected_skills=skills,
        selected_memories=memories,
        skill_ids=[s.skill_id for s in skills],
        memory_ids=[m.memory_id for m in memories],
        token_budget=TokenBudget(max_input_tokens=12_000),
    )


def test_builder_produces_system_and_user_messages(tmp_path: Path) -> None:
    builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
    plan = _make_plan(skill_ids=["playwright-typescript-pom"])

    messages = builder.build(_make_request(), plan)

    roles = [m.role for m in messages]
    assert ProviderRole.SYSTEM in roles
    assert ProviderRole.USER in roles


def test_builder_system_message_includes_generation_rules(tmp_path: Path) -> None:
    builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
    plan = _make_plan(skill_ids=["playwright-typescript-pom"])

    messages = builder.build(_make_request(), plan)
    system_text = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)

    assert "Use POM" in system_text
    assert "Async/await" in system_text


def test_builder_system_message_includes_output_schema(tmp_path: Path) -> None:
    builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
    plan = _make_plan(skill_ids=["playwright-typescript-pom"])

    messages = builder.build(_make_request(), plan)
    system_text = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)

    assert "artifacts" in system_text
    assert "artifact_type" in system_text


def test_builder_user_message_includes_prompt(tmp_path: Path) -> None:
    builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
    plan = _make_plan(skill_ids=["playwright-typescript-pom"])

    messages = builder.build(_make_request(), plan)
    user_text = next(m.content for m in messages if m.role == ProviderRole.USER)

    assert "Generate a page object" in user_text


def test_builder_user_message_includes_scope(tmp_path: Path) -> None:
    builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
    plan = _make_plan(skill_ids=["playwright-typescript-pom"])

    messages = builder.build(_make_request(), plan)
    user_text = next(m.content for m in messages if m.role == ProviderRole.USER)

    assert "checkout" in user_text


def test_builder_user_message_includes_memory_knowledge(tmp_path: Path) -> None:
    entry = MemoryEntry(
        entity_id="mem_submit",
        tenant_id="tenant_test",
        application_id="app_test",
        summary="Submit button",
        knowledge="Submit button uses role=button name=Submit.",
        tags={"domain": "checkout"},
    )
    builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper([entry]))
    plan = _make_plan(skill_ids=["playwright-typescript-pom"], memory_ids=["mem_submit"])

    messages = builder.build(_make_request(), plan)
    user_text = next(m.content for m in messages if m.role == ProviderRole.USER)

    assert "Submit button" in user_text
    assert "role=button" in user_text


def test_builder_without_memory_omits_context_section(tmp_path: Path) -> None:
    builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
    plan = _make_plan(skill_ids=["playwright-typescript-pom"])

    messages = builder.build(_make_request(), plan)
    user_text = next(m.content for m in messages if m.role == ProviderRole.USER)

    assert "Project Context" not in user_text


def test_artifact_schema_is_valid_json_schema(tmp_path: Path) -> None:
    schema = PromptBuilder.artifact_schema()

    assert schema["type"] == "object"
    assert "artifacts" in schema["properties"]
    assert "content" in schema["properties"]["artifacts"]["items"]["properties"]
