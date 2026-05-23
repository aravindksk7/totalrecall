import pytest
from pydantic import ValidationError

from totalrecall.catalogue.models import (
    CatalogueCategory,
    CatalogueEntry,
    CatalogueSearchFilters,
    CatalogueSource,
    CatalogueStatus,
)
from totalrecall.context.models import (
    ContextExclusion,
    ContextExclusionReason,
    ContextPlan,
    SelectedMemory,
    SelectedSkill,
    TokenBudget,
)
from totalrecall.errors import ServiceError, ServiceErrorCode
from totalrecall.generation.models import (
    ArtifactType,
    Framework,
    GeneratedArtifact,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    Language,
)
from totalrecall.learning.models import (
    LearningApproval,
    LearningApprovalDecision,
    LearningDelta,
    LearningDeltaState,
    LearningDiscovery,
    LearningDiscoveryType,
    LearningRun,
    LearningScope,
    LearningTriggerType,
)
from totalrecall.memory.models import MemoryEntry, MemorySearchRequest, MemorySource, MemoryStatus
from totalrecall.providers.models import (
    ProviderConfig,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
    ProviderRole,
    ProviderUsage,
)
from totalrecall.skills.models import SkillDefinition, SkillOutputFile, SkillValidator


def test_generation_contract_accepts_framework_target_and_rejects_extra_fields() -> None:
    request = GenerationRequest.model_validate(
        {
            "tenant_id": "tenant_acme",
            "application_id": "shop",
            "prompt": "Create a login test",
            "target": {"language": "typescript", "framework": "playwright"},
            "scope": {"domain": "authentication", "route": "/login"},
            "options": {"validate": False},
        }
    )
    result = GenerationResult(
        request_id="gen_1",
        status=GenerationStatus.COMPLETED,
        artifacts=[
            GeneratedArtifact(
                path="tests/login.spec.ts",
                language=Language.TYPESCRIPT,
                content="test('login', async () => {})",
                artifact_type=ArtifactType.TEST_SPEC,
            )
        ],
    )

    assert request.target.framework is Framework.PLAYWRIGHT
    assert request.provider.provider_id == "stub"
    assert request.options.validation_enabled is False
    assert result.artifacts[0].path == "tests/login.spec.ts"

    with pytest.raises(ValidationError):
        GenerationRequest.model_validate(
            {
                "tenant_id": "tenant_acme",
                "application_id": "shop",
                "prompt": "Create a login test",
                "target": {"language": "go", "framework": "playwright"},
                "scope": {"domain": "authentication"},
                "unexpected": True,
            }
        )


def test_skill_contract_requires_output_files_and_validators_are_typed() -> None:
    skill = SkillDefinition(
        skill_id="playwright-pom",
        version="1.0.0",
        language=Language.TYPESCRIPT,
        framework=Framework.PLAYWRIGHT,
        output_files=[
            SkillOutputFile(
                artifact_type=ArtifactType.PAGE_OBJECT,
                path_template="pages/{name}.ts",
                template_ref="playwright/page-object",
            )
        ],
        validators=[SkillValidator(type="structure", rules=["requires-page-object"])],
    )

    assert skill.output_files[0].template_ref == "playwright/page-object"
    assert skill.validators[0].type == "structure"

    with pytest.raises(ValidationError):
        SkillDefinition(
            skill_id="bad",
            version="1.0.0",
            language=Language.PYTHON,
            framework=Framework.PYTEST,
            output_files=[],
        )


def test_memory_contract_enforces_source_attribution_and_search_limits() -> None:
    memory = MemoryEntry(
        entity_id="mem_login",
        tenant_id="tenant_acme",
        application_id="shop",
        summary="Login submit button",
        knowledge="The login submit control has accessible name Sign in.",
        source=MemorySource(
            source_type="learning_run",
            reference="run_1",
            file_path="tests/login.spec.ts",
            symbol_name="login succeeds",
        ),
        tags={"domain": "authentication"},
    )

    assert memory.status is MemoryStatus.ACTIVE
    assert memory.source is not None
    assert memory.source.file_path == "tests/login.spec.ts"

    with pytest.raises(ValidationError):
        MemoryEntry(
            entity_id="mem_bad",
            tenant_id="tenant_acme",
            application_id="shop",
            summary="Bad confidence",
            knowledge="Confidence must be bounded.",
            confidence=1.1,
        )

    with pytest.raises(ValidationError):
        MemorySearchRequest(tenant_id="tenant_acme", application_id="shop", limit=0)


