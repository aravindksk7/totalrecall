"""Generation orchestrator: ties context planning, prompt building, provider, and validation."""

import uuid
from typing import TYPE_CHECKING

from totalrecall.context.models import ContextExclusionReason
from totalrecall.context.planner import ContextPlanner, ExternalPlanInputs
from totalrecall.errors import ServiceError, ServiceErrorCode
from totalrecall.generation.models import (
    GenerationContextMetadata,
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    ValidationStatus,
)
from totalrecall.prompts.builder import PromptBuilder
from totalrecall.prompts.redactor import redact_messages
from totalrecall.prompts.repair import build_repair_messages
from totalrecall.providers.gateway import ProviderGateway, ProviderNotFoundError
from totalrecall.providers.models import ProviderConfig, ProviderRequest
from totalrecall.providers.normalizer import ResponseNormalizer
from totalrecall.skills.registry import SkillRegistry
from totalrecall.testgen.guardrails.input_guardrail import InputGuardrailAdapter
from totalrecall.testgen.guardrails.output_guardrail import OutputGuardrailAdapter
from totalrecall.testgen.jira.adapter import JiraAdapterProtocol
from totalrecall.testgen.pack.normalizer import TestCasePackNormalizer
from totalrecall.testgen.prompts.testgen_builder import TestGenPromptBuilder
from totalrecall.testgen.rag.store import RagStoreProtocol
from totalrecall.testgen.reformulator import ReformulatorAdapter
from totalrecall.testgen.routing.router import TestTypeRouter
from totalrecall.testgen.tone.checker import ToneCheckAdapter
from totalrecall.validation.coordinator import ValidationCoordinator

if TYPE_CHECKING:
    from totalrecall.testgen.models import ReformulatedIntent


