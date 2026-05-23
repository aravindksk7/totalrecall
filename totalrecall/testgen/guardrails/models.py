from enum import StrEnum

from pydantic import Field

from totalrecall.contracts import ContractModel


class GuardrailViolationCode(StrEnum):
    UNSAFE_CONTENT = "unsafe_content"
    NOT_QA_DOMAIN = "not_qa_domain"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    JIRA_KEY_FORMAT = "jira_key_format"


class GuardrailViolation(ContractModel):
    code: GuardrailViolationCode
    message: str = Field(min_length=1)
    field: str | None = None


class GuardrailResult(ContractModel):
    passed: bool
    violations: list[GuardrailViolation] = Field(default_factory=list)
