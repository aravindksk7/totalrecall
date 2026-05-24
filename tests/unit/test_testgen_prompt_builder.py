"""Unit tests for TestGenPromptBuilder."""

from datetime import UTC, datetime
from pathlib import Path

from totalrecall.context.models import ContextPlan, TokenBudget
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
from totalrecall.providers.models import ProviderRole
from totalrecall.testgen.jira.models import JiraAcceptanceCriterion, JiraStory
from totalrecall.testgen.models import ReformulatedIntent, TestType
from totalrecall.testgen.prompts.testgen_builder import TestGenPromptBuilder


def _make_request() -> GenerationRequest:
    return GenerationRequest(
        tenant_id="t1",
        application_id="app1",
        prompt="Generate tests for the login flow",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="auth"),
        options=GenerationOptions(validate=False, max_input_tokens=12_000),
    )


def _make_plan(jira_story=None, rag_chunks=None) -> ContextPlan:
    return ContextPlan(
        context_plan_id="plan-1",
        tenant_id="t1",
        application_id="app1",
        request_id="req-1",
        token_budget=TokenBudget(max_input_tokens=12_000),
        jira_story=jira_story,
        rag_chunks=rag_chunks or [],
    )


def _make_intent(test_types: list[TestType] | None = None) -> ReformulatedIntent:
    return ReformulatedIntent(
        intent_summary="Verify login works correctly",
        test_types=test_types or [TestType.FUNCTIONAL],
        raw_prompt="test the login page",
    )


class TestTestGenPromptBuilder:
    def test_builds_system_and_user_messages(self):
        builder = TestGenPromptBuilder()
        messages = builder.build(_make_request(), _make_plan(), _make_intent(), [TestType.FUNCTIONAL])
        roles = [m.role for m in messages]
        assert ProviderRole.SYSTEM in roles
        assert ProviderRole.USER in roles

    def test_system_message_contains_requested_test_types(self):
        builder = TestGenPromptBuilder()
        messages = builder.build(
            _make_request(), _make_plan(), _make_intent(),
            [TestType.FUNCTIONAL, TestType.NEGATIVE],
        )
        system_text = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
        assert "functional" in system_text
        assert "negative" in system_text

    def test_system_message_contains_output_schema(self):
        builder = TestGenPromptBuilder()
        messages = builder.build(_make_request(), _make_plan(), _make_intent(), [TestType.FUNCTIONAL])
        system_text = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)
        assert "test_cases" in system_text
        assert "story_summary" in system_text

    def test_user_message_contains_jira_story(self):
        story = JiraStory(
            jira_key="AUTH-1",
            summary="User can log in",
            acceptance_criteria=[JiraAcceptanceCriterion(index=0, text="Valid creds redirect to home")],
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        builder = TestGenPromptBuilder()
        messages = builder.build(
            _make_request(), _make_plan(jira_story=story), _make_intent(), [TestType.FUNCTIONAL]
        )
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)
        assert "AUTH-1" in user_text
        assert "User can log in" in user_text
        assert "Valid creds redirect to home" in user_text

    def test_user_message_contains_all_section_headers(self):
        builder = TestGenPromptBuilder()
        active_types = [TestType.FUNCTIONAL, TestType.NEGATIVE, TestType.EDGE_CASE]
        messages = builder.build(_make_request(), _make_plan(), _make_intent(), active_types)
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)
        assert "Functional Tests" in user_text
        assert "Negative Tests" in user_text
        assert "Edge Case Tests" in user_text

    def test_user_message_contains_intent_summary(self):
        builder = TestGenPromptBuilder()
        intent = _make_intent()
        messages = builder.build(_make_request(), _make_plan(), intent, [TestType.FUNCTIONAL])
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)
        assert "Verify login works correctly" in user_text

    def test_user_message_contains_original_prompt(self):
        builder = TestGenPromptBuilder()
        messages = builder.build(_make_request(), _make_plan(), _make_intent(), [TestType.FUNCTIONAL])
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)
        assert "Generate tests for the login flow" in user_text

    def test_rag_chunks_appear_in_user_message(self):
        chunks = [type("Chunk", (), {"chunk_text": "Use explicit waits"})()]
        builder = TestGenPromptBuilder()
        messages = builder.build(
            _make_request(), _make_plan(rag_chunks=chunks), _make_intent(), [TestType.FUNCTIONAL]
        )
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)
        assert "Use explicit waits" in user_text

    def test_api_test_section_present_when_requested(self):
        builder = TestGenPromptBuilder()
        messages = builder.build(_make_request(), _make_plan(), _make_intent(), [TestType.API])
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)
        assert "API Tests" in user_text

    def test_regression_test_section_present_when_requested(self):
        builder = TestGenPromptBuilder()
        messages = builder.build(_make_request(), _make_plan(), _make_intent(), [TestType.REGRESSION])
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)
        assert "Regression Tests" in user_text

    def test_user_message_includes_jira_story_description(self):
        story = JiraStory(
            jira_key="AUTH-2",
            summary="User can log in",
            description="This covers the standard login flow with email and password.",
            acceptance_criteria=[],
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        builder = TestGenPromptBuilder()
        messages = builder.build(
            _make_request(), _make_plan(jira_story=story), _make_intent(), [TestType.FUNCTIONAL]
        )
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)
        assert "This covers the standard login flow" in user_text
