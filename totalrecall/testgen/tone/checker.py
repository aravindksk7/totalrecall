"""Tone checker protocol, LLM implementation, and null adapter."""

from typing import Protocol, runtime_checkable

_TONE_SYSTEM_PROMPT = (
    "You are a QA writing coach. You will be given generated test case output. "
    "Rewrite it using professional, concise QA language: "
    "active voice, present tense, no filler phrases, no marketing language. "
    "Preserve all JSON structure and field values exactly — only improve wording inside "
    "string fields (title, steps, expected_result). "
    "Return only the revised JSON with no additional commentary."
)


@runtime_checkable
class ToneCheckAdapter(Protocol):
    def refine(self, raw_text: str, request_id: str) -> tuple[str, bool]: ...


class LLMToneChecker:
    """Calls the provider gateway to refine tone of the generated test case output."""

    def __init__(self, gateway) -> None:
        self._gateway = gateway

    def refine(self, raw_text: str, request_id: str) -> tuple[str, bool]:
        from totalrecall.providers.models import ProviderConfig, ProviderMessage, ProviderRequest, ProviderRole

        provider_request = ProviderRequest(
            request_id=f"{request_id}-tone",
            tenant_id="system",
            messages=[
                ProviderMessage(role=ProviderRole.SYSTEM, content=_TONE_SYSTEM_PROMPT),
                ProviderMessage(role=ProviderRole.USER, content=raw_text),
            ],
            config=ProviderConfig(
                provider_id="default",
                model="default",
                max_output_tokens=4096,
            ),
        )
        try:
            response = self._gateway.generate(provider_request)
            refined = response.raw_text.strip()
            changed = refined != raw_text.strip()
            return refined, changed
        except Exception:
            return raw_text, False


class NullToneChecker:
    """Returns the original text unchanged; used when tone_check.enabled=False."""

    def refine(self, raw_text: str, request_id: str) -> tuple[str, bool]:
        return raw_text, False
