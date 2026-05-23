"""Unit tests for KeywordReformulator and StubReformulator."""

import pytest

from totalrecall.testgen.models import ReformulatedIntent, TestType
from totalrecall.testgen.reformulator import KeywordReformulator, StubReformulator


class TestKeywordReformulator:
    def setup_method(self):
        self.reformulator = KeywordReformulator()

    def test_extracts_jira_key_from_prompt(self):
        intent = self.reformulator.reformulate(
            "Generate test cases for PROJ-42 login flow", None, None
        )
        assert intent.jira_key == "PROJ-42"

    def test_uses_explicit_jira_key_over_prompt(self):
        intent = self.reformulator.reformulate(
            "Generate test cases for PROJ-42 login flow", "SCRUM-99", None
        )
        assert intent.jira_key == "SCRUM-99"

    def test_no_jira_key_returns_none(self):
        intent = self.reformulator.reformulate("Generate tests for login", None, None)
        assert intent.jira_key is None

    def test_infers_functional_from_keywords(self):
        intent = self.reformulator.reformulate("Happy path functional tests", None, None)
        assert TestType.FUNCTIONAL in intent.test_types

    def test_infers_negative_from_keywords(self):
        intent = self.reformulator.reformulate("Generate negative and invalid input tests", None, None)
        assert TestType.NEGATIVE in intent.test_types

    def test_infers_edge_case_from_keywords(self):
        intent = self.reformulator.reformulate("Test edge cases and boundary values", None, None)
        assert TestType.EDGE_CASE in intent.test_types

    def test_infers_api_from_keywords(self):
        intent = self.reformulator.reformulate("API endpoint tests for rest request", None, None)
        assert TestType.API in intent.test_types

    def test_infers_regression_from_keywords(self):
        intent = self.reformulator.reformulate("Regression smoke tests", None, None)
        assert TestType.REGRESSION in intent.test_types

    def test_defaults_to_three_types_when_no_keywords(self):
        intent = self.reformulator.reformulate("Generate tests", None, None)
        assert intent.test_types == [TestType.FUNCTIONAL, TestType.NEGATIVE, TestType.EDGE_CASE]

    def test_uses_explicit_test_types(self):
        intent = self.reformulator.reformulate(
            "Generate tests", None, [TestType.API, TestType.REGRESSION]
        )
        assert intent.test_types == [TestType.API, TestType.REGRESSION]

    def test_intent_summary_is_first_line(self):
        intent = self.reformulator.reformulate("Short prompt", None, None)
        assert intent.intent_summary == "Short prompt"

    def test_intent_summary_truncated_at_200(self):
        long_prompt = "x" * 300
        intent = self.reformulator.reformulate(long_prompt, None, None)
        assert len(intent.intent_summary) == 200

    def test_raw_prompt_preserved(self):
        prompt = "Generate tests for PROJ-1"
        intent = self.reformulator.reformulate(prompt, None, None)
        assert intent.raw_prompt == prompt

    def test_adapter_version(self):
        assert self.reformulator.adapter_version == "keyword"

    def test_output_is_reformulated_intent(self):
        intent = self.reformulator.reformulate("Some prompt", None, None)
        assert isinstance(intent, ReformulatedIntent)

    def test_confidence_is_float_in_range(self):
        intent = self.reformulator.reformulate("Some prompt", None, None)
        assert 0.0 <= intent.confidence <= 1.0


class TestStubReformulator:
    def test_returns_fixed_intent_when_provided(self):
        fixed = ReformulatedIntent(
            jira_key="FIXED-1",
            intent_summary="Fixed summary",
            test_types=[TestType.API],
            raw_prompt="original",
        )
        stub = StubReformulator(fixed_intent=fixed)
        result = stub.reformulate("anything", None, None)
        assert result is fixed

    def test_returns_default_when_no_fixed(self):
        stub = StubReformulator()
        result = stub.reformulate("some prompt", "KEY-1", [TestType.REGRESSION])
        assert result.jira_key == "KEY-1"
        assert result.test_types == [TestType.REGRESSION]
        assert result.raw_prompt == "some prompt"

    def test_default_functional_when_no_test_types(self):
        stub = StubReformulator()
        result = stub.reformulate("some prompt", None, None)
        assert result.test_types == [TestType.FUNCTIONAL]

    def test_adapter_version(self):
        assert StubReformulator().adapter_version == "stub"
