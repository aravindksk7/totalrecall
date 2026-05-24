"""Unit tests for TestCasePackNormalizer."""

import json

from totalrecall.errors import ServiceErrorCode
from totalrecall.testgen.pack.normalizer import TestCasePackNormalizer


def _valid_pack_json(**overrides) -> str:
    data = {
        "story_summary": "User can log in",
        "test_cases": [
            {
                "id": "TC-001",
                "type": "functional",
                "title": "Login with valid credentials",
                "steps": ["Navigate to login", "Enter valid email", "Click Submit"],
                "expected_result": "User is redirected to dashboard",
            }
        ],
    }
    data.update(overrides)
    return json.dumps(data)


class TestTestCasePackNormalizer:
    def test_valid_json_returns_pack(self):
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(_valid_pack_json())
        assert pack is not None
        assert errors == []
        assert pack.story_summary == "User can log in"

    def test_valid_json_with_optional_fields(self):
        json_str = _valid_pack_json(
            assumptions=["User has an account"],
            coverage_summary="Covers happy path",
            test_types_covered=["functional"],
        )
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(json_str)
        assert pack is not None
        assert pack.assumptions == ["User has an account"]

    def test_malformed_json_returns_error(self):
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize("{not valid json}")
        assert pack is None
        assert len(errors) == 1
        assert errors[0].code == ServiceErrorCode.NORMALIZATION_FAILED

    def test_missing_story_summary_returns_error(self):
        data = {"test_cases": []}
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(json.dumps(data))
        assert pack is None
        assert any("story_summary" in e.message for e in errors)

    def test_missing_test_cases_returns_error(self):
        data = {"story_summary": "A story"}
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(json.dumps(data))
        assert pack is None
        assert any("test_cases" in e.message for e in errors)

    def test_non_dict_json_returns_error(self):
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize("[1, 2, 3]")
        assert pack is None
        assert len(errors) == 1

    def test_source_jira_key_injected_when_missing(self):
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(_valid_pack_json(), source_jira_key="PROJ-99")
        assert pack is not None
        assert pack.source_jira_key == "PROJ-99"

    def test_source_jira_key_not_overwritten_when_present(self):
        json_str = _valid_pack_json(source_jira_key="ORIG-1")
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(json_str, source_jira_key="OTHER-2")
        assert pack is not None
        assert pack.source_jira_key == "ORIG-1"

    def test_strips_markdown_fences(self):
        raw = "```json\n" + _valid_pack_json() + "\n```"
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(raw)
        assert pack is not None
        assert errors == []

    def test_test_cases_are_hydrated_as_models(self):
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(_valid_pack_json())
        assert len(pack.test_cases) == 1
        assert pack.test_cases[0].id == "TC-001"
        assert pack.test_cases[0].title == "Login with valid credentials"

    def test_unknown_top_level_keys_log_warning_and_fail_validation(self):
        import json
        from totalrecall.errors import ServiceErrorCode

        data = json.loads(_valid_pack_json())
        data["unexpected_field"] = "some_value"
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(json.dumps(data))
        # pydantic extra="forbid" rejects unknown fields — pack is None but the warning path was reached
        assert pack is None
        assert any(e.code == ServiceErrorCode.NORMALIZATION_FAILED for e in errors)

    def test_pydantic_validation_failure_returns_error(self):
        import json
        from totalrecall.errors import ServiceErrorCode

        data = {
            "story_summary": "A story",
            "test_cases": [
                {
                    "id": "",  # min_length=1 — will fail pydantic validation
                    "type": "functional",
                    "title": "A test",
                    "steps": ["step 1"],
                    "expected_result": "passes",
                }
            ],
        }
        norm = TestCasePackNormalizer()
        pack, errors = norm.normalize(json.dumps(data))
        assert pack is None
        assert any(e.code == ServiceErrorCode.NORMALIZATION_FAILED for e in errors)
