"""Unit tests for the repair prompt builder."""

from totalrecall.generation.models import ValidationDiagnostic, ValidationStatus
from totalrecall.prompts.repair import build_repair_messages
from totalrecall.providers.models import ProviderMessage, ProviderRole


def _messages() -> list[ProviderMessage]:
    return [
        ProviderMessage(role=ProviderRole.SYSTEM, content="You are a code generator."),
        ProviderMessage(role=ProviderRole.USER, content="Generate a page object."),
    ]


def _diagnostics() -> list[ValidationDiagnostic]:
    return [
        ValidationDiagnostic(
            code="POM_CLASS_MISSING",
            message="Page object must define a class",
            severity=ValidationStatus.FAILED,
        ),
    ]


def test_repair_appends_two_messages() -> None:
    result = build_repair_messages(_messages(), '{"artifacts": []}', _diagnostics())
    assert len(result) == 4


def test_repair_third_message_is_assistant_with_raw_text() -> None:
    raw = '{"artifacts": []}'
    result = build_repair_messages(_messages(), raw, _diagnostics())
    assert result[2].role == ProviderRole.ASSISTANT
    assert result[2].content == raw


def test_repair_fourth_message_is_user() -> None:
    result = build_repair_messages(_messages(), '{}', _diagnostics())
    assert result[3].role == ProviderRole.USER


def test_repair_user_message_contains_diagnostic_code() -> None:
    result = build_repair_messages(_messages(), '{}', _diagnostics())
    assert "POM_CLASS_MISSING" in result[3].content


def test_repair_user_message_contains_diagnostic_message() -> None:
    result = build_repair_messages(_messages(), '{}', _diagnostics())
    assert "Page object must define a class" in result[3].content


def test_repair_preserves_original_messages() -> None:
    originals = _messages()
    result = build_repair_messages(originals, '{}', _diagnostics())
    assert result[0] == originals[0]
    assert result[1] == originals[1]


def test_repair_empty_raw_text_falls_back_to_empty_object() -> None:
    result = build_repair_messages(_messages(), "", _diagnostics())
    assert result[2].content == "{}"


def test_repair_includes_all_diagnostics() -> None:
    diagnostics = [
        ValidationDiagnostic(
            code="POM_CLASS_MISSING",
            message="Must have a class",
            severity=ValidationStatus.FAILED,
        ),
        ValidationDiagnostic(
            code="CONSTRUCTOR_MISSING",
            message="Must have a constructor",
            severity=ValidationStatus.WARNING,
        ),
    ]
    result = build_repair_messages(_messages(), '{}', diagnostics)
    assert "POM_CLASS_MISSING" in result[3].content
    assert "CONSTRUCTOR_MISSING" in result[3].content
