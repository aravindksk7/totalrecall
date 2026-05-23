import json

from totalrecall.errors import ServiceErrorCode
from totalrecall.generation.models import ArtifactType, Language
from totalrecall.providers.models import (
    ProviderFinishReason,
    ProviderResponse,
    ProviderUsage,
)
from totalrecall.providers.normalizer import ResponseNormalizer


def _make_response(raw_text: str) -> ProviderResponse:
    return ProviderResponse(
        request_id="req_001",
        provider_id="stub",
        model="stub",
        raw_text=raw_text,
        usage=ProviderUsage(),
        finish_reason=ProviderFinishReason.STOP,
    )


def _valid_payload(*overrides: dict) -> str:
    artifact = {
        "path": "pages/checkout/checkout.page.ts",
        "artifact_type": "page_object",
        "language": "typescript",
        "content": "export class CheckoutPage {}",
    }
    artifact.update(*overrides if overrides else [{}])
    return json.dumps({"artifacts": [artifact]})


def test_normalizer_parses_valid_artifact() -> None:
    normalizer = ResponseNormalizer()
    artifacts, errors = normalizer.normalize(_make_response(_valid_payload()))

    assert errors == []
    assert len(artifacts) == 1
    assert artifacts[0].path == "pages/checkout/checkout.page.ts"
    assert artifacts[0].artifact_type == ArtifactType.PAGE_OBJECT
    assert artifacts[0].language == Language.TYPESCRIPT


def test_normalizer_returns_error_for_invalid_json() -> None:
    normalizer = ResponseNormalizer()
    artifacts, errors = normalizer.normalize(_make_response("not json at all"))

    assert artifacts == []
    assert len(errors) == 1
    assert errors[0].code == ServiceErrorCode.VALIDATION_FAILED


def test_normalizer_returns_error_when_artifacts_key_missing() -> None:
    normalizer = ResponseNormalizer()
    artifacts, errors = normalizer.normalize(_make_response('{"other": []}'))

    assert artifacts == []
    assert errors[0].code == ServiceErrorCode.VALIDATION_FAILED
    assert "artifacts" in errors[0].message


def test_normalizer_returns_error_when_artifacts_not_a_list() -> None:
    normalizer = ResponseNormalizer()
    artifacts, errors = normalizer.normalize(_make_response('{"artifacts": "bad"}'))

    assert artifacts == []
    assert errors[0].code == ServiceErrorCode.VALIDATION_FAILED


def test_normalizer_returns_error_for_missing_required_fields() -> None:
    normalizer = ResponseNormalizer()
    payload = json.dumps({"artifacts": [{"path": "x.ts"}]})
    artifacts, errors = normalizer.normalize(_make_response(payload))

    assert artifacts == []
    assert any("missing" in e.message.lower() for e in errors)


def test_normalizer_returns_error_for_unknown_artifact_type() -> None:
    normalizer = ResponseNormalizer()
    payload = _valid_payload({"artifact_type": "banana"})
    artifacts, errors = normalizer.normalize(_make_response(payload))

    assert artifacts == []
    assert any("artifact_type" in e.message for e in errors)


def test_normalizer_returns_error_for_unknown_language() -> None:
    normalizer = ResponseNormalizer()
    payload = _valid_payload({"language": "cobol"})
    artifacts, errors = normalizer.normalize(_make_response(payload))

    assert artifacts == []
    assert any("language" in e.message for e in errors)


def test_normalizer_handles_multiple_artifacts() -> None:
    normalizer = ResponseNormalizer()
    payload = json.dumps({
        "artifacts": [
            {
                "path": "pages/checkout.page.ts",
                "artifact_type": "page_object",
                "language": "typescript",
                "content": "export class CheckoutPage {}",
            },
            {
                "path": "tests/checkout.spec.ts",
                "artifact_type": "test_spec",
                "language": "typescript",
                "content": "test('checkout', () => {});",
            },
        ]
    })
    artifacts, errors = normalizer.normalize(_make_response(payload))

    assert errors == []
    assert len(artifacts) == 2
    types = {a.artifact_type for a in artifacts}
    assert ArtifactType.PAGE_OBJECT in types
    assert ArtifactType.TEST_SPEC in types
