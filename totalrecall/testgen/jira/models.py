from datetime import datetime

from pydantic import Field

from totalrecall.contracts import ContractModel


class JiraAcceptanceCriterion(ContractModel):
    index: int = Field(ge=0)
    text: str = Field(min_length=1)


class JiraStory(ContractModel):
    jira_key: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    description: str = ""
    acceptance_criteria: list[JiraAcceptanceCriterion] = Field(default_factory=list)
    story_type: str = ""
    status: str = ""
    labels: list[str] = Field(default_factory=list)
    fetched_at: datetime
