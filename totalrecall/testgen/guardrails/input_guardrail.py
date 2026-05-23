"""Input guardrail: validates a GenerationRequest is QA/JIRA-safe before any LLM calls."""

import re
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from totalrecall.testgen.guardrails.models import (
    GuardrailResult,
    GuardrailViolation,
    GuardrailViolationCode,
)

if TYPE_CHECKING:
    from totalrecall.generation.models import GenerationRequest
    from totalrecall.testgen.models import ReformulatedIntent

_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")

_PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),           # SSN
    re.compile(r"\b4[0-9]{12}(?:[0-9]{3})?\b"),      # Visa card
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"),  # email
]

_QA_KEYWORDS = {
    "test", "spec", "scenario", "case", "validate", "verify", "check",
    "assert", "jira", "story", "acceptance", "criteria", "functional",
    "negative", "edge", "api", "regression", "login", "logout", "user",
    "form", "page", "flow", "endpoint",
}


@runtime_checkable
class InputGuardrailAdapter(Protocol):
    adapter_version: str

    def check(
        self,
        request: "GenerationRequest",
        intent: "ReformulatedIntent | None",
    ) -> GuardrailResult: ...


class RuleBasedInputGuardrail:
    """Validates JIRA key format, non-empty prompt, QA domain, and no PII in prompt."""

    adapter_version = "rule_based"

    def check(
        self,
        request: "GenerationRequest",
        intent: "ReformulatedIntent | None",
    ) -> GuardrailResult:
        violations: list[GuardrailViolation] = []

        if request.jira_key and not _JIRA_KEY_RE.match(request.jira_key):
            violations.append(
                GuardrailViolation(
                    code=GuardrailViolationCode.JIRA_KEY_FORMAT,
                    message=f"JIRA key '{request.jira_key}' does not match PROJECT-NNN format",
                    field="jira_key",
                )
            )

        prompt_lower = request.prompt.lower()
        if not any(kw in prompt_lower for kw in _QA_KEYWORDS):
            violations.append(
                GuardrailViolation(
                    code=GuardrailViolationCode.NOT_QA_DOMAIN,
                    message="Prompt does not appear to be a QA test generation request",
                    field="prompt",
                )
            )

        for pattern in _PII_PATTERNS:
            if pattern.search(request.prompt):
                violations.append(
                    GuardrailViolation(
                        code=GuardrailViolationCode.UNSAFE_CONTENT,
                        message="Prompt contains potential PII — remove before submitting",
                        field="prompt",
                    )
                )
                break

        return GuardrailResult(passed=len(violations) == 0, violations=violations)


class NullInputGuardrail:
    """Always passes — used when guardrails.input_enabled=False."""

    adapter_version = "null"

    def check(
        self,
        request: "GenerationRequest",
        intent: "ReformulatedIntent | None",
    ) -> GuardrailResult:
        return GuardrailResult(passed=True)


class StubInputGuardrail:
    """Configurable pass/fail for tests."""

    adapter_version = "stub"

    def __init__(self, *, should_pass: bool = True, violations: list[GuardrailViolation] | None = None) -> None:
        self._should_pass = should_pass
        self._violations = violations or []

    def check(
        self,
        request: "GenerationRequest",
        intent: "ReformulatedIntent | None",
    ) -> GuardrailResult:
        return GuardrailResult(passed=self._should_pass, violations=self._violations)
