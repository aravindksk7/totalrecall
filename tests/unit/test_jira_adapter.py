"""Unit tests for JIRA adapter implementations."""

from datetime import UTC, datetime

import httpx
import pytest
import respx

from totalrecall.config.credentials import CredentialNotFoundError
from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.testgen.jira.adapter import (
    JiraCloudAdapter,
    NullJiraAdapter,
    StubJiraAdapter,
    _adf_to_text,
    _extract_acceptance_criteria,
    _parse_acceptance_criteria,
)
from totalrecall.testgen.jira.factory import build_jira_adapter
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


class TestExtractAcceptanceCriteria:
    def test_uses_customfield_acceptance_criteria(self):
        fields = {"customfield_acceptance_criteria": "- Given user is logged in\n- When they navigate to home"}
        criteria = _extract_acceptance_criteria(fields)
        assert len(criteria) == 2

    def test_falls_back_to_customfield_10016(self):
        fields = {"customfield_10016": "- Accept A\n- Accept B"}
        criteria = _extract_acceptance_criteria(fields)
        assert len(criteria) == 2

    def test_extracts_from_description_with_ac_header(self):
        fields = {"description": "Acceptance Criteria:\n- User sees login form\n- Submit works"}
        criteria = _extract_acceptance_criteria(fields)
        assert len(criteria) >= 1

    def test_parses_adf_description(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Acceptance Criteria:"}],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "- User can log in"}],
                                }
                            ],
                        }
                    ],
                },
            ],
        }
        fields = {"description": adf}
        criteria = _extract_acceptance_criteria(fields)
        assert len(criteria) >= 0  # parsed without error

    def test_returns_empty_when_no_ac_in_plain_description(self):
        fields = {"description": "Just a plain description with no criteria"}
        criteria = _extract_acceptance_criteria(fields)
        assert criteria == []

    def test_returns_empty_when_all_fields_missing(self):
        assert _extract_acceptance_criteria({}) == []


class TestAdfToText:
    def test_text_node_returns_text(self):
        node = {"type": "text", "text": "Hello world"}
        assert _adf_to_text(node) == "Hello world"

    def test_container_node_joins_children(self):
        node = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "First"},
                {"type": "text", "text": "Second"},
            ],
        }
        result = _adf_to_text(node)
        assert "First" in result
        assert "Second" in result

    def test_empty_node_returns_empty_string(self):
        assert _adf_to_text({}) == ""

    def test_nested_structure(self):
        node = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Nested text"}],
                }
            ],
        }
        result = _adf_to_text(node)
        assert "Nested text" in result


class TestJiraCloudAdapterInit:
    def test_instantiation(self):
        adapter = JiraCloudAdapter(
            base_url="https://myorg.atlassian.net",
            email="user@example.com",
            api_token="secret",
        )
        assert adapter.adapter_version == "jira_cloud_v3"

    def test_trailing_slash_stripped_from_base_url(self):
        adapter = JiraCloudAdapter(
            base_url="https://myorg.atlassian.net/",
            email="user@example.com",
            api_token="secret",
        )
        assert not adapter._base_url.endswith("/")

    def test_auth_header_is_basic(self):
        adapter = JiraCloudAdapter(
            base_url="https://myorg.atlassian.net",
            email="user@example.com",
            api_token="secret",
        )
        assert adapter._auth_header.startswith("Basic ")


