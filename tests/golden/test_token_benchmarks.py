"""Benchmark fixtures: verify context planner token estimates for known request shapes.

These are deterministic checks that the baseline and optimised token estimates
stay within expected ranges as the prompt builder and skill definitions evolve.
A large unexpected change in token counts indicates a regression in the prompt
synthesis or token-estimate logic.
"""

from pathlib import Path

import pytest

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
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
    ProviderSelection,
)
from totalrecall.memory.adapters.null import NullMemoryAdapter
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.skills.registry import SkillRegistry

_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


@pytest.fixture(scope="module")
def planner() -> ContextPlanner:
    registry = SkillRegistry(_SKILLS_DIR)
    registry.load()
    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "null"}),
        adapters={"null": NullMemoryAdapter()},
    )
    return ContextPlanner(skill_registry=registry, memory_wrapper=wrapper)


def _playwright_request() -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_bench",
        application_id="app_bench",
        prompt="Generate a login page object for the authentication flow",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="auth", route="/login"),
        provider=ProviderSelection(),
        options=GenerationOptions(validate=False, max_input_tokens=12_000),
    )


def _pytest_request() -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_bench",
        application_id="app_bench",
        prompt="Generate a pytest page object for the dashboard overview",
        target=GenerationTarget(
            language=Language.PYTHON,
            framework=Framework.PYTEST,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="dashboard", route="/dashboard"),
        provider=ProviderSelection(),
        options=GenerationOptions(validate=False, max_input_tokens=12_000),
    )


# --- Playwright TypeScript benchmarks ---

def test_playwright_baseline_estimate_is_positive(planner: ContextPlanner) -> None:
    plan = planner.plan(_playwright_request(), "req_bench_1")
    assert plan.token_budget.baseline_estimate > 0


def test_playwright_estimated_input_tokens_is_positive(planner: ContextPlanner) -> None:
    plan = planner.plan(_playwright_request(), "req_bench_2")
    assert plan.token_budget.estimated_input_tokens > 0


def test_playwright_estimate_within_budget(planner: ContextPlanner) -> None:
    req = _playwright_request()
    plan = planner.plan(req, "req_bench_3")
    assert plan.token_budget.estimated_input_tokens <= req.options.max_input_tokens


def test_playwright_estimate_includes_skill_tokens(planner: ContextPlanner) -> None:
    """Skill rules contribute tokens — estimate > overhead + prompt words alone."""
    plan = planner.plan(_playwright_request(), "req_bench_4")
    # 300 overhead + ~10 prompt words = ~310 bare minimum; skill rules push it higher
    assert plan.token_budget.estimated_input_tokens > 310


def test_playwright_skill_selected(planner: ContextPlanner) -> None:
    plan = planner.plan(_playwright_request(), "req_bench_5")
    assert len(plan.selected_skills) == 1
    assert plan.selected_skills[0].skill_id == "playwright-typescript-pom"


# --- Pytest Python benchmarks ---

def test_pytest_baseline_estimate_is_positive(planner: ContextPlanner) -> None:
    plan = planner.plan(_pytest_request(), "req_bench_6")
    assert plan.token_budget.baseline_estimate > 0


def test_pytest_skill_selected(planner: ContextPlanner) -> None:
    plan = planner.plan(_pytest_request(), "req_bench_7")
    assert len(plan.selected_skills) == 1
    assert plan.selected_skills[0].skill_id == "pytest-python-pom"


def test_pytest_estimate_within_budget(planner: ContextPlanner) -> None:
    req = _pytest_request()
    plan = planner.plan(req, "req_bench_8")
    assert plan.token_budget.estimated_input_tokens <= req.options.max_input_tokens


# --- Comparative benchmarks ---

def test_no_memory_means_baseline_equals_optimised(planner: ContextPlanner) -> None:
    """With NullMemoryAdapter there are no memories, so optimised == baseline."""
    plan = planner.plan(_playwright_request(), "req_bench_9")
    assert plan.token_budget.estimated_input_tokens == plan.token_budget.baseline_estimate


def test_unknown_framework_produces_no_skill(planner: ContextPlanner) -> None:
    req = GenerationRequest(
        tenant_id="tenant_bench",
        application_id="app_bench",
        prompt="Generate something",
        target=GenerationTarget(
            language=Language.JAVA,
            framework=Framework.JUNIT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="api"),
        provider=ProviderSelection(),
        options=GenerationOptions(validate=False, max_input_tokens=12_000),
    )
    plan = planner.plan(req, "req_bench_10")
    assert plan.selected_skills == []
    assert len(plan.excluded) >= 1
