import json
from pathlib import Path

from totalrecall.config.feature_flags import ConfigFeatureFlagProvider
from totalrecall.context.planner import ContextPlanner
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
from totalrecall.providers.gateway import ProviderGateway
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
