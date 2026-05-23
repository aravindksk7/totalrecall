from enum import StrEnum

from pydantic import Field

from totalrecall.contracts import ContractModel
from totalrecall.generation.models import (
    ArtifactType,
    AutomationPattern,
    Framework,
    Language,
    LocatorStrategy,
)


class SkillStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class SkillValidatorType(StrEnum):
    STRUCTURE = "structure"
    SYNTAX = "syntax"
    POLICY = "policy"
    DRY_RUN = "dry_run"


class SkillOutputFile(ContractModel):
    artifact_type: ArtifactType
    path_template: str = Field(min_length=1)
    template_ref: str = Field(min_length=1)


class SkillValidator(ContractModel):
    type: SkillValidatorType
    command: str | None = None
    rules: list[str] = Field(default_factory=list)


class SkillDefinition(ContractModel):
    skill_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    language: Language
    framework: Framework
    pattern: AutomationPattern = AutomationPattern.POM
    supported_locator_strategies: list[LocatorStrategy] = Field(
        default_factory=lambda: [LocatorStrategy.PAGE_FILE]
    )
    output_files: list[SkillOutputFile] = Field(min_length=1)
    generation_rules: list[str] = Field(default_factory=list)
    validators: list[SkillValidator] = Field(default_factory=list)
    status: SkillStatus = SkillStatus.DRAFT
    owner: str | None = None
    description: str | None = None
