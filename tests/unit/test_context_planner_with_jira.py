"""Tests for ContextPlanner with JIRA and RAG plan_inputs injection."""

from datetime import UTC, datetime
from pathlib import Path

from totalrecall.context.planner import ContextPlanner, ExternalPlanInputs
from totalrecall.testgen.jira.models import JiraAcceptanceCriterion, JiraStory

from tests.unit.test_context_planner import _make_memory_wrapper, _make_registry, _make_request


class TestContextPlannerWithJira:
    def test_plan_inputs_jira_story_appears_on_plan(self, tmp_path: Path) -> None:
        story = JiraStory(
            jira_key="PROJ-42",
            summary="User can log in",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        planner = ContextPlanner(_make_registry(tmp_path), _make_memory_wrapper())
        plan = planner.plan(_make_request(), "req-1", plan_inputs=ExternalPlanInputs(jira_story=story))
        assert plan.jira_story is story
        assert plan.jira_story.jira_key == "PROJ-42"

    def test_plan_no_inputs_jira_story_is_none(self, tmp_path: Path) -> None:
        planner = ContextPlanner(_make_registry(tmp_path), _make_memory_wrapper())
        plan = planner.plan(_make_request(), "req-1")
        assert plan.jira_story is None

    def test_plan_inputs_rag_chunks_appear_on_plan(self, tmp_path: Path) -> None:
        chunks = [{"chunk_text": "Use page objects"}, {"chunk_text": "Prefer data-driven tests"}]
        planner = ContextPlanner(_make_registry(tmp_path), _make_memory_wrapper())
        plan = planner.plan(_make_request(), "req-1", plan_inputs=ExternalPlanInputs(rag_chunks=chunks))
        assert plan.rag_chunks == chunks

    def test_plan_no_inputs_rag_chunks_empty(self, tmp_path: Path) -> None:
        planner = ContextPlanner(_make_registry(tmp_path), _make_memory_wrapper())
        plan = planner.plan(_make_request(), "req-1")
        assert plan.rag_chunks == []

    def test_plan_inputs_with_both_jira_and_rag(self, tmp_path: Path) -> None:
        story = JiraStory(
            jira_key="TEST-1",
            summary="Test story",
            acceptance_criteria=[JiraAcceptanceCriterion(index=0, text="AC1")],
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        chunks = [{"chunk_text": "guidance"}]
        planner = ContextPlanner(_make_registry(tmp_path), _make_memory_wrapper())
        plan = planner.plan(
            _make_request(), "req-1", plan_inputs=ExternalPlanInputs(jira_story=story, rag_chunks=chunks)
        )
        assert plan.jira_story is story
        assert plan.rag_chunks == chunks
