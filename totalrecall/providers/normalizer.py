"""Normalizes raw provider text output into structured GeneratedArtifact objects."""

import json
from typing import Any

from totalrecall.errors import ServiceError, ServiceErrorCode
from totalrecall.generation.models import ArtifactType, GeneratedArtifact, Language
from totalrecall.providers.models import ProviderResponse

_VALID_ARTIFACT_TYPES = {v.value for v in ArtifactType}
_VALID_LANGUAGES = {v.value for v in Language}


class ResponseNormalizer:
    """Parses the raw_text from a ProviderResponse into validated GeneratedArtifact objects."""

    def normalize(
        self, response: ProviderResponse
    ) -> tuple[list[GeneratedArtifact], list[ServiceError]]:
        errors: list[ServiceError] = []

        try:
            payload = json.loads(response.raw_text)
        except json.JSONDecodeError as exc:
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.VALIDATION_FAILED,
                    message=f"Provider response is not valid JSON: {exc}",
                    details={"raw_text_preview": response.raw_text[:200]},
                )
            )
            return [], errors

        if not isinstance(payload, dict) or "artifacts" not in payload:
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.VALIDATION_FAILED,
                    message='Provider response missing required "artifacts" key',
                    details={
                        "keys_found": list(payload.keys()) if isinstance(payload, dict) else []
                    },
                )
            )
            return [], errors

        raw_artifacts = payload["artifacts"]
        if not isinstance(raw_artifacts, list):
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.VALIDATION_FAILED,
                    message='"artifacts" must be a JSON array',
                )
            )
            return [], errors

        artifacts: list[GeneratedArtifact] = []
        for i, item in enumerate(raw_artifacts):
            artifact, item_errors = self._parse_artifact(i, item)
            errors.extend(item_errors)
            if artifact is not None:
                artifacts.append(artifact)

        return artifacts, errors

    def _parse_artifact(
        self, index: int, item: Any
    ) -> tuple[GeneratedArtifact | None, list[ServiceError]]:
        errors: list[ServiceError] = []
        prefix = f"artifacts[{index}]"

        if not isinstance(item, dict):
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.VALIDATION_FAILED,
                    message=f"{prefix}: each artifact must be a JSON object",
                )
            )
            return None, errors

        missing = [f for f in ("path", "artifact_type", "language", "content") if f not in item]
        if missing:
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.VALIDATION_FAILED,
                    message=f"{prefix}: missing required fields: {', '.join(missing)}",
                    details={"missing": missing},
                )
            )
            return None, errors

        artifact_type_raw = item["artifact_type"]
        if artifact_type_raw not in _VALID_ARTIFACT_TYPES:
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.VALIDATION_FAILED,
                    message=f"{prefix}: unknown artifact_type '{artifact_type_raw}'",
                    details={"valid": sorted(_VALID_ARTIFACT_TYPES)},
                )
            )
            return None, errors

        language_raw = item["language"]
        if language_raw not in _VALID_LANGUAGES:
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.VALIDATION_FAILED,
                    message=f"{prefix}: unknown language '{language_raw}'",
                    details={"valid": sorted(_VALID_LANGUAGES)},
                )
            )
            return None, errors

        return (
            GeneratedArtifact(
                path=str(item["path"]),
                artifact_type=ArtifactType(artifact_type_raw),
                language=Language(language_raw),
                content=str(item["content"]),
            ),
            [],
        )
