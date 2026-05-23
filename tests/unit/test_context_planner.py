import json
from pathlib import Path

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.context.models import ContextExclusionReason
from totalrecall.context.planner import ContextPlanner
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
    "generation_rules": ["Use POM", "Async/await"],
    "status": "active",
}


def _make_registry(tmp_path: Path, skill: dict = _PLAYWRIGHT_SKILL) -> SkillRegistry:
    (tmp_path / "skill.json").write_text(json.dumps(skill), encoding="utf-8")
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


def _make_request(
    language: Language = Language.TYPESCRIPT,
    framework: Framework = Framework.PLAYWRIGHT,
    domain: str = "checkout",
    route: str | None = None,
    max_input_tokens: int = 12_000,
) -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_test",
        application_id="app_test",
        prompt="Generate a page object for the checkout page",
        target=GenerationTarget(
            language=language,
            framework=framework,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain=domain, route=route),
        options=GenerationOptions(validate=True, max_input_tokens=max_input_tokens),
    )


def test_planner_selects_matching_skill(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    planner = ContextPlanner(registry, _make_memory_wrapper())

    plan = planner.plan(_make_request(), request_id="req_001")

    assert plan.skill_ids == ["playwright-typescript-pom"]
    assert plan.selected_skills[0].version == "1.0.0"


def test_planner_excludes_unmatched_framework(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    planner = ContextPlanner(registry, _make_memory_wrapper())

    plan = planner.plan(
        _make_request(language=Language.JAVA, framework=Framework.JUNIT),
        request_id="req_002",
    )

    assert plan.skill_ids == []
    assert len(plan.excluded) == 1
    assert plan.excluded[0].reason == ContextExclusionReason.FRAMEWORK_MISMATCH


def test_planner_includes_memory_matching_domain(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    entry = MemoryEntry(
        entity_id="mem_checkout_btn",
        tenant_id="tenant_test",
        application_id="app_test",
        summary="Checkout button",
        knowledge="Checkout button is role=button name=Checkout.",
        tags={"domain": "checkout"},
    )
    planner = ContextPlanner(registry, _make_memory_wrapper([entry]))

    plan = planner.plan(_make_request(domain="checkout"), request_id="req_003")

    assert "mem_checkout_btn" in plan.memory_ids


def test_planner_excludes_memories_over_token_budget(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)

    # Each memory costs 60 tokens; request 1 token of budget to force exclusion
    entries = [
        MemoryEntry(
            entity_id=f"mem_{i}",
            tenant_id="tenant_test",
            application_id="app_test",
            summary=f"Memory {i}",
            knowledge=f"Knowledge {i}",
            tags={"domain": "checkout"},
        )
        for i in range(10)
    ]
    planner = ContextPlanner(registry, _make_memory_wrapper(entries))

    # Very tight budget — skill tokens (~40) + overhead (300) exhaust most of 400 tokens
    plan = planner.plan(_make_request(max_input_tokens=400), request_id="req_004")

    excluded_reasons = [e.reason for e in plan.excluded]
    assert ContextExclusionReason.TOKEN_BUDGET in excluded_reasons


def test_planner_sets_tenant_and_application_on_plan(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    planner = ContextPlanner(registry, _make_memory_wrapper())

    plan = planner.plan(_make_request(), request_id="req_005")

    assert plan.tenant_id == "tenant_test"
    assert plan.application_id == "app_test"
    assert plan.request_id == "req_005"


def test_planner_token_budget_is_populated(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    planner = ContextPlanner(registry, _make_memory_wrapper())

    plan = planner.plan(_make_request(), request_id="req_006")

    assert plan.token_budget.max_input_tokens == 12_000
    assert plan.token_budget.estimated_input_tokens >= 0
