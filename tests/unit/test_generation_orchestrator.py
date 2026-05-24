import json
from pathlib import Path

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.context.planner import ContextPlanner
from totalrecall.errors import ServiceErrorCode
from totalrecall.generation.models import (
    AutomationPattern,
    Framework,
    GenerationOptions,
    GenerationRequest,
    GenerationScope,
    GenerationStatus,
    GenerationTarget,
    Language,
    LocatorStrategy,
    ProviderSelection,
    ValidationStatus,
)
from totalrecall.generation.orchestrator import GenerationOrchestrator
from totalrecall.memory.adapters.null import NullMemoryAdapter
from totalrecall.memory.adapters.stub import StubMemoryAdapter
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.prompts.builder import PromptBuilder
from totalrecall.providers.base import ProviderInterface
from totalrecall.providers.gateway import ProviderGateway, ProviderNotFoundError
from totalrecall.providers.models import (
    ProviderFinishReason,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from totalrecall.providers.normalizer import ResponseNormalizer
from totalrecall.providers.stub.provider import StubProvider
from totalrecall.skills.registry import SkillRegistry
from totalrecall.testgen.guardrails.models import GuardrailResult, GuardrailViolation, GuardrailViolationCode
from totalrecall.testgen.guardrails.input_guardrail import StubInputGuardrail
from totalrecall.validation.coordinator import ValidationCoordinator

_PLAYWRIGHT_SKILL = {
    "skill_id": "playwright-typescript-pom",
    "version": "1.0.0",
    "language": "typescript",
    "framework": "playwright",
    "pattern": "pom",
    "supported_locator_strategies": ["page_file"],
    "output_files": [
        {
            "artifact_type": "page_object",
            "path_template": "pages/{domain}/{route}.page.ts",
            "template_ref": "playwright/page_object.ts",
        }
    ],
    "generation_rules": ["Use POM"],
    "status": "active",
}


def _make_registry(tmp_path: Path) -> SkillRegistry:
    (tmp_path / "skill.json").write_text(json.dumps(_PLAYWRIGHT_SKILL), encoding="utf-8")
    reg = SkillRegistry(tmp_path)
    reg.load()
    return reg


def _make_orchestrator(
    tmp_path: Path, fixed_response: dict | None = None
) -> GenerationOrchestrator:
    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        adapters={"stub": StubMemoryAdapter([]), "null": NullMemoryAdapter()},
    )
    return GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": StubProvider(fixed_response=fixed_response)}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
    )


def _make_request(provider_id: str = "stub") -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_test",
        application_id="app_test",
        prompt="Generate a page object for the checkout page",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="checkout"),
        provider=ProviderSelection(provider_id=provider_id, model="stub"),
        options=GenerationOptions(validate=True, max_input_tokens=12_000),
    )


def test_orchestrator_completes_with_stub_provider(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path)
    result = orchestrator.generate(_make_request())

    assert result.status == GenerationStatus.COMPLETED
    assert len(result.artifacts) >= 1


def test_orchestrator_populates_context_metadata(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path)
    result = orchestrator.generate(_make_request())

    assert result.context.context_plan_id is not None
    assert "playwright-typescript-pom" in result.context.skill_ids


def test_orchestrator_runs_validation(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path)
    result = orchestrator.generate(_make_request())

    assert result.validation.status != ValidationStatus.NOT_RUN


def test_orchestrator_returns_unique_request_ids(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path)
    r1 = orchestrator.generate(_make_request())
    r2 = orchestrator.generate(_make_request())

    assert r1.request_id != r2.request_id


def test_orchestrator_fails_gracefully_on_unknown_provider(tmp_path: Path) -> None:
    orchestrator = _make_orchestrator(tmp_path)
    result = orchestrator.generate(_make_request(provider_id="openai"))

    assert result.status == GenerationStatus.FAILED
    assert len(result.errors) >= 1


def test_orchestrator_skips_validation_when_disabled(tmp_path: Path) -> None:
    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        adapters={"stub": StubMemoryAdapter([]), "null": NullMemoryAdapter()},
    )
    orchestrator = GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": StubProvider()}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
    )

    request = GenerationRequest(
        tenant_id="tenant_test",
        application_id="app_test",
        prompt="Generate page object",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="checkout"),
        options=GenerationOptions(validate=False, max_input_tokens=12_000),
    )
    result = orchestrator.generate(request)

    assert result.validation.status == ValidationStatus.NOT_RUN


# --- Repair loop tests ---

_PLAYWRIGHT_SKILL_WITH_VALIDATOR = {
    "skill_id": "playwright-typescript-pom",
    "version": "1.0.0",
    "language": "typescript",
    "framework": "playwright",
    "pattern": "pom",
    "supported_locator_strategies": ["page_file"],
    "output_files": [
        {
            "artifact_type": "page_object",
            "path_template": "pages/{domain}/{route}.page.ts",
            "template_ref": "playwright/page_object.ts",
        }
    ],
    "generation_rules": ["Use POM"],
    "validators": [{"type": "structure", "rules": ["page_object_class_required"]}],
    "status": "active",
}

