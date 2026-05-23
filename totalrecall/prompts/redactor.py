"""Prompt redaction: strip secrets from user messages before dispatch to a provider."""

from totalrecall.learning.redactor import redact
from totalrecall.providers.models import ProviderMessage, ProviderRole


def redact_messages(messages: list[ProviderMessage]) -> tuple[list[ProviderMessage], list[str]]:
    """Return (redacted_messages, all_warnings).

    Only USER messages are redacted; SYSTEM and ASSISTANT messages are passed through
    unchanged because they are constructed internally and do not contain user-supplied data.
    """
    redacted: list[ProviderMessage] = []
    all_warnings: list[str] = []

    for msg in messages:
        if msg.role == ProviderRole.USER:
            clean_content, warnings = redact(msg.content)
            all_warnings.extend(warnings)
            redacted.append(ProviderMessage(role=msg.role, content=clean_content))
        else:
            redacted.append(msg)

    return redacted, all_warnings
