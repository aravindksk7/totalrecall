"""TestCasePackNormalizer: parses raw LLM JSON into a TestCasePack."""

import json
import logging

from totalrecall.errors import ServiceError, ServiceErrorCode
from totalrecall.testgen.pack.models import TestCasePack

_log = logging.getLogger(__name__)

_REQUIRED_TOP_LEVEL = {"story_summary", "test_cases"}
_ALLOWED_TOP_LEVEL = {
    "story_summary",
    "assumptions",
    "test_cases",
    "traceability_matrix",
    "coverage_summary",
    "source_jira_key",
    "test_types_covered",
}


class TestCasePackNormalizer:
    """Parses a raw LLM text response into a TestCasePack model."""

    def normalize(
        self, raw_text: str, source_jira_key: str | None = None
    ) -> tuple[TestCasePack | None, list[ServiceError]]:
        errors: list[ServiceError] = []

        # Strip markdown fences if present
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[start:end])

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.NORMALIZATION_FAILED,
                    message=f"Invalid JSON in test case pack response: {exc}",
                )
            )
            return None, errors

        if not isinstance(data, dict):
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.NORMALIZATION_FAILED,
                    message="Test case pack response must be a JSON object",
                )
            )
            return None, errors

        # Validate required fields
        for field in _REQUIRED_TOP_LEVEL:
            if field not in data:
                errors.append(
                    ServiceError(
                        code=ServiceErrorCode.NORMALIZATION_FAILED,
                        message=f"Missing required field: {field}",
                    )
                )

        if errors:
            return None, errors

        # Check for unknown top-level keys (schema drift warning, not fatal)
        unknown_keys = set(data.keys()) - _ALLOWED_TOP_LEVEL
        if unknown_keys:
            _log.warning("Unknown keys in test case pack response: %s", unknown_keys)

        # Inject source_jira_key if not already present
        if source_jira_key and "source_jira_key" not in data:
            data["source_jira_key"] = source_jira_key

        try:
            pack = TestCasePack.model_validate(data)
        except Exception as exc:
            errors.append(
                ServiceError(
                    code=ServiceErrorCode.NORMALIZATION_FAILED,
                    message=f"Test case pack validation failed: {exc}",
                )
            )
            return None, errors

        return pack, []
