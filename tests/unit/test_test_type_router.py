"""Unit tests for TestTypeRouter."""

import pytest

from totalrecall.testgen.models import ReformulatedIntent, TestType
from totalrecall.testgen.routing.router import TestTypeRouter, _DEFAULT_TEST_TYPES


def _make_intent(test_types: list[TestType]) -> ReformulatedIntent:
    return ReformulatedIntent(
        intent_summary="Generate tests",
        test_types=test_types,
        raw_prompt="test the login page",
    )


class _MockRequest:
    def __init__(self, test_types=None):
        self.test_types = test_types


class TestTestTypeRouter:
    def test_request_test_types_take_priority_over_intent(self):
        router = TestTypeRouter()
        intent = _make_intent([TestType.API])
        request = _MockRequest(test_types=[TestType.REGRESSION])
        result = router.route(intent, request)
        assert result == [TestType.REGRESSION]

    def test_intent_test_types_used_when_request_has_none(self):
        router = TestTypeRouter()
        intent = _make_intent([TestType.NEGATIVE, TestType.EDGE_CASE])
        request = _MockRequest(test_types=None)
        result = router.route(intent, request)
        assert result == [TestType.NEGATIVE, TestType.EDGE_CASE]

    def test_defaults_used_when_both_none(self):
        router = TestTypeRouter()
        request = _MockRequest(test_types=None)
        result = router.route(None, request)
        assert result == list(_DEFAULT_TEST_TYPES)

    def test_defaults_used_when_intent_has_empty_test_types(self):
        router = TestTypeRouter()
        intent = _make_intent([])
        request = _MockRequest(test_types=None)
        result = router.route(intent, request)
        assert result == list(_DEFAULT_TEST_TYPES)

    def test_request_empty_list_falls_through_to_intent(self):
        router = TestTypeRouter()
        intent = _make_intent([TestType.API])
        request = _MockRequest(test_types=[])
        result = router.route(intent, request)
        # Empty list is falsy, so falls through to intent
        assert result == [TestType.API]

    def test_all_five_test_types_supported(self):
        router = TestTypeRouter()
        all_types = list(TestType)
        request = _MockRequest(test_types=all_types)
        result = router.route(None, request)
        assert set(result) == set(all_types)

    def test_default_types_are_functional_negative_edge_case(self):
        assert TestType.FUNCTIONAL in _DEFAULT_TEST_TYPES
        assert TestType.NEGATIVE in _DEFAULT_TEST_TYPES
        assert TestType.EDGE_CASE in _DEFAULT_TEST_TYPES
