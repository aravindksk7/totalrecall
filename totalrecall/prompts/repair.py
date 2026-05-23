"""Repair prompt builder: extends a conversation with a fix-it turn after validation failure."""

from totalrecall.generation.models import ValidationDiagnostic
from totalrecall.providers.models import ProviderMessage, ProviderRole


def build_repair_messages(
    original_messages: list[ProviderMessage],
    original_raw_text: str,
    diagnostics: list[ValidationDiagnostic],
) -> list[ProviderMessage]:
    """Append an assistant turn and a repair-request user turn to the original conversation."""
    diagnostic_lines = "\n".join(
        f"- [{d.severity}] {d.code}: {d.message}" for d in diagnostics
    )
    repair_content = (
        "The following validation errors were found in your previous response:\n\n"
        f"{diagnostic_lines}\n\n"
        "Please fix these issues and respond again with a corrected JSON artifact object. "
        "Do not include any text outside the JSON object."
    )
    return [
        *original_messages,
        ProviderMessage(role=ProviderRole.ASSISTANT, content=original_raw_text or "{}"),
        ProviderMessage(role=ProviderRole.USER, content=repair_content),
    ]
