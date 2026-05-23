"""Unit tests for ToneChecker adapters."""

from totalrecall.testgen.tone.checker import LLMToneChecker, NullToneChecker


class TestNullToneChecker:
    def test_returns_original_text_unchanged(self):
        checker = NullToneChecker()
        text = '{"test_cases": []}'
        result_text, changed = checker.refine(text, "req-1")
        assert result_text == text
        assert changed is False

    def test_was_changed_is_always_false(self):
        checker = NullToneChecker()
        _, changed = checker.refine("any text", "req-2")
        assert changed is False


class TestLLMToneChecker:
    def test_returns_stub_provider_output(self):
        class _StubGateway:
            def generate(self, req):
                class _Resp:
                    raw_text = '{"test_cases": [{"title": "Refined title"}]}'
                return _Resp()

        checker = LLMToneChecker(gateway=_StubGateway())
        text = '{"test_cases": [{"title": "original title"}]}'
        result_text, changed = checker.refine(text, "req-1")
        assert "Refined title" in result_text
        assert changed is True

    def test_returns_original_on_gateway_exception(self):
        class _FailingGateway:
            def generate(self, req):
                raise RuntimeError("provider down")

        checker = LLMToneChecker(gateway=_FailingGateway())
        text = "original output"
        result_text, changed = checker.refine(text, "req-1")
        assert result_text == text
        assert changed is False

    def test_changed_false_when_output_identical(self):
        original = '{"test_cases": []}'

        class _IdenticalGateway:
            def generate(self, req):
                class _Resp:
                    raw_text = original
                return _Resp()

        checker = LLMToneChecker(gateway=_IdenticalGateway())
        _, changed = checker.refine(original, "req-1")
        assert changed is False
