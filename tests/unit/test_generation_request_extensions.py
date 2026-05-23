"""Tests for new optional fields on GenerationRequest and GenerationResult."""

import pytest
from pydantic import ValidationError

from totalrecall.generation.models import (
    Framework,
    GenerationOptions,
    GenerationRequest,
    GenerationResult,
    GenerationScope,
    GenerationStatus,
    GenerationTarget,
    Language,
    ProviderSelection,
)
from totalrecall.testgen.models import TestType
from totalrecall.testgen.pack.models import TestCasePack


def _base_request(**overrides) -> dict:
    base = {
        "tenant_id": "t1",
        "application_id": "app1",
        "prompt": "Generate tests",
        "target": {
            "language": "python",
            "framework": "pytest",
        },
        "scope": {"domain": "login"},
    }
    base.update(overrides)
    return base


class TestGenerationRequestExtensions:
    def test_jira_key_defaults_to_none(self):
        req = GenerationRequest(**_base_request())
        assert req.jira_key is None

    def test_test_types_defaults_to_none(self):
        req = GenerationRequest(**_base_request())
        assert req.test_types is None

    def test_jira_key_accepts_valid_key(self):
        req = GenerationRequest(**_base_request(jira_key="PROJ-123"))
        assert req.jira_key == "PROJ-123"

    def test_test_types_accepts_list(self):
        req = GenerationRequest(**_base_request(test_types=["functional", "negative"]))
        assert req.test_types == [TestType.FUNCTIONAL, TestType.NEGATIVE]

    def test_existing_fields_still_required(self):
        with pytest.raises(ValidationError):
            GenerationRequest(tenant_id="t", application_id="a", target=None, scope=None, prompt="x")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            GenerationRequest(**_base_request(unknown_field="oops"))

    def test_round_trip_without_new_fields(self):
        req = GenerationRequest(**_base_request())
        dumped = req.model_dump()
        restored = GenerationRequest(**dumped)
        assert restored.tenant_id == req.tenant_id
        assert restored.jira_key is None
        assert restored.test_types is None

    def test_round_trip_with_new_fields(self):
        req = GenerationRequest(**_base_request(jira_key="SCRUM-5", test_types=["api"]))
        dumped = req.model_dump()
        restored = GenerationRequest(**dumped)
        assert restored.jira_key == "SCRUM-5"
        assert restored.test_types == [TestType.API]


class TestGenerationResultExtensions:
    def _base_result(self, **overrides) -> dict:
        base = {"request_id": "req-1", "status": "completed"}
        base.update(overrides)
        return base

    def test_test_case_pack_defaults_to_none(self):
        from totalrecall.generation.models import GenerationResult
        result = GenerationResult(**self._base_result())
        assert result.test_case_pack is None

    def test_test_case_pack_accepts_valid_pack(self):
        from totalrecall.generation.models import GenerationResult
        pack = TestCasePack(story_summary="Test story", test_types_covered=[TestType.FUNCTIONAL])
        result = GenerationResult(**self._base_result(test_case_pack=pack.model_dump()))
        assert result.test_case_pack is not None
        assert result.test_case_pack.story_summary == "Test story"

    def test_extra_fields_still_rejected(self):
        from totalrecall.generation.models import GenerationResult
        with pytest.raises(ValidationError):
            GenerationResult(**self._base_result(unknown_field="oops"))
