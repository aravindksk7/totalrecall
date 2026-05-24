"""Unit tests for KeywordReformulator, StubReformulator, and LLMReformulator."""

import json

import pytest

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.providers.gateway import ProviderGateway
from totalrecall.providers.models import ProviderConfig
from totalrecall.providers.stub.provider import StubProvider
from totalrecall.testgen.models import ReformulatedIntent, TestType
from totalrecall.testgen.reformulator import KeywordReformulator, LLMReformulator, StubReformulator
from totalrecall.testgen.reformulator_factory import build_reformulator
from totalrecall.testgen.tone.factory import build_tone_checker


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


# --- LLMReformulator ---


def _make_llm_reformulator(fixed_response: dict | None = None) -> LLMReformulator:
    gateway = ProviderGateway(providers={"stub": StubProvider(fixed_response=fixed_response)})
    config = ProviderConfig(provider_id="stub", model="stub", max_output_tokens=512)
    return LLMReformulator(gateway=gateway, provider_config=config)


class TestLLMReformulator:
    def test_adapter_version(self):
        assert _make_llm_reformulator().adapter_version == "llm"

    def test_returns_reformulated_intent_from_valid_json(self):
        payload = {
            "intent_summary": "Test login page",
            "test_types": ["functional", "negative"],
            "output_format": "test_case_pack",
            "confidence": 0.95,
        }
        reformulator = _make_llm_reformulator(fixed_response=payload)
        result = reformulator.reformulate("Test the login page", None, None)
        assert isinstance(result, ReformulatedIntent)
        assert result.intent_summary == "Test login page"
        assert TestType.FUNCTIONAL in result.test_types
        assert TestType.NEGATIVE in result.test_types

    def test_prepends_jira_key_to_user_content(self):
        payload = {
            "intent_summary": "Login tests",
            "test_types": ["functional"],
            "confidence": 0.9,
        }
        reformulator = _make_llm_reformulator(fixed_response=payload)
        result = reformulator.reformulate("Test the login", "AUTH-1", None)
        assert result.jira_key == "AUTH-1"

    def test_appends_test_types_to_user_content(self):
        payload = {
            "intent_summary": "API tests",
            "test_types": ["api"],
            "confidence": 0.9,
        }
        reformulator = _make_llm_reformulator(fixed_response=payload)
        result = reformulator.reformulate("Test the API", None, [TestType.API])
        assert TestType.API in result.test_types

    def test_falls_back_to_keyword_on_provider_error(self):
        gateway = ProviderGateway(providers={"stub": StubProvider()})
        # Use a non-existent provider to trigger ProviderNotFoundError → fallback
        config = ProviderConfig(provider_id="nonexistent", model="test", max_output_tokens=512)
        reformulator = LLMReformulator(gateway=gateway, provider_config=config)
        result = reformulator.reformulate("Generate functional tests", None, None)
        assert isinstance(result, ReformulatedIntent)

    def test_skips_invalid_test_type_values(self):
        payload = {
            "intent_summary": "Login tests",
            "test_types": ["functional", "not_a_real_type"],
            "confidence": 0.9,
        }
        reformulator = _make_llm_reformulator(fixed_response=payload)
        result = reformulator.reformulate("Test login", None, None)
        assert TestType.FUNCTIONAL in result.test_types
        assert "not_a_real_type" not in [str(t) for t in result.test_types]


# --- build_reformulator factory ---


class TestBuildReformulator:
    def test_builds_keyword_reformulator_by_default(self):
        flags = ConfigFeatureFlagProvider({})
        result = build_reformulator(flags)
        assert result.adapter_version == "keyword"

    def test_builds_stub_reformulator(self):
        flags = ConfigFeatureFlagProvider({"reformulator.adapter": "stub"})
        result = build_reformulator(flags)
        assert result.adapter_version == "stub"

    def test_builds_llm_reformulator_when_gateway_provided(self):
        flags = ConfigFeatureFlagProvider({"reformulator.adapter": "llm"})
        gateway = ProviderGateway(providers={"stub": StubProvider()})
        result = build_reformulator(flags, gateway=gateway)
        assert result.adapter_version == "llm"

    def test_falls_back_to_keyword_when_llm_but_no_gateway(self):
        flags = ConfigFeatureFlagProvider({"reformulator.adapter": "llm"})
        result = build_reformulator(flags, gateway=None)
        assert result.adapter_version == "keyword"


# --- build_tone_checker factory ---


class TestBuildToneChecker:
    def test_returns_null_when_disabled(self):
        from totalrecall.testgen.tone.checker import NullToneChecker

        flags = ConfigFeatureFlagProvider({"tone_check.enabled": False})
        checker = build_tone_checker(flags)
        assert isinstance(checker, NullToneChecker)

    def test_returns_null_when_enabled_but_no_gateway(self):
        from totalrecall.testgen.tone.checker import NullToneChecker

        flags = ConfigFeatureFlagProvider({"tone_check.enabled": True})
        checker = build_tone_checker(flags, gateway=None)
        assert isinstance(checker, NullToneChecker)

    def test_returns_llm_when_enabled_with_gateway(self):
        from totalrecall.testgen.tone.checker import LLMToneChecker

        flags = ConfigFeatureFlagProvider({"tone_check.enabled": True})
        gateway = ProviderGateway(providers={"stub": StubProvider()})
        checker = build_tone_checker(flags, gateway=gateway)
        assert isinstance(checker, LLMToneChecker)
