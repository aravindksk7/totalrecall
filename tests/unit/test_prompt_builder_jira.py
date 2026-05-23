"""Tests for PromptBuilder JIRA story and RAG chunk injection."""

from datetime import UTC, datetime
from pathlib import Path

from totalrecall.context.models import ContextPlan, SelectedSkill, TokenBudget
from totalrecall.providers.models import ProviderRole
from totalrecall.testgen.jira.models import JiraAcceptanceCriterion, JiraStory

from tests.unit.test_prompt_builder import (
    _make_memory_wrapper,
    _make_plan,
    _make_registry,
    _make_request,
)
from totalrecall.prompts.builder import PromptBuilder


def _make_plan_with_jira(
    jira_story: JiraStory | None = None,
    rag_chunks: list | None = None,
) -> ContextPlan:
    plan = _make_plan(skill_ids=["playwright-typescript-pom"])
    return plan.model_copy(
        update={"jira_story": jira_story, "rag_chunks": rag_chunks or []}
    )


class TestPromptBuilderJira:
    def test_jira_story_summary_appears_in_user_message(self, tmp_path: Path) -> None:
        story = JiraStory(
            jira_key="PROJ-99",
            summary="User can complete checkout",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
        plan = _make_plan_with_jira(jira_story=story)

        messages = builder.build(_make_request(), plan)
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)

        assert "PROJ-99" in user_text
        assert "User can complete checkout" in user_text

    def test_jira_story_acceptance_criteria_appear_in_user_message(self, tmp_path: Path) -> None:
        story = JiraStory(
            jira_key="PROJ-10",
            summary="Login flow",
            acceptance_criteria=[
                JiraAcceptanceCriterion(index=0, text="User sees error on bad password"),
                JiraAcceptanceCriterion(index=1, text="User is redirected on success"),
            ],
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
        plan = _make_plan_with_jira(jira_story=story)

        messages = builder.build(_make_request(), plan)
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)

        assert "User sees error on bad password" in user_text
        assert "User is redirected on success" in user_text

    def test_no_jira_story_omits_jira_section(self, tmp_path: Path) -> None:
        builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
        plan = _make_plan_with_jira(jira_story=None)

        messages = builder.build(_make_request(), plan)
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)

        assert "JIRA Story" not in user_text

    def test_jira_story_prepended_before_scope(self, tmp_path: Path) -> None:
        story = JiraStory(
            jira_key="PROJ-5",
            summary="First story",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
        plan = _make_plan_with_jira(jira_story=story)

        messages = builder.build(_make_request(), plan)
        user_text = next(m.content for m in messages if m.role == ProviderRole.USER)

        jira_pos = user_text.find("JIRA Story")
        scope_pos = user_text.find("## Scope")
        assert jira_pos < scope_pos

    def test_rag_chunks_appear_in_system_message(self, tmp_path: Path) -> None:
        chunks = [
            type("Chunk", (), {"chunk_text": "Use explicit waits in Playwright"})(),
            type("Chunk", (), {"chunk_text": "Prefer getByRole over CSS selectors"})(),
        ]
        builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
        plan = _make_plan_with_jira(rag_chunks=chunks)

        messages = builder.build(_make_request(), plan)
        system_text = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)

        assert "Use explicit waits in Playwright" in system_text
        assert "Prefer getByRole over CSS selectors" in system_text

    def test_rag_section_header_present_when_chunks_exist(self, tmp_path: Path) -> None:
        chunks = [type("Chunk", (), {"chunk_text": "Some guidance"})()]
        builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
        plan = _make_plan_with_jira(rag_chunks=chunks)

        messages = builder.build(_make_request(), plan)
        system_text = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)

        assert "Testing Guidance from Knowledge Base" in system_text

    def test_no_rag_chunks_omits_rag_section(self, tmp_path: Path) -> None:
        builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
        plan = _make_plan_with_jira(rag_chunks=[])

        messages = builder.build(_make_request(), plan)
        system_text = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)

        assert "Testing Guidance from Knowledge Base" not in system_text

    def test_rag_chunks_capped_at_three(self, tmp_path: Path) -> None:
        chunks = [
            type("Chunk", (), {"chunk_text": f"Guidance {i}"})()
            for i in range(5)
        ]
        builder = PromptBuilder(_make_registry(tmp_path), _make_memory_wrapper())
        plan = _make_plan_with_jira(rag_chunks=chunks)

        messages = builder.build(_make_request(), plan)
        system_text = next(m.content for m in messages if m.role == ProviderRole.SYSTEM)

        assert "Guidance 0" in system_text
        assert "Guidance 2" in system_text
        assert "Guidance 3" not in system_text
        assert "Guidance 4" not in system_text
