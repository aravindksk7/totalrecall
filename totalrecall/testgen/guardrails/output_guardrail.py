"""Output guardrail: validates LLM raw text after generation, before normalization."""

import json
import re
from typing import Protocol, runtime_checkable

from totalrecall.testgen.guardrails.models import (
    GuardrailResult,
    GuardrailViolation,
    GuardrailViolationCode,
)

_SQL_INJECTION_RE = re.compile(
    r"(DROP\s+TABLE|DELETE\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|TRUNCATE\s+TABLE|ALTER\s+TABLE)",
    re.IGNORECASE,
)

_PII_RE = re.compile(
    r"(\b\d{3}-\d{2}-\d{4}\b"
    r"|\b4[0-9]{12}(?:[0-9]{3})?\b"
    r"|\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b)",
)

_ALLOWED_TOP_KEYS = {
    "story_summary", "assumptions", "test_cases", "traceability_matrix",
    "coverage_summary", "artifacts",
}


@runtime_checkable
class OutputGuardrailAdapter(Protocol):
    adapter_version: str

    def check(self, raw_text: str) -> GuardrailResult: ...


class RuleBasedOutputGuardrail:
    """Checks raw LLM output for JSON validity, SQL injection, PII, and schema violations."""

    adapter_version = "rule_based"

    def check(self, raw_text: str) -> GuardrailResult:
        violations: list[GuardrailViolation] = []

        try:
            data = json.loads(raw_text)
        except (json.JSONDecodeError, ValueError):
            violations.append(
                GuardrailViolation(
                    code=GuardrailViolationCode.UNSAFE_CONTENT,
                    message="LLM response is not valid JSON",
                )
            )
            return GuardrailResult(passed=False, violations=violations)

        if isinstance(data, dict):
            unknown_keys = set(data.keys()) - _ALLOWED_TOP_KEYS
            if unknown_keys:
                violations.append(
                    GuardrailViolation(
                        code=GuardrailViolationCode.UNSAFE_CONTENT,
                        message=f"Response contains unexpected top-level keys: {sorted(unknown_keys)}",
                    )
                )

        text_content = json.dumps(data)
        if _SQL_INJECTION_RE.search(text_content):
            violations.append(
                GuardrailViolation(
                    code=GuardrailViolationCode.UNSAFE_CONTENT,
                    message="Response contains SQL injection patterns",
                )
            )

        if _PII_RE.search(text_content):
            violations.append(
                GuardrailViolation(
                    code=GuardrailViolationCode.UNSAFE_CONTENT,
                    message="Response contains potential PII",
                )
            )

        return GuardrailResult(passed=len(violations) == 0, violations=violations)


class NullOutputGuardrail:
    """Always passes — used when guardrails.output_enabled=False."""

    adapter_version = "null"

    def check(self, raw_text: str) -> GuardrailResult:
        return GuardrailResult(passed=True)
