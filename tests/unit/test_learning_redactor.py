"""Unit tests for the learning secret redactor."""

from totalrecall.learning.redactor import redact


def test_redact_api_key_assignment() -> None:
    text = 'api_key = "sk-abcdefghijklmnopqrst"'
    result, warnings = redact(text)
    assert "[REDACTED]" in result
    assert len(warnings) > 0


def test_redact_password_assignment_double_quotes() -> None:
    text = 'password = "supersecret123!"'
    result, warnings = redact(text)
    assert "[REDACTED]" in result
    assert "password" not in result.lower() or "[REDACTED]" in result


def test_redact_secret_colon_syntax() -> None:
    text = "secret: 'my-long-secret-value-here'"
    result, warnings = redact(text)
    assert "[REDACTED]" in result
    assert len(warnings) > 0


def test_redact_openai_key_pattern() -> None:
    text = "token = sk-" + "A" * 25
    result, warnings = redact(text)
    assert "[REDACTED]" in result
    assert len(warnings) > 0


def test_redact_github_pat() -> None:
    text = "ghp_" + "A" * 36
    result, warnings = redact(text)
    assert "[REDACTED]" in result
    assert len(warnings) > 0


def test_redact_base64_secret() -> None:
    # 64+ character base64-like string — matches the long base64 pattern
    b64 = "A" * 64
    result, warnings = redact(b64)
    assert "[REDACTED]" in result
    assert len(warnings) > 0


def test_no_redaction_when_no_secrets() -> None:
    text = "class LoginPage:\n    def goto(self): self.page.goto('/login')"
    result, warnings = redact(text)
    assert result == text
    assert warnings == []


def test_redact_returns_warning_with_pattern_info() -> None:
    text = 'api_key = "my-secret-api-value"'
    _, warnings = redact(text)
    assert any("Redacted content" in w for w in warnings)


def test_redact_multiple_patterns_in_one_text() -> None:
    text = 'token = "abcdefgh12345678" and key = "zyxwvutsrqponm"'
    result, warnings = redact(text)
    assert "[REDACTED]" in result


def test_redact_short_value_not_redacted() -> None:
    # Values under 8 chars in the key=value pattern should NOT be redacted
    text = 'api_key = "short"'
    result, warnings = redact(text)
    # "short" is 5 chars — below the 8-char threshold
    assert "[REDACTED]" not in result
    assert warnings == []


def test_redact_is_case_insensitive_for_key_names() -> None:
    text = 'API_KEY = "longsecretvalue123"'
    result, warnings = redact(text)
    assert "[REDACTED]" in result
    assert len(warnings) > 0
