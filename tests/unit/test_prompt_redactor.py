"""Unit tests for prompt message redaction."""

from totalrecall.prompts.redactor import redact_messages
from totalrecall.providers.models import ProviderMessage, ProviderRole


def _msg(role: ProviderRole, content: str) -> ProviderMessage:
    return ProviderMessage(role=role, content=content)


def test_user_message_with_secret_is_redacted() -> None:
    messages = [
        _msg(ProviderRole.SYSTEM, "You are a code generator."),
        _msg(ProviderRole.USER, 'Generate a page. API_KEY = "sk-supersecret12345678"'),
    ]
    result, warnings = redact_messages(messages)

    assert "sk-supersecret12345678" not in result[1].content
    assert "[REDACTED]" in result[1].content
    assert len(warnings) > 0


def test_system_message_is_not_redacted() -> None:
    system_content = 'System prompt with api_key = "some-secret-value-here"'
    messages = [_msg(ProviderRole.SYSTEM, system_content)]
    result, warnings = redact_messages(messages)

    assert result[0].content == system_content
    assert warnings == []


def test_assistant_message_is_not_redacted() -> None:
    content = 'token = "sk-' + "A" * 25 + '"'
    messages = [_msg(ProviderRole.ASSISTANT, content)]
    result, warnings = redact_messages(messages)

    assert result[0].content == content
    assert warnings == []


def test_clean_user_message_passes_through_unchanged() -> None:
    content = "Generate a page object for the login route."
    messages = [_msg(ProviderRole.USER, content)]
    result, warnings = redact_messages(messages)

    assert result[0].content == content
    assert warnings == []


def test_message_count_is_preserved() -> None:
    messages = [
        _msg(ProviderRole.SYSTEM, "System prompt."),
        _msg(ProviderRole.USER, "User request."),
        _msg(ProviderRole.ASSISTANT, "Assistant response."),
    ]
    result, _ = redact_messages(messages)

    assert len(result) == 3


def test_roles_are_preserved() -> None:
    messages = [
        _msg(ProviderRole.SYSTEM, "S"),
        _msg(ProviderRole.USER, "U"),
        _msg(ProviderRole.ASSISTANT, "A"),
    ]
    result, _ = redact_messages(messages)

    assert result[0].role == ProviderRole.SYSTEM
    assert result[1].role == ProviderRole.USER
    assert result[2].role == ProviderRole.ASSISTANT


def test_empty_message_list_returns_empty() -> None:
    result, warnings = redact_messages([])
    assert result == []
    assert warnings == []
