from enum import StrEnum
from typing import Any

from pydantic import Field

from totalrecall.contracts import ContractModel
from totalrecall.errors import ServiceError
from totalrecall.testgen.models import TestType
from totalrecall.testgen.pack.models import TestCasePack


class Language(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVA = "java"


class Framework(StrEnum):
    PLAYWRIGHT = "playwright"
    PYTEST = "pytest"
    JUNIT = "junit"
    TESTNG = "testng"


class AutomationPattern(StrEnum):
    POM = "pom"


class LocatorStrategy(StrEnum):
    PAGE_FILE = "page_file"
    CENTRAL_MODULE = "central_module"
    EXTERNAL_STORE = "external_store"


class ArtifactType(StrEnum):
    PAGE_OBJECT = "page_object"
    TEST_SPEC = "test_spec"
    FIXTURE = "fixture"
    CONFIG = "config"
    SUPPORT = "support"


class ValidationStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class GenerationStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationTarget(ContractModel):
    language: Language
    framework: Framework
    pattern: AutomationPattern = AutomationPattern.POM
    locator_strategy: LocatorStrategy = LocatorStrategy.PAGE_FILE


TechStackTarget = GenerationTarget


class GenerationScope(ContractModel):
    domain: str = Field(min_length=1)
    route: str | None = None
    tags: list[str] = Field(default_factory=list)


class ProviderSelection(ContractModel):
    provider_id: str = Field(default="stub", min_length=1)
    model: str = Field(default="test", min_length=1)
    fallback_provider_ids: list[str] = Field(default_factory=list)


class GenerationOptions(ContractModel):
    validation_enabled: bool = Field(default=True, alias="validate")
    allow_repair: bool = False
    max_input_tokens: int = Field(default=12_000, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)


class GenerationRequest(ContractModel):
    tenant_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    target: GenerationTarget
    scope: GenerationScope
    provider: ProviderSelection = Field(default_factory=ProviderSelection)
    options: GenerationOptions = Field(default_factory=GenerationOptions)
    jira_key: str | None = Field(default=None, description="JIRA issue key, e.g. PROJ-123")
    test_types: list[TestType] | None = Field(
        default=None,
        description="Override test type routing",
    )


class GeneratedArtifact(ContractModel):
    path: str = Field(min_length=1)
    language: Language
    content: str
    artifact_type: ArtifactType


class ValidationDiagnostic(ContractModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    path: str | None = None
    severity: ValidationStatus = ValidationStatus.FAILED
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationSummary(ContractModel):
    status: ValidationStatus = ValidationStatus.NOT_RUN
    diagnostics: list[ValidationDiagnostic] = Field(default_factory=list)


class GenerationContextMetadata(ContractModel):
    context_plan_id: str | None = None
    skill_ids: list[str] = Field(default_factory=list)
    memory_ids: list[str] = Field(default_factory=list)
    estimated_input_tokens: int = Field(default=0, ge=0)
    baseline_input_tokens: int = Field(default=0, ge=0)
    estimated_tokens_saved: int = Field(default=0, ge=0)
    token_savings_percent: float = Field(default=0.0, ge=0.0)
    excluded_memory_count: int = Field(default=0, ge=0)
    max_input_tokens: int = Field(default=0, ge=0)


class GenerationResult(ContractModel):
    request_id: str = Field(min_length=1)
    status: GenerationStatus
    artifacts: list[GeneratedArtifact] = Field(default_factory=list)
    validation: ValidationSummary = Field(default_factory=ValidationSummary)
    context: GenerationContextMetadata = Field(default_factory=GenerationContextMetadata)
    errors: list[ServiceError] = Field(default_factory=list)
    test_case_pack: TestCasePack | None = Field(default=None)
