"""Unit tests for RuleBasedInputGuardrail."""

import pytest

from totalrecall.generation.models import (
    Framework,
    GenerationRequest,
    GenerationScope,
    GenerationTarget,
    Language,
)
from totalrecall.testgen.guardrails.input_guardrail import (
    NullInputGuardrail,
    RuleBasedInputGuardrail,
    StubInputGuardrail,
)
from totalrecall.testgen.guardrails.models import GuardrailViolationCode


def _make_request(**overrides) -> GenerationRequest:
    base = {
        "tenant_id": "t1",
        "application_id": "app1",
        "prompt": "Generate test cases for the login form",
        "target": {"language": "python", "framework": "pytest"},
        "scope": {"domain": "login"},
    }
    base.update(overrides)
    return GenerationRequest(**base)


class TestRuleBasedInputGuardrail:
    def setup_method(self):
        self.guardrail = RuleBasedInputGuardrail()

    def test_valid_request_passes(self):
        result = self.guardrail.check(_make_request(), None)
        assert result.passed is True
        assert result.violations == []

    def test_valid_jira_key_passes(self):
        result = self.guardrail.check(_make_request(jira_key="PROJ-123"), None)
        assert result.passed is True

    def test_malformed_jira_key_fails(self):
        result = self.guardrail.check(_make_request(jira_key="proj-123"), None)
        assert result.passed is False
        assert any(v.code == GuardrailViolationCode.JIRA_KEY_FORMAT for v in result.violations)

    def test_numeric_only_jira_key_fails(self):
        result = self.guardrail.check(_make_request(jira_key="123-456"), None)
        assert result.passed is False

    def test_non_qa_prompt_flagged(self):
        result = self.guardrail.check(
            _make_request(prompt="Tell me a joke about programming"), None
        )
        assert result.passed is False
        assert any(v.code == GuardrailViolationCode.NOT_QA_DOMAIN for v in result.violations)

    def test_ssn_in_prompt_flagged(self):
        result = self.guardrail.check(
            _make_request(prompt="Test user login with SSN 123-45-6789"), None
        )
        assert result.passed is False
        assert any(v.code == GuardrailViolationCode.UNSAFE_CONTENT for v in result.violations)

    def test_email_in_prompt_flagged(self):
        result = self.guardrail.check(
            _make_request(prompt="Test login for user@example.com acceptance criteria"), None
        )
        assert result.passed is False
        assert any(v.code == GuardrailViolationCode.UNSAFE_CONTENT for v in result.violations)

    def test_multiple_violations_collected(self):
        result = self.guardrail.check(
            _make_request(jira_key="bad-key", prompt="Tell me a joke"), None
        )
        assert result.passed is False
        assert len(result.violations) >= 2

    def test_adapter_version(self):
        assert self.guardrail.adapter_version == "rule_based"


class TestNullInputGuardrail:
    def test_always_passes(self):
        guardrail = NullInputGuardrail()
        result = guardrail.check(_make_request(), None)
        assert result.passed is True
        assert result.violations == []

    def test_adapter_version(self):
        assert NullInputGuardrail().adapter_version == "null"


class TestStubInputGuardrail:
    def test_passes_by_default(self):
        stub = StubInputGuardrail()
        result = stub.check(_make_request(), None)
        assert result.passed is True

    def test_can_be_set_to_fail(self):
        from totalrecall.testgen.guardrails.models import GuardrailViolation
        violation = GuardrailViolation(
            code=GuardrailViolationCode.UNSAFE_CONTENT,
            message="stub violation",
        )
        stub = StubInputGuardrail(should_pass=False, violations=[violation])
        result = stub.check(_make_request(), None)
        assert result.passed is False
        assert len(result.violations) == 1
