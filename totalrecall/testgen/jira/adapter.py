"""JIRA adapter: fetches story + acceptance criteria via JIRA Cloud REST v3."""

import base64
import re
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from totalrecall.testgen.jira.models import JiraAcceptanceCriterion, JiraStory

_AC_LINE_RE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
_AC_HEADER_RE = re.compile(
    r"(?:acceptance\s+criteria?|given|when|then)[:\s]",
    re.IGNORECASE,
)


def _parse_acceptance_criteria(text: str) -> list[JiraAcceptanceCriterion]:
    """Extract bullet-point acceptance criteria from description or custom field text."""
    lines = _AC_LINE_RE.findall(text)
    return [
        JiraAcceptanceCriterion(index=i, text=line.strip())
        for i, line in enumerate(lines)
        if line.strip()
    ]


def _extract_acceptance_criteria(fields: dict[str, Any]) -> list[JiraAcceptanceCriterion]:
    for key in ("customfield_acceptance_criteria", "customfield_10016"):
        value = fields.get(key)
        if value and isinstance(value, str):
            return _parse_acceptance_criteria(value)

    description = fields.get("description") or ""
    if isinstance(description, dict):
        description = _adf_to_text(description)
    if _AC_HEADER_RE.search(description):
        return _parse_acceptance_criteria(description)

    return []


def _adf_to_text(node: dict) -> str:
    """Minimal Atlassian Document Format → plain text extractor."""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = []
    for child in node.get("content", []):
        parts.append(_adf_to_text(child))
    return "\n".join(p for p in parts if p)


@runtime_checkable
class JiraAdapterProtocol(Protocol):
    adapter_version: str

    def fetch_story(self, jira_key: str) -> JiraStory | None: ...
    def health(self) -> dict[str, str]: ...


class JiraCloudAdapter:
    """Sync httpx adapter for JIRA Cloud REST v3. Uses Basic auth (email:api_token)."""

    adapter_version = "jira_cloud_v3"
    _FIELDS = "summary,description,issuetype,status,labels"

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        timeout_seconds: int = 10,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        credentials = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._auth_header = f"Basic {credentials}"

    def fetch_story(self, jira_key: str) -> JiraStory | None:
        import httpx

        url = f"{self._base_url}/rest/api/3/issue/{jira_key}?fields={self._FIELDS}"
        try:
            response = httpx.get(
                url,
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
        except Exception:
            return None

        if response.status_code == 404:
            return None
        if not response.is_success:
            return None

        data = response.json()
        fields = data.get("fields", {})
        description_raw = fields.get("description") or ""
        description_text = (
            _adf_to_text(description_raw) if isinstance(description_raw, dict) else description_raw
        )
        return JiraStory(
            jira_key=data.get("key", jira_key),
            summary=fields.get("summary") or "",
            description=description_text,
            acceptance_criteria=_extract_acceptance_criteria(fields),
            story_type=(fields.get("issuetype") or {}).get("name", ""),
            status=(fields.get("status") or {}).get("name", ""),
            labels=fields.get("labels") or [],
            fetched_at=datetime.now(UTC),
        )

    def health(self) -> dict[str, str]:
        import httpx

        try:
            response = httpx.get(
                f"{self._base_url}/rest/api/3/myself",
                headers={"Authorization": self._auth_header, "Accept": "application/json"},
                timeout=5,
            )
            return {"status": "ok" if response.is_success else "degraded"}
        except Exception as exc:
            return {"status": "unavailable", "error": str(exc)}


class StubJiraAdapter:
    """Returns a fixed JiraStory for any key. Deterministic for tests."""

    adapter_version = "stub"

    def __init__(self, story: JiraStory | None = None) -> None:
        self._story = story

    def fetch_story(self, jira_key: str) -> JiraStory | None:
        if self._story is not None:
            return self._story
        return JiraStory(
            jira_key=jira_key,
            summary=f"Stub story for {jira_key}",
            description="This is a stub description.",
            acceptance_criteria=[
                JiraAcceptanceCriterion(index=0, text="User can log in with valid credentials"),
                JiraAcceptanceCriterion(index=1, text="User sees error on invalid credentials"),
            ],
            story_type="Story",
            status="In Progress",
            labels=["stub"],
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def health(self) -> dict[str, str]:
        return {"status": "ok"}


class NullJiraAdapter:
    """No-op adapter — used when jira.enabled=False."""

    adapter_version = "null"

    def fetch_story(self, jira_key: str) -> JiraStory | None:
        return None

    def health(self) -> dict[str, str]:
        return {"status": "disabled"}
