"""Per-test-type prompt section builders."""

from totalrecall.testgen.models import TestType

_TEST_CASE_PACK_SCHEMA = {
    "type": "object",
    "required": ["story_summary", "test_cases"],
    "properties": {
        "story_summary": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "type", "title", "steps", "expected_result"],
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "title": {"type": "string"},
                    "preconditions": {"type": "array", "items": {"type": "string"}},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "expected_result": {"type": "string"},
                    "acceptance_criterion_ref": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "traceability_matrix": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["acceptance_criterion", "test_case_ids"],
                "properties": {
                    "acceptance_criterion": {"type": "string"},
                    "test_case_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "coverage_summary": {"type": "string"},
        "source_jira_key": {"type": "string"},
        "test_types_covered": {"type": "array", "items": {"type": "string"}},
    },
}


def build_functional_section(story, rag_chunks) -> str:
    lines = [
        "### Functional Tests",
        "Generate positive-path test cases that verify the feature works as specified.",
        "Each test case should map to one acceptance criterion.",
    ]
    return "\n".join(lines)


def build_negative_section(story, rag_chunks) -> str:
    lines = [
        "### Negative Tests",
        "Generate test cases for invalid inputs, boundary violations, and error paths.",
        "Include expected error messages or HTTP status codes where applicable.",
    ]
    return "\n".join(lines)


def build_edge_case_section(story, rag_chunks) -> str:
    lines = [
        "### Edge Case Tests",
        "Generate test cases for boundary values, empty inputs, maximum lengths, and race conditions.",
    ]
    return "\n".join(lines)


def build_api_section(story, rag_chunks) -> str:
    lines = [
        "### API Tests",
        "Generate contract-level test cases verifying request/response schema, status codes, and headers.",
        "Include authentication, pagination, and error response tests.",
    ]
    return "\n".join(lines)


def build_regression_section(story, rag_chunks) -> str:
    lines = [
        "### Regression Tests",
        "Generate test cases that guard against regressions in existing behavior.",
        "Focus on previously reported bugs and critical user journeys.",
    ]
    return "\n".join(lines)


_SECTION_BUILDERS = {
    TestType.FUNCTIONAL: build_functional_section,
    TestType.NEGATIVE: build_negative_section,
    TestType.EDGE_CASE: build_edge_case_section,
    TestType.API: build_api_section,
    TestType.REGRESSION: build_regression_section,
}
