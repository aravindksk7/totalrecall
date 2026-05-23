"""Deterministic stub provider for tests and CI — never calls a real LLM."""

import json

from totalrecall.providers.base import ProviderInterface
from totalrecall.providers.models import (
    ProviderFinishReason,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)

_DEFAULT_ARTIFACT = {
    "artifacts": [
        {
            "path": "pages/stub/stub.page.ts",
            "artifact_type": "page_object",
            "language": "typescript",
            "content": "// stub generated page object\nexport class StubPage {}",
        }
    ]
}

_DEFAULT_TEST_CASE_PACK = {
    "story_summary": "Stub story summary",
    "assumptions": ["Stub provider returns deterministic local test cases."],
    "test_cases": [
        {
            "id": "TC-001",
            "type": "negative",
            "title": "Reject invalid login credentials",
            "preconditions": ["User is on the login page"],
            "steps": [
                "Enter an invalid username or password",
                "Submit the login form",
            ],
            "expected_result": "The user remains on the login page and sees a validation error.",
            "acceptance_criterion_ref": "AC-001",
            "tags": ["login", "negative"],
        }
    ],
    "traceability_matrix": [
        {
            "acceptance_criterion": "Invalid credentials are rejected",
            "test_case_ids": ["TC-001"],
        }
    ],
    "coverage_summary": "Covers one deterministic negative-path login scenario.",
    "test_types_covered": ["negative"],
}


class StubProvider(ProviderInterface):
    """Returns a deterministic JSON artifact response without any network call.

    Accepts an optional ``fixed_response`` to override the default stub payload,
    which is useful in tests that need to assert on specific artifact content.
    """

    _PROVIDER_ID = "stub"

    def __init__(self, fixed_response: dict | None = None) -> None:
        self._fixed_response = fixed_response

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        raw_text = json.dumps(self._fixed_response or _default_response_for(request))
        input_tokens = sum(len(m.content.split()) for m in request.messages)
        output_tokens = len(raw_text.split())

        return ProviderResponse(
            request_id=request.request_id,
            provider_id=self._PROVIDER_ID,
            model=request.config.model,
            raw_text=raw_text,
            usage=ProviderUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            finish_reason=ProviderFinishReason.STOP,
            latency_ms=0,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self._PROVIDER_ID,
            status=ProviderHealthStatus.OK,
            model="stub",
            latency_ms=0,
        )


def _default_response_for(request: ProviderRequest) -> dict:
    prompt_text = "\n".join(message.content for message in request.messages)
    if '"test_cases"' in prompt_text and '"story_summary"' in prompt_text:
        return _DEFAULT_TEST_CASE_PACK
    return _DEFAULT_ARTIFACT
