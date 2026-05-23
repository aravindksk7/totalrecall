"""Unit tests for RuleBasedOutputGuardrail."""

import json

from totalrecall.testgen.guardrails.models import GuardrailViolationCode
from totalrecall.testgen.guardrails.output_guardrail import (
    NullOutputGuardrail,
    RuleBasedOutputGuardrail,
)


class TestRuleBasedOutputGuardrail:
    def setup_method(self):
        self.guardrail = RuleBasedOutputGuardrail()

    def _valid_pack(self) -> str:
        return json.dumps({
            "story_summary": "User login flow",
            "test_cases": [],
            "traceability_matrix": [],
            "coverage_summary": "All covered",
        })

    def test_valid_json_passes(self):
        result = self.guardrail.check(self._valid_pack())
        assert result.passed is True

    def test_malformed_json_blocked(self):
        result = self.guardrail.check("not-json{")
        assert result.passed is False
        assert any(v.code == GuardrailViolationCode.UNSAFE_CONTENT for v in result.violations)

    def test_sql_injection_in_test_step_blocked(self):
        payload = json.dumps({
            "story_summary": "Test",
            "test_cases": [{"steps": ["DROP TABLE users"]}],
        })
        result = self.guardrail.check(payload)
        assert result.passed is False
        assert any("SQL" in v.message for v in result.violations)

    def test_pii_email_blocked(self):
        payload = json.dumps({
            "story_summary": "Test login for admin@example.com",
            "test_cases": [],
        })
        result = self.guardrail.check(payload)
        assert result.passed is False
        assert any("PII" in v.message for v in result.violations)

    def test_unknown_top_level_key_blocked(self):
        payload = json.dumps({
            "story_summary": "Test",
            "test_cases": [],
            "malicious_key": "bad value",
        })
        result = self.guardrail.check(payload)
        assert result.passed is False

    def test_artifacts_key_allowed(self):
        payload = json.dumps({
            "artifacts": [
                {"path": "test.py", "artifact_type": "test_spec", "language": "python", "content": "pass"}
            ]
        })
        result = self.guardrail.check(payload)
        assert result.passed is True

    def test_adapter_version(self):
        assert self.guardrail.adapter_version == "rule_based"


class TestNullOutputGuardrail:
    def test_always_passes(self):
        guardrail = NullOutputGuardrail()
        result = guardrail.check("anything goes here")
        assert result.passed is True

    def test_adapter_version(self):
        assert NullOutputGuardrail().adapter_version == "null"