def test_catalogue_contract_preserves_governance_metadata() -> None:
    entry = CatalogueEntry(
        entity_id="mem_login",
        tenant_id="tenant_acme",
        application_id="shop",
        category=CatalogueCategory.DYNAMIC_MEMORY,
        status=CatalogueStatus.ACTIVE,
        summary="Login submit button memory",
        source=CatalogueSource(
            type="repository_learning",
            reference="run_1",
            file_path="tests/login.spec.ts",
            symbol_name="login succeeds",
            commit_id="abc123",
        ),
        approved_by="actor_admin",
    )
    filters = CatalogueSearchFilters(
        tenant_id="tenant_acme",
        category="dynamic_memory",
        framework="playwright",
        limit=25,
    )

    assert entry.source.commit_id == "abc123"
    assert entry.approved_by == "actor_admin"
    assert filters.framework is Framework.PLAYWRIGHT

    with pytest.raises(ValidationError):
        CatalogueSearchFilters(tenant_id="tenant_acme", limit=0)


def test_learning_contract_captures_delta_source_and_approval() -> None:
    discovery = LearningDiscovery(
        discovery_id="disc_1",
        discovery_type=LearningDiscoveryType.DYNAMIC_MEMORY,
        delta=LearningDelta(
            state=LearningDeltaState.CHANGED,
            previous_hash="old",
            current_hash="new",
            changed_fields=["locator"],
        ),
        summary="Login locator changed",
        source=CatalogueSource(
            type="repository_learning",
            reference="run_1",
            file_path="tests/login.spec.ts",
        ),
        approval=LearningApproval(
            decision=LearningApprovalDecision.APPROVED,
            actor_id="actor_admin",
        ),
    )
    run = LearningRun(
        run_id="run_1",
        tenant_id="tenant_acme",
        application_id="shop",
        scope=LearningScope(
            repository="https://example.invalid/shop-tests.git",
            branch="main",
            path="tests",
            framework=Framework.PLAYWRIGHT,
        ),
        trigger_type=LearningTriggerType.MANUAL,
        discoveries=[discovery],
    )

    assert run.discoveries[0].delta.state is LearningDeltaState.CHANGED
    assert run.discoveries[0].approval is not None

    with pytest.raises(ValidationError):
        LearningDiscovery(
            discovery_id="disc_bad",
            discovery_type=LearningDiscoveryType.DYNAMIC_MEMORY,
            delta=LearningDelta(state=LearningDeltaState.NEW),
            summary="Invalid confidence",
            confidence=-0.1,
            source=CatalogueSource(type="repository_learning", reference="run_1"),
        )


def test_context_plan_contract_tracks_selection_budget_and_exclusions() -> None:
    plan = ContextPlan(
        context_plan_id="ctx_1",
        tenant_id="tenant_acme",
        application_id="shop",
        request_id="gen_1",
        selected_skills=[SelectedSkill(skill_id="playwright-pom", version="1.0.0")],
        selected_memories=[SelectedMemory(memory_id="mem_login", confidence=0.91)],
        skill_ids=["playwright-pom"],
        memory_ids=["mem_login"],
        excluded=[
            ContextExclusion(
                entity_id="mem_checkout",
                reason=ContextExclusionReason.DOMAIN_MISMATCH,
            )
        ],
        token_budget=TokenBudget(
            max_input_tokens=12_000,
            estimated_input_tokens=2_000,
            baseline_estimate=8_000,
            estimated_tokens_saved=6_000,
        ),
    )

    assert plan.token_budget.estimated_tokens_saved == 6_000
    assert plan.excluded[0].reason is ContextExclusionReason.DOMAIN_MISMATCH

    with pytest.raises(ValidationError):
        TokenBudget(max_input_tokens=0)


def test_provider_contract_normalizes_request_response_health_and_errors() -> None:
    request = ProviderRequest(
        request_id="gen_1",
        tenant_id="tenant_acme",
        messages=[ProviderMessage(role=ProviderRole.USER, content="Generate a test")],
        config=ProviderConfig(provider_id="stub", model="deterministic"),
    )
    response = ProviderResponse(
        request_id=request.request_id,
        provider_id=request.config.provider_id,
        model=request.config.model,
        raw_text='{"artifacts": []}',
        usage=ProviderUsage(input_tokens=100, output_tokens=25),
        errors=[
            ServiceError(
                code=ServiceErrorCode.PROVIDER_RATE_LIMITED,
                message="Provider throttled the request.",
                retryable=True,
            )
        ],
    )
    health = ProviderHealth(provider_id="stub", status=ProviderHealthStatus.OK)

    assert response.usage.input_tokens == 100
    assert response.errors[0].retryable is True
    assert health.status is ProviderHealthStatus.OK

    with pytest.raises(ValidationError):
        ProviderConfig(provider_id="stub", model="deterministic", temperature=2.1)
