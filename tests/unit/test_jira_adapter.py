"""Unit tests for JIRA adapter implementations."""

from datetime import UTC, datetime

import pytest

from totalrecall.testgen.jira.adapter import (
    NullJiraAdapter,
    StubJiraAdapter,
    _parse_acceptance_criteria,
)
from totalrecall.testgen.jira.models import JiraAcceptanceCriterion, JiraStory


class TestParseAcceptanceCriteria:
    def test_parses_bullet_list(self):
        text = "- User can log in\n- User sees dashboard"
        criteria = _parse_acceptance_criteria(text)
        assert len(criteria) == 2
        assert criteria[0].text == "User can log in"
        assert criteria[0].index == 0
        assert criteria[1].text == "User sees dashboard"
        assert criteria[1].index == 1

    def test_parses_asterisk_list(self):
        text = "* First criterion\n* Second criterion"
        criteria = _parse_acceptance_criteria(text)
        assert len(criteria) == 2

    def test_empty_text_returns_empty(self):
        assert _parse_acceptance_criteria("") == []

    def test_plain_text_no_bullets_returns_empty(self):
        assert _parse_acceptance_criteria("User can log in to the system.") == []


class TestStubJiraAdapter:
    def test_returns_story_for_any_key(self):
        stub = StubJiraAdapter()
        story = stub.fetch_story("PROJ-1")
        assert story is not None
        assert story.jira_key == "PROJ-1"
        assert story.summary.startswith("Stub story for")
        assert len(story.acceptance_criteria) == 2

    def test_returns_fixed_story_when_provided(self):
        fixed = JiraStory(
            jira_key="FIXED-1",
            summary="Fixed story",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        stub = StubJiraAdapter(story=fixed)
        result = stub.fetch_story("ANYTHING")
        assert result is fixed

    def test_health_returns_ok(self):
        assert StubJiraAdapter().health()["status"] == "ok"

    def test_adapter_version(self):
        assert StubJiraAdapter().adapter_version == "stub"


class TestNullJiraAdapter:
    def test_fetch_story_returns_none(self):
        null = NullJiraAdapter()
        assert null.fetch_story("PROJ-1") is None

    def test_health_returns_disabled(self):
        assert NullJiraAdapter().health()["status"] == "disabled"

    def test_adapter_version(self):
        assert NullJiraAdapter().adapter_version == "null"
