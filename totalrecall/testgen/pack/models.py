from datetime import UTC, datetime

from pydantic import Field

from totalrecall.contracts import ContractModel
from totalrecall.testgen.models import TestType


class TestCase(ContractModel):
    id: str = Field(min_length=1)
    type: TestType
    title: str = Field(min_length=1)
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    acceptance_criterion_ref: str | None = None
    tags: list[str] = Field(default_factory=list)


class TraceabilityEntry(ContractModel):
    acceptance_criterion: str = Field(min_length=1)
    test_case_ids: list[str] = Field(default_factory=list)


class TestCasePack(ContractModel):
    __test__ = False  # prevent pytest collection
    story_summary: str = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    traceability_matrix: list[TraceabilityEntry] = Field(default_factory=list)
    coverage_summary: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_jira_key: str | None = None
    test_types_covered: list[TestType] = Field(default_factory=list)