class GenerationOrchestrator:
    """Runs the full generation pipeline for a single GenerationRequest."""

    def __init__(
        self,
        planner: ContextPlanner,
        prompt_builder: PromptBuilder,
        gateway: ProviderGateway,
        normalizer: ResponseNormalizer,
        validator: ValidationCoordinator,
        skill_registry: SkillRegistry,
        *,
        reformulator: ReformulatorAdapter | None = None,
        input_guardrail: InputGuardrailAdapter | None = None,
        output_guardrail: OutputGuardrailAdapter | None = None,
        jira_adapter: JiraAdapterProtocol | None = None,
        rag_store: RagStoreProtocol | None = None,
        test_type_router: TestTypeRouter | None = None,
        testgen_prompt_builder: TestGenPromptBuilder | None = None,
        tone_checker: ToneCheckAdapter | None = None,
        testgen_normalizer: TestCasePackNormalizer | None = None,
    ) -> None:
        self._planner = planner
        self._prompt_builder = prompt_builder
        self._gateway = gateway
        self._normalizer = normalizer
        self._validator = validator
        self._skills = skill_registry
        self._reformulator = reformulator
        self._input_guardrail = input_guardrail
        self._output_guardrail = output_guardrail
        self._jira_adapter = jira_adapter
        self._rag_store = rag_store
        self._test_type_router = test_type_router
        self._testgen_prompt_builder = testgen_prompt_builder
        self._tone_checker = tone_checker
        self._testgen_normalizer = testgen_normalizer

    def generate(self, request: GenerationRequest) -> GenerationResult:
        request_id = str(uuid.uuid4())

        # 0. Reformulate free-text prompt into structured intent when testgen fields are present
        intent: ReformulatedIntent | None = None
        if self._reformulator is not None and (request.jira_key or request.test_types):
            intent = self._reformulator.reformulate(
                request.prompt,
                request.jira_key,
                request.test_types,
            )

        # 1. Input guardrail — short-circuit before any LLM calls
        if self._input_guardrail is not None:
            guard_result = self._input_guardrail.check(request, intent)
            if not guard_result.passed:
                return GenerationResult(
                    request_id=request_id,
                    status=GenerationStatus.FAILED,
                    errors=[
                        ServiceError(
                            code=ServiceErrorCode.GUARDRAIL_BLOCKED,
                            message=v.message,
                        )
                        for v in guard_result.violations
                    ],
                )

        # 2. Parallel fetch: JIRA story + RAG chunks (fail-open on any error)
        import logging
        from concurrent.futures import ThreadPoolExecutor

        _log = logging.getLogger(__name__)
        jira_story = None
        rag_chunks: list = []

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures: dict[str, object] = {}
            if self._jira_adapter is not None and request.jira_key:
                futures["jira"] = executor.submit(
                    self._jira_adapter.fetch_story, request.jira_key
                )
            if self._rag_store is not None:
                futures["rag"] = executor.submit(
                    self._rag_store.retrieve, request.prompt, request.tenant_id, 5
                )
            if "jira" in futures:
                try:
                    jira_story = futures["jira"].result(timeout=15)  # type: ignore[union-attr]
                except Exception as exc:
                    _log.warning("JIRA fetch failed (fail-open): %s", exc)
            if "rag" in futures:
                try:
                    rag_chunks = futures["rag"].result(timeout=10)  # type: ignore[union-attr]
                except Exception as exc:
                    _log.warning("RAG fetch failed (fail-open): %s", exc)

        plan_inputs = ExternalPlanInputs(jira_story=jira_story, rag_chunks=rag_chunks)

        # 3. Build context plan
        plan = self._planner.plan(request, request_id, plan_inputs=plan_inputs)

        # 4. Build prompt messages — testgen path when intent is present, otherwise legacy codegen
        if (
            intent is not None
            and self._test_type_router is not None
            and self._testgen_prompt_builder is not None
        ):
            active_test_types = self._test_type_router.route(intent, request)
            messages = self._testgen_prompt_builder.build(request, plan, intent, active_test_types)
        else:
            active_test_types = []
            messages = self._prompt_builder.build(request, plan)

        # 5. Redact secrets from user-supplied prompt content before dispatch
        messages, _ = redact_messages(messages)

        # 4. Call provider via gateway
        provider_request = ProviderRequest(
            request_id=request_id,
            tenant_id=request.tenant_id,
            messages=messages,
            config=ProviderConfig(
                provider_id=request.provider.provider_id,
                model=request.provider.model,
                max_output_tokens=request.options.max_output_tokens,
            ),
        )

        try:
            provider_response = self._gateway.generate(
                provider_request,
                fallback_provider_ids=request.provider.fallback_provider_ids or None,
            )
        except ProviderNotFoundError as exc:
            return GenerationResult(
                request_id=request_id,
                status=GenerationStatus.FAILED,
                errors=[
                    ServiceError(
                        code=ServiceErrorCode.PROVIDER_UNAVAILABLE,
                        message=str(exc),
                    )
                ],
            )

        # 4a. Output guardrail — runs on raw LLM text before normalization
        if self._output_guardrail is not None:
            out_guard = self._output_guardrail.check(provider_response.raw_text)
            if not out_guard.passed:
                return GenerationResult(
                    request_id=request_id,
                    status=GenerationStatus.FAILED,
                    errors=[
                        ServiceError(
                            code=ServiceErrorCode.GUARDRAIL_BLOCKED,
                            message=v.message,
                        )
                        for v in out_guard.violations
                    ],
                )

        # 4b. Tone check — optional LLM refine pass; replaces raw_text in-place
        if self._tone_checker is not None:
            refined_text, _ = self._tone_checker.refine(provider_response.raw_text, request_id)
            provider_response = provider_response.model_copy(update={"raw_text": refined_text})

        # 5. Normalize response.
        # Testgen uses TestCasePackNormalizer; codegen uses ResponseNormalizer.
        test_case_pack = None
        if intent is not None and self._testgen_normalizer is not None:
            jira_key = request.jira_key if hasattr(request, "jira_key") else None
            test_case_pack, norm_errors = self._testgen_normalizer.normalize(
                provider_response.raw_text, source_jira_key=jira_key
            )
            artifacts = []
        else:
            artifacts, norm_errors = self._normalizer.normalize(provider_response)

        # 6. Validate artifacts if enabled
        from totalrecall.generation.models import ValidationSummary

        skill = (
            self._skills.select(request.target.language, request.target.framework)
            if request.options.validation_enabled
            else None
        )
        validation = ValidationSummary(status=ValidationStatus.NOT_RUN)
        if request.options.validation_enabled:
            validation = self._validator.validate(artifacts, skill)

        # 5a. Single-pass repair when validation fails and the caller opted in
        if (
            request.options.allow_repair
            and validation.status == ValidationStatus.FAILED
            and validation.diagnostics
        ):
            repair_messages = build_repair_messages(
                messages, provider_response.raw_text, validation.diagnostics
            )
            repair_provider_request = ProviderRequest(
                request_id=request_id,
                tenant_id=request.tenant_id,
                messages=repair_messages,
                config=ProviderConfig(
                    provider_id=request.provider.provider_id,
                    model=request.provider.model,
                    max_output_tokens=request.options.max_output_tokens,
                ),
            )
            try:
                repair_response = self._gateway.generate(
                    repair_provider_request,
                    fallback_provider_ids=request.provider.fallback_provider_ids or None,
                )
                repair_artifacts, repair_norm_errors = self._normalizer.normalize(repair_response)
                repair_validation = ValidationSummary(status=ValidationStatus.NOT_RUN)
                if request.options.validation_enabled:
                    repair_validation = self._validator.validate(repair_artifacts, skill)
                artifacts = repair_artifacts
                norm_errors = repair_norm_errors
                validation = repair_validation
            except ProviderNotFoundError:
                pass  # keep original validation result on repair transport failure

        # 6. Assemble result
        all_errors = norm_errors
        has_failures = bool(all_errors) or validation.status == ValidationStatus.FAILED
        if has_failures and not artifacts:
            status = GenerationStatus.FAILED
        else:
            status = GenerationStatus.COMPLETED
        excluded_memory_count = sum(
            1
            for exclusion in plan.excluded
            if exclusion.reason == ContextExclusionReason.TOKEN_BUDGET
        )
        token_savings_percent = (
            round(
                (
                    plan.token_budget.estimated_tokens_saved
                    / plan.token_budget.baseline_estimate
                )
                * 100,
                2,
            )
            if plan.token_budget.baseline_estimate
            else 0.0
        )

        return GenerationResult(
            request_id=request_id,
            status=status,
            artifacts=artifacts,
            test_case_pack=test_case_pack,
            validation=validation,
            context=GenerationContextMetadata(
                context_plan_id=plan.context_plan_id,
                skill_ids=plan.skill_ids,
                memory_ids=plan.memory_ids,
                estimated_input_tokens=plan.token_budget.estimated_input_tokens,
                baseline_input_tokens=plan.token_budget.baseline_estimate,
                estimated_tokens_saved=plan.token_budget.estimated_tokens_saved,
                token_savings_percent=token_savings_percent,
                excluded_memory_count=excluded_memory_count,
                max_input_tokens=plan.token_budget.max_input_tokens,
            ),
            errors=all_errors,
        )
