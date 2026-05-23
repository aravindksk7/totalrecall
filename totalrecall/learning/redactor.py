"""Regex-based secret redaction for learning discovery excerpts."""

import re

_REPLACEMENT = "[REDACTED]"

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r'(?i)(?:api[_-]?key|secret|password|token|credential|auth)\s*[=:]\s*["\']([^"\']{8,})["\']'
    ),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{60,}={0,2}(?![A-Za-z0-9+/=])"),
]


def redact(text: str) -> tuple[str, list[str]]:
    """Return (redacted_text, warning_messages). Warnings name which pattern fired."""
    warnings: list[str] = []
    for pattern in _PATTERNS:
        if pattern.search(text):
            text = pattern.sub(_REPLACEMENT, text)
            warnings.append(f"Redacted content matching: {pattern.pattern[:60]}")
    return text, warnings