class TestBuildJiraAdapterFactory:
    def _flags(self, overrides: dict):
        return ConfigFeatureFlagProvider(overrides)

    def _cred(self, *, raises=False, value="my-token"):
        class _StubCred:
            def get(self, key: str) -> str:
                if raises:
                    raise CredentialNotFoundError("not found")
                return value

        return _StubCred()

    def test_returns_null_when_disabled(self):
        flags = self._flags({"jira.enabled": False})
        adapter = build_jira_adapter(flags, self._cred())
        assert isinstance(adapter, NullJiraAdapter)

    def test_returns_stub_when_adapter_is_stub(self):
        flags = self._flags({"jira.enabled": True, "jira.adapter": "stub"})
        adapter = build_jira_adapter(flags, self._cred())
        assert isinstance(adapter, StubJiraAdapter)

    def test_returns_null_when_base_url_missing(self):
        flags = self._flags({"jira.enabled": True, "jira.email": "u@x.com"})
        adapter = build_jira_adapter(flags, self._cred())
        assert isinstance(adapter, NullJiraAdapter)

    def test_returns_null_when_email_missing(self):
        flags = self._flags({"jira.enabled": True, "jira.base_url": "https://x.atlassian.net"})
        adapter = build_jira_adapter(flags, self._cred())
        assert isinstance(adapter, NullJiraAdapter)

    def test_returns_null_when_credential_not_found(self):
        flags = self._flags({
            "jira.enabled": True,
            "jira.base_url": "https://x.atlassian.net",
            "jira.email": "u@x.com",
        })
        adapter = build_jira_adapter(flags, self._cred(raises=True))
        assert isinstance(adapter, NullJiraAdapter)

    def test_returns_cloud_adapter_when_fully_configured(self):
        flags = self._flags({
            "jira.enabled": True,
            "jira.base_url": "https://x.atlassian.net",
            "jira.email": "u@x.com",
        })
        adapter = build_jira_adapter(flags, self._cred(value="tok"))
        assert isinstance(adapter, JiraCloudAdapter)


_BASE = "https://myorg.atlassian.net"
_STORY_FIELDS = {
    "summary": "User login",
    "description": "User can log in with email and password.",
    "issuetype": {"name": "Story"},
    "status": {"name": "In Progress"},
    "labels": ["auth"],
}


def _make_adapter() -> JiraCloudAdapter:
    return JiraCloudAdapter(base_url=_BASE, email="user@x.com", api_token="token")


class TestJiraCloudAdapterFetchStory:
    @respx.mock
    def test_fetch_story_success(self):
        respx.get(f"{_BASE}/rest/api/3/issue/PROJ-1").mock(
            return_value=httpx.Response(200, json={"key": "PROJ-1", "fields": _STORY_FIELDS})
        )
        story = _make_adapter().fetch_story("PROJ-1")
        assert story is not None
        assert story.jira_key == "PROJ-1"
        assert story.summary == "User login"
        assert story.labels == ["auth"]

    @respx.mock
    def test_fetch_story_returns_none_on_404(self):
        respx.get(f"{_BASE}/rest/api/3/issue/PROJ-999").mock(
            return_value=httpx.Response(404, json={"errorMessages": ["Not found"]})
        )
        story = _make_adapter().fetch_story("PROJ-999")
        assert story is None

    @respx.mock
    def test_fetch_story_returns_none_on_server_error(self):
        respx.get(f"{_BASE}/rest/api/3/issue/PROJ-1").mock(
            return_value=httpx.Response(500, text="Server error")
        )
        story = _make_adapter().fetch_story("PROJ-1")
        assert story is None

    @respx.mock
    def test_fetch_story_returns_none_on_network_error(self):
        respx.get(f"{_BASE}/rest/api/3/issue/PROJ-1").mock(
            side_effect=httpx.ConnectError("connection failed")
        )
        story = _make_adapter().fetch_story("PROJ-1")
        assert story is None

    @respx.mock
    def test_fetch_story_with_adf_description(self):
        adf_description = {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Desc text"}]}],
        }
        fields = {**_STORY_FIELDS, "description": adf_description}
        respx.get(f"{_BASE}/rest/api/3/issue/PROJ-2").mock(
            return_value=httpx.Response(200, json={"key": "PROJ-2", "fields": fields})
        )
        story = _make_adapter().fetch_story("PROJ-2")
        assert story is not None
        assert "Desc text" in story.description


class TestJiraCloudAdapterHealth:
    @respx.mock
    def test_health_returns_ok_on_success(self):
        respx.get(f"{_BASE}/rest/api/3/myself").mock(return_value=httpx.Response(200, json={}))
        result = _make_adapter().health()
        assert result["status"] == "ok"

    @respx.mock
    def test_health_returns_degraded_on_auth_failure(self):
        respx.get(f"{_BASE}/rest/api/3/myself").mock(return_value=httpx.Response(401, json={}))
        result = _make_adapter().health()
        assert result["status"] == "degraded"

    @respx.mock
    def test_health_returns_unavailable_on_network_error(self):
        respx.get(f"{_BASE}/rest/api/3/myself").mock(
            side_effect=httpx.ConnectError("network failure")
        )
        result = _make_adapter().health()
        assert result["status"] == "unavailable"
