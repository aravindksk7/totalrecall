"""Golden tests: prompt structural invariants using real skill definitions.

These tests load the production skill files and verify that the prompt builder
produces structurally correct messages for both supported frameworks. They catch
changes to skill definitions or the prompt builder that break generation contracts.
"""

from pathlib import Path

import pytest

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.context.models import ContextPlan, SelectedSkill, TokenBudget
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
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.prompts.builder import PromptBuilder
from totalrecall.providers.models import ProviderRole
from totalrecall.skills.registry import SkillRegistry

_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


@pytest.fixture(scope="module")
def registry() -> SkillRegistry:
    reg = SkillRegistry(_SKILLS_DIR)
    reg.load()
    return reg


@pytest.fixture(scope="module")
def builder(registry: SkillRegistry) -> PromptBuilder:
    wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "null"}),
        adapters={"null": NullMemoryAdapter()},
    )
    return PromptBuilder(skill_registry=registry, memory_wrapper=wrapper)


def _plan(skill_id: str) -> ContextPlan:
    return ContextPlan(
        context_plan_id="plan_golden",
        tenant_id="tenant_golden",
        application_id="app_golden",
        request_id="req_golden",
        selected_skills=[SelectedSkill(skill_id=skill_id, version="1.0.0")],
        selected_memories=[],
        skill_ids=[skill_id],
        memory_ids=[],
        token_budget=TokenBudget(max_input_tokens=8_000),
    )


def _playwright_request() -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_golden",
        application_id="app_golden",
        prompt="Generate a login page object for the authentication flow",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="auth", route="login"),
        options=GenerationOptions(validate=False, max_input_tokens=8_000),
    )


def _pytest_request() -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_golden",
        application_id="app_golden",
        prompt="Generate a pytest page object for the dashboard",
        target=GenerationTarget(
            language=Language.PYTHON,
            framework=Framework.PYTEST,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="dashboard", route="home"),
        options=GenerationOptions(validate=False, max_input_tokens=8_000),
    )


# --- Playwright TypeScript golden tests ---


def test_playwright_produces_system_and_user_messages(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    roles = {m.role for m in messages}
    assert ProviderRole.SYSTEM in roles
    assert ProviderRole.USER in roles


def test_playwright_produces_exactly_two_messages(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    assert len(messages) == 2


def test_playwright_system_mentions_framework(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    system = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
    assert "playwright" in system.lower()


def test_playwright_system_includes_artifact_schema(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    system = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
    assert "artifacts" in system
    assert "artifact_type" in system
    assert "content" in system


def test_playwright_system_has_generation_rules(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    system = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
    assert "POM" in system or "Page Object" in system


def test_playwright_system_includes_output_format_section(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    system = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
    assert "## Output Format" in system


def test_playwright_user_includes_scope_domain(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    user = next(m.content for m in messages if m.role == ProviderRole.USER)
    assert "auth" in user


def test_playwright_user_includes_prompt_text(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    user = next(m.content for m in messages if m.role == ProviderRole.USER)
    assert "login page object" in user


def test_playwright_user_has_request_section(builder: PromptBuilder) -> None:
    messages = builder.build(_playwright_request(), _plan("playwright-typescript-pom"))
    user = next(m.content for m in messages if m.role == ProviderRole.USER)
    assert "## Request" in user


# --- Pytest Python golden tests ---


def test_pytest_system_mentions_framework(builder: PromptBuilder) -> None:
    messages = builder.build(_pytest_request(), _plan("pytest-python-pom"))
    system = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
    assert "pytest" in system.lower()


def test_pytest_system_includes_artifact_schema(builder: PromptBuilder) -> None:
    messages = builder.build(_pytest_request(), _plan("pytest-python-pom"))
    system = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
    assert "artifacts" in system
    assert "content" in system


def test_pytest_system_has_fixture_rule(builder: PromptBuilder) -> None:
    messages = builder.build(_pytest_request(), _plan("pytest-python-pom"))
    system = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
    assert "fixture" in system.lower()


def test_pytest_user_includes_scope_domain(builder: PromptBuilder) -> None:
    messages = builder.build(_pytest_request(), _plan("pytest-python-pom"))
    user = next(m.content for m in messages if m.role == ProviderRole.USER)
    assert "dashboard" in user


def test_pytest_user_includes_prompt_text(builder: PromptBuilder) -> None:
    messages = builder.build(_pytest_request(), _plan("pytest-python-pom"))
    user = next(m.content for m in messages if m.role == ProviderRole.USER)
    assert "dashboard" in user
