from enum import StrEnum

from pydantic import Field

from totalrecall.contracts import ContractModel


class TestType(StrEnum):
    __test__ = False  # prevent pytest collection

    FUNCTIONAL = "functional"
    NEGATIVE = "negative"
    EDGE_CASE = "edge_case"
    API = "api"
    REGRESSION = "regression"


class ReformulatedIntent(ContractModel):
    jira_key: str | None = None
    intent_summary: str = Field(min_length=1)
    test_types: list[TestType] = Field(default_factory=list)
    output_format: str = Field(default="test_case_pack")
    raw_prompt: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
