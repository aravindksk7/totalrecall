"""Reformulator adapters: convert free-text user prompt into a structured ReformulatedIntent."""

import json
import re
import uuid
from typing import Protocol, runtime_checkable

from totalrecall.providers.gateway import ProviderGateway
from totalrecall.providers.models import ProviderConfig, ProviderMessage, ProviderRequest, ProviderRole
from totalrecall.testgen.models import ReformulatedIntent, TestType

_JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")

_KEYWORD_MAP: dict[TestType, list[str]] = {
    TestType.FUNCTIONAL: ["functional", "happy path", "positive", "valid"],
    TestType.NEGATIVE: ["negative", "invalid", "error", "failure", "unhappy"],
    TestType.EDGE_CASE: ["edge", "boundary", "corner", "limit"],
    TestType.API: ["api", "endpoint", "rest", "request", "response", "http"],
    TestType.REGRESSION: ["regression", "smoke", "re-test", "existing"],
}

_REFORMULATOR_SYSTEM_PROMPT = (
    "You are a QA test planning assistant. Extract structured information from the user's request "
    "and return ONLY a JSON object with these fields:\n"
    '  "jira_key": string or null (JIRA issue key like PROJECT-123),\n'
    '  "intent_summary": string (one sentence describing what to test),\n'
    '  "test_types": array of strings from [functional, negative, edge_case, api, regression],\n'
    '  "output_format": "test_case_pack",\n'
    '  "confidence": float 0.0-1.0\n'
    "Return ONLY the JSON object, no markdown."
)


@runtime_checkable
class ReformulatorAdapter(Protocol):
    adapter_version: str

    def reformulate(
        self,
        prompt: str,
        jira_key: str | None,
        test_types: list[TestType] | None,
    ) -> ReformulatedIntent: ...


class KeywordReformulator:
    """Deterministic keyword-based reformulator — no LLM call."""

    adapter_version = "keyword"

    def reformulate(
        self,
        prompt: str,
        jira_key: str | None,
        test_types: list[TestType] | None,
    ) -> ReformulatedIntent:
        resolved_key = jira_key or self._extract_jira_key(prompt)
        resolved_types = list(test_types) if test_types else self._infer_types(prompt)
        return ReformulatedIntent(
            jira_key=resolved_key,
            intent_summary=self._summarize(prompt),
            test_types=resolved_types,
            output_format="test_case_pack",
            raw_prompt=prompt,
            confidence=0.7,
        )

    def _extract_jira_key(self, text: str) -> str | None:
        m = _JIRA_KEY_RE.search(text)
        return m.group(1) if m else None

    def _infer_types(self, text: str) -> list[TestType]:
        lower = text.lower()
        matched = [t for t, kws in _KEYWORD_MAP.items() if any(kw in lower for kw in kws)]
        return matched if matched else [TestType.FUNCTIONAL, TestType.NEGATIVE, TestType.EDGE_CASE]

    def _summarize(self, prompt: str) -> str:
        first_line = prompt.strip().splitlines()[0]
        return first_line[:200] if len(first_line) > 200 else first_line


class LLMReformulator:
    """LLM-backed reformulator via ProviderGateway."""

    adapter_version = "llm"

    def __init__(self, gateway: ProviderGateway, provider_config: ProviderConfig) -> None:
        self._gateway = gateway
        self._provider_config = provider_config

    def reformulate(
        self,
        prompt: str,
        jira_key: str | None,
        test_types: list[TestType] | None,
    ) -> ReformulatedIntent:
        user_content = prompt
        if jira_key:
            user_content = f"JIRA key: {jira_key}\n\n{prompt}"
        if test_types:
            user_content += f"\n\nRequested test types: {', '.join(test_types)}"

        request = ProviderRequest(
            request_id=str(uuid.uuid4()),
            tenant_id="__system__",
            messages=[
                ProviderMessage(role=ProviderRole.SYSTEM, content=_REFORMULATOR_SYSTEM_PROMPT),
                ProviderMessage(role=ProviderRole.USER, content=user_content),
            ],
            config=self._provider_config,
        )
        try:
            response = self._gateway.generate(request)
            data = json.loads(response.raw_text)
            raw_types = data.get("test_types") or []
            parsed_types: list[TestType] = []
            for t in raw_types:
                try:
                    parsed_types.append(TestType(t))
                except ValueError:
                    pass
            return ReformulatedIntent(
                jira_key=data.get("jira_key") or jira_key,
                intent_summary=data.get("intent_summary") or prompt[:200],
                test_types=parsed_types or (list(test_types) if test_types else []),
                output_format=data.get("output_format", "test_case_pack"),
                raw_prompt=prompt,
                confidence=float(data.get("confidence", 0.9)),
            )
        except Exception:
            # Fall back to keyword reformulation on any error
            return KeywordReformulator().reformulate(prompt, jira_key, test_types)


class StubReformulator:
    """Deterministic stub for tests — always returns a fixed intent."""

    adapter_version = "stub"

    def __init__(self, fixed_intent: ReformulatedIntent | None = None) -> None:
        self._fixed = fixed_intent

    def reformulate(
        self,
        prompt: str,
        jira_key: str | None,
        test_types: list[TestType] | None,
    ) -> ReformulatedIntent:
        if self._fixed is not None:
            return self._fixed
        return ReformulatedIntent(
            jira_key=jira_key,
            intent_summary="Stub intent summary",
            test_types=list(test_types) if test_types else [TestType.FUNCTIONAL],
            output_format="test_case_pack",
            raw_prompt=prompt,
            confidence=1.0,
        )