_INVALID_ARTIFACT = {
    "artifacts": [
        {
            "path": "pages/checkout/checkout.page.ts",
            "artifact_type": "page_object",
            "language": "typescript",
            "content": "// no implementation here",
        }
    ]
}

_VALID_ARTIFACT = {
    "artifacts": [
        {
            "path": "pages/checkout/checkout.page.ts",
            "artifact_type": "page_object",
            "language": "typescript",
            "content": "export class CheckoutPage {}",
        }
    ]
}


class _SequenceProvider(ProviderInterface):
    """Returns pre-defined responses in order, tracking call count."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.call_count = 0

    @property
    def provider_id(self) -> str:
        return "stub"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        payload = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        self.call_count += 1
        return ProviderResponse(
            request_id=request.request_id,
            provider_id="stub",
            model=request.config.model,
            raw_text=json.dumps(payload),
            usage=ProviderUsage(input_tokens=10, output_tokens=10),
            finish_reason=ProviderFinishReason.STOP,
            latency_ms=0,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id="stub", status=ProviderHealthStatus.OK, model="stub")


def _make_registry_with_validator(tmp_path: Path) -> SkillRegistry:
    (tmp_path / "skill.json").write_text(
        json.dumps(_PLAYWRIGHT_SKILL_WITH_VALIDATOR), encoding="utf-8"
    )
    reg = SkillRegistry(tmp_path)
    reg.load()
    return reg


def _make_repair_request(allow_repair: bool = True) -> GenerationRequest:
    return GenerationRequest(
        tenant_id="tenant_test",
        application_id="app_test",
        prompt="Generate a page object for checkout",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="checkout"),
        provider=ProviderSelection(provider_id="stub", model="stub"),
        options=GenerationOptions(validate=True, allow_repair=allow_repair, max_input_tokens=12_000),
    )


def _make_orchestrator_with_sequence(
    tmp_path: Path, provider: _SequenceProvider
) -> GenerationOrchestrator:
    skill_registry = _make_registry_with_validator(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "null"}),
        adapters={"null": NullMemoryAdapter()},
    )
    return GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": provider}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
    )


def test_repair_fixes_failed_validation(tmp_path: Path) -> None:
    """First response fails validation; repair response passes — result is COMPLETED."""
    provider = _SequenceProvider([_INVALID_ARTIFACT, _VALID_ARTIFACT])
    orchestrator = _make_orchestrator_with_sequence(tmp_path, provider)
    result = orchestrator.generate(_make_repair_request(allow_repair=True))

    assert result.status == GenerationStatus.COMPLETED
    assert result.validation.status == ValidationStatus.PASSED
    assert provider.call_count == 2


def test_repair_not_triggered_when_disabled(tmp_path: Path) -> None:
    """When allow_repair=False, a failed validation is not retried — exactly one provider call."""
    provider = _SequenceProvider([_INVALID_ARTIFACT])
    orchestrator = _make_orchestrator_with_sequence(tmp_path, provider)
    result = orchestrator.generate(_make_repair_request(allow_repair=False))

    assert result.validation.status == ValidationStatus.FAILED
    assert provider.call_count == 1


def test_repair_remains_failed_when_repair_also_fails(tmp_path: Path) -> None:
    """Both calls return invalid artifacts — validation is still FAILED after repair."""
    provider = _SequenceProvider([_INVALID_ARTIFACT, _INVALID_ARTIFACT])
    orchestrator = _make_orchestrator_with_sequence(tmp_path, provider)
    result = orchestrator.generate(_make_repair_request(allow_repair=True))

    assert result.validation.status == ValidationStatus.FAILED
    assert provider.call_count == 2


# --- Guardrail tests ---


def test_input_guardrail_blocks_request(tmp_path: Path) -> None:
    """When input guardrail fails, orchestrator short-circuits before any LLM calls."""
    violation = GuardrailViolation(
        code=GuardrailViolationCode.NOT_QA_DOMAIN,
        message="Prompt does not appear to be a QA request",
    )
    guardrail = StubInputGuardrail(should_pass=False, violations=[violation])
    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        adapters={"stub": StubMemoryAdapter([]), "null": NullMemoryAdapter()},
    )
    orchestrator = GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": StubProvider()}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
        input_guardrail=guardrail,
    )

    result = orchestrator.generate(_make_request())

    assert result.status == GenerationStatus.FAILED
    assert any(e.code == ServiceErrorCode.GUARDRAIL_BLOCKED for e in result.errors)


def test_output_guardrail_blocks_response(tmp_path: Path) -> None:
    """When output guardrail fails, orchestrator returns FAILED with GUARDRAIL_BLOCKED."""

    class _BlockingOutputGuardrail:
        adapter_version = "stub"

        def check(self, raw_text: str) -> GuardrailResult:
            return GuardrailResult(
                passed=False,
                violations=[
                    GuardrailViolation(
                        code=GuardrailViolationCode.UNSAFE_CONTENT,
                        message="Unsafe content detected",
                    )
                ],
            )

    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        adapters={"stub": StubMemoryAdapter([]), "null": NullMemoryAdapter()},
    )
    orchestrator = GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": StubProvider()}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
        output_guardrail=_BlockingOutputGuardrail(),
    )

    result = orchestrator.generate(_make_request())

    assert result.status == GenerationStatus.FAILED
    assert any(e.code == ServiceErrorCode.GUARDRAIL_BLOCKED for e in result.errors)


# --- Fail-open tests for parallel JIRA/RAG fetch ---


def test_jira_fetch_fail_open(tmp_path: Path) -> None:
    """When JIRA adapter raises, orchestrator logs a warning and continues normally."""

    class _ErrorJiraAdapter:
        adapter_version = "stub"

        def fetch_story(self, jira_key: str):
            raise RuntimeError("JIRA timed out")

        def health(self) -> dict:
            return {"status": "error"}

    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        adapters={"stub": StubMemoryAdapter([]), "null": NullMemoryAdapter()},
    )
    orchestrator = GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": StubProvider()}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
        jira_adapter=_ErrorJiraAdapter(),
    )

    request = GenerationRequest(
        tenant_id="tenant_test",
        application_id="app_test",
        prompt="Generate a page object for the checkout page",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="checkout"),
        provider=ProviderSelection(provider_id="stub", model="stub"),
        options=GenerationOptions(validate=False, max_input_tokens=12_000),
        jira_key="PROJ-123",
    )
    result = orchestrator.generate(request)

    assert result.status == GenerationStatus.COMPLETED


def test_rag_fetch_fail_open(tmp_path: Path) -> None:
    """When RAG store raises, orchestrator logs a warning and continues normally."""

    class _ErrorRagStore:
        def retrieve(self, query: str, tenant_id: str, limit: int = 5) -> list:
            raise RuntimeError("pgvector connection failed")

        def ingest(self, chunks: list) -> int:
            return 0

        def health(self) -> dict:
            return {"status": "error"}

    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "stub"}),
        adapters={"stub": StubMemoryAdapter([]), "null": NullMemoryAdapter()},
    )
    orchestrator = GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": StubProvider()}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
        rag_store=_ErrorRagStore(),
    )

    result = orchestrator.generate(_make_request())

    assert result.status == GenerationStatus.COMPLETED


# --- Repair transport failure test ---


class _FailOnRepairProvider(ProviderInterface):
    """Returns a valid-but-invalid artifact on the first call; raises ProviderNotFoundError on repair."""

    def __init__(self) -> None:
        self.call_count = 0

    @property
    def provider_id(self) -> str:
        return "stub"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.call_count += 1
        if self.call_count == 1:
            payload = _INVALID_ARTIFACT
        else:
            raise ProviderNotFoundError("repair provider unavailable")
        return ProviderResponse(
            request_id=request.request_id,
            provider_id="stub",
            model=request.config.model,
            raw_text=json.dumps(payload),
            usage=ProviderUsage(input_tokens=10, output_tokens=10),
            finish_reason=ProviderFinishReason.STOP,
            latency_ms=0,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider_id="stub", status=ProviderHealthStatus.OK, model="stub")


def test_repair_keeps_original_result_on_provider_not_found(tmp_path: Path) -> None:
    """When repair call raises ProviderNotFoundError, original failed validation result is preserved."""
    provider = _FailOnRepairProvider()
    skill_registry = _make_registry_with_validator(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "null"}),
        adapters={"null": NullMemoryAdapter()},
    )
    orchestrator = GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": provider}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
    )

    result = orchestrator.generate(_make_repair_request(allow_repair=True))

    assert result.validation.status == ValidationStatus.FAILED
    assert provider.call_count == 2


# --- Testgen path tests ---


def _make_testgen_orchestrator(tmp_path: Path) -> GenerationOrchestrator:
    from totalrecall.testgen.pack.normalizer import TestCasePackNormalizer
    from totalrecall.testgen.prompts.testgen_builder import TestGenPromptBuilder
    from totalrecall.testgen.reformulator import KeywordReformulator
    from totalrecall.testgen.routing.router import TestTypeRouter

    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "null"}),
        adapters={"null": NullMemoryAdapter()},
    )
    return GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": StubProvider()}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
        reformulator=KeywordReformulator(),
        test_type_router=TestTypeRouter(),
        testgen_prompt_builder=TestGenPromptBuilder(),
        testgen_normalizer=TestCasePackNormalizer(),
    )


def _make_testgen_request(allow_repair: bool = False) -> GenerationRequest:
    from totalrecall.testgen.models import TestType

    return GenerationRequest(
        tenant_id="tenant_test",
        application_id="app_test",
        prompt="Generate negative test cases for login",
        target=GenerationTarget(
            language=Language.TYPESCRIPT,
            framework=Framework.PLAYWRIGHT,
            pattern=AutomationPattern.POM,
            locator_strategy=LocatorStrategy.PAGE_FILE,
        ),
        scope=GenerationScope(domain="auth"),
        provider=ProviderSelection(provider_id="stub", model="stub"),
        options=GenerationOptions(validate=True, allow_repair=allow_repair, max_input_tokens=12_000),
        test_types=[TestType.NEGATIVE],
    )


def test_testgen_path_completes_with_test_case_pack(tmp_path: Path) -> None:
    """Testgen request with test_types produces COMPLETED with test_case_pack and no artifacts."""
    orchestrator = _make_testgen_orchestrator(tmp_path)
    result = orchestrator.generate(_make_testgen_request())

    assert result.status == GenerationStatus.COMPLETED
    assert result.test_case_pack is not None
    assert len(result.artifacts) == 0


def test_testgen_path_skips_artifact_validation(tmp_path: Path) -> None:
    """Validation must not run on the testgen path — test_case_pack has no code artifacts to validate."""
    orchestrator = _make_testgen_orchestrator(tmp_path)
    result = orchestrator.generate(_make_testgen_request())

    assert result.validation.status == ValidationStatus.NOT_RUN


def test_testgen_path_with_allow_repair_does_not_trigger_repair(tmp_path: Path) -> None:
    """When allow_repair=True on a testgen request, the repair path must not run.

    The stub provider is called exactly once. Previously, the repair path would run because
    artifacts=[] caused ValidationCoordinator to return FAILED, then repair would invoke
    ResponseNormalizer on testcase-pack format, producing a VALIDATION_FAILED error.
    """
    call_count = 0
    real_stub = StubProvider()

    class _CountingProvider(ProviderInterface):
        @property
        def provider_id(self) -> str:
            return "stub"

        def generate(self, request: ProviderRequest) -> ProviderResponse:
            nonlocal call_count
            call_count += 1
            return real_stub.generate(request)

        def health(self) -> ProviderHealth:
            return real_stub.health()

    from totalrecall.testgen.pack.normalizer import TestCasePackNormalizer
    from totalrecall.testgen.prompts.testgen_builder import TestGenPromptBuilder
    from totalrecall.testgen.reformulator import KeywordReformulator
    from totalrecall.testgen.routing.router import TestTypeRouter

    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "null"}),
        adapters={"null": NullMemoryAdapter()},
    )
    orchestrator = GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": _CountingProvider()}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
        reformulator=KeywordReformulator(),
        test_type_router=TestTypeRouter(),
        testgen_prompt_builder=TestGenPromptBuilder(),
        testgen_normalizer=TestCasePackNormalizer(),
    )

    result = orchestrator.generate(_make_testgen_request(allow_repair=True))

    assert result.status == GenerationStatus.COMPLETED
    assert result.test_case_pack is not None
    assert len(result.errors) == 0
    assert call_count == 1


def test_testgen_path_returns_failed_when_normalizer_errors(tmp_path: Path) -> None:
    """When TestCasePackNormalizer fails (bad JSON), testgen request returns FAILED with errors."""
    from totalrecall.testgen.pack.normalizer import TestCasePackNormalizer
    from totalrecall.testgen.prompts.testgen_builder import TestGenPromptBuilder
    from totalrecall.testgen.reformulator import KeywordReformulator
    from totalrecall.testgen.routing.router import TestTypeRouter

    skill_registry = _make_registry(tmp_path)
    memory_wrapper = MemoryWrapper(
        feature_flags=ConfigFeatureFlagProvider({"memory.adapter": "null"}),
        adapters={"null": NullMemoryAdapter()},
    )
    orchestrator = GenerationOrchestrator(
        planner=ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        prompt_builder=PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper),
        gateway=ProviderGateway(providers={"stub": StubProvider(fixed_response={"bad": "json"})}),
        normalizer=ResponseNormalizer(),
        validator=ValidationCoordinator(),
        skill_registry=skill_registry,
        reformulator=KeywordReformulator(),
        test_type_router=TestTypeRouter(),
        testgen_prompt_builder=TestGenPromptBuilder(),
        testgen_normalizer=TestCasePackNormalizer(),
    )

    result = orchestrator.generate(_make_testgen_request())

    assert result.status == GenerationStatus.FAILED
    assert len(result.errors) >= 1
    assert result.test_case_pack is None
