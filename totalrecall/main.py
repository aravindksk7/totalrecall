from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from totalrecall import __version__
from totalrecall.api.routes import (
    catalogue,
    credentials,
    generations,
    health,
    learning,
    memories,
    monitoring,
    skills,
    system,
)
from totalrecall.auth.provider import ConfigAuthProvider
from totalrecall.cache.provider import TTLCache
from totalrecall.config.factory import build_credential_provider, build_feature_flag_provider
from totalrecall.config.runtime_credentials import RuntimeCredentialStore
from totalrecall.config.runtime_flags import RuntimeFeatureFlagStore
from totalrecall.config.settings import Settings
from totalrecall.context.planner import ContextPlanner
from totalrecall.generation.orchestrator import GenerationOrchestrator
from totalrecall.memory.factory import build_memory_wrapper
from totalrecall.memory.tombstone import TombstoneFilter
from totalrecall.observability.metrics import GenerationMetrics
from totalrecall.observability.middleware import RequestIdMiddleware
from totalrecall.prompts.builder import PromptBuilder
from totalrecall.providers.gateway import ProviderGateway
from totalrecall.providers.local.provider import LocalProvider
from totalrecall.providers.normalizer import ResponseNormalizer
from totalrecall.providers.openai.provider import OpenAIProvider
from totalrecall.providers.stub.provider import StubProvider
from totalrecall.ratelimit.provider import RateLimitProvider
from totalrecall.skills.registry import SkillRegistry
from totalrecall.storage.audit_repo import PostgresAuditRepository
from totalrecall.storage.catalogue_repo import PostgresCatalogueRepository
from totalrecall.storage.context_repo import PostgresContextSnapshotRepository
from totalrecall.storage.learning_repo import PostgresLearningRepository
from totalrecall.storage.pool import close_pool, create_pool
from totalrecall.storage.provider_mapping_repo import PostgresProviderMappingRepository
from totalrecall.storage.skill_governance_repo import PostgresSkillGovernanceRepository
from totalrecall.storage.tombstone_repo import PostgresTombstoneRepository
from totalrecall.validation.coordinator import ValidationCoordinator
from totalrecall.validation.worker import SubprocessPlaywrightWorkerClient


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # --- startup ---
        pool = None
        if resolved_settings.enable_database:
            pool = await create_pool(resolved_settings.database_url)
        app.state.pool = pool

        tombstone_filter: TombstoneFilter = app.state.tombstone_filter
        if pool is not None:
            tombstone_repo = PostgresTombstoneRepository(pool)
            existing = await tombstone_repo.load_all()
            tombstone_filter.load_bulk(existing)
            app.state.tombstone_repo = tombstone_repo
            app.state.audit_repo = PostgresAuditRepository(pool)
            app.state.catalogue_repo = PostgresCatalogueRepository(pool)
            app.state.learning_repo = PostgresLearningRepository(pool)
            app.state.context_snapshot_repo = PostgresContextSnapshotRepository(pool)
            app.state.provider_mapping_repo = PostgresProviderMappingRepository(pool)
            governance_repo = PostgresSkillGovernanceRepository(pool)
            app.state.skill_governance_repo = governance_repo
            raw_overrides = await governance_repo.load_overrides()
            from totalrecall.skills.models import SkillStatus

            skill_registry.apply_governance_overrides(
                {
                    sid: SkillStatus(s)
                    for sid, s in raw_overrides.items()
                    if s in SkillStatus.__members__.values()
                }
            )
        else:
            app.state.tombstone_repo = None
            app.state.audit_repo = None
            app.state.catalogue_repo = None
            app.state.learning_repo = None
            app.state.context_snapshot_repo = None
            app.state.skill_governance_repo = None
            app.state.provider_mapping_repo = None

        yield

        # --- shutdown ---
        await close_pool(pool)

    app = FastAPI(title=resolved_settings.service_name, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    app.state.settings = resolved_settings
    app.state.runtime_credential_store = RuntimeCredentialStore(
        resolved_settings.local_secrets_dir
    )
    app.state.runtime_feature_flag_store = RuntimeFeatureFlagStore(
        resolved_settings.local_secrets_dir
    )
    feature_flags = build_feature_flag_provider(
        resolved_settings,
        app.state.runtime_feature_flag_store,
    )
    app.state.feature_flags = feature_flags
    app.state.credential_provider = build_credential_provider(
        resolved_settings,
        app.state.runtime_credential_store,
    )
    app.state.auth_provider = ConfigAuthProvider(resolved_settings.auth_tokens)

    # Tombstone filter (populated from DB in lifespan)
    tombstone_filter = TombstoneFilter()
    app.state.tombstone_filter = tombstone_filter

    # Skill registry
    skill_registry = SkillRegistry(resolved_settings.skills_dir)
    if resolved_settings.skills_dir.exists():
        skill_registry.load()
    app.state.skill_registry = skill_registry

    # Cache (created before MemoryWrapper so it can be passed in)
    cache = TTLCache(ttl_seconds=resolved_settings.cache_ttl_seconds)
    app.state.cache = cache

    # Memory wrapper
    memory_wrapper = build_memory_wrapper(
        settings=resolved_settings,
        feature_flags=feature_flags,
        credential_provider=app.state.credential_provider,
        tombstone_filter=tombstone_filter,
        cache=cache,
    )
    app.state.memory_wrapper = memory_wrapper

    # Generation pipeline
    planner = ContextPlanner(skill_registry=skill_registry, memory_wrapper=memory_wrapper)
    prompt_builder = PromptBuilder(skill_registry=skill_registry, memory_wrapper=memory_wrapper)
    gateway = ProviderGateway(
        providers={
            "stub": StubProvider(),
            "openai": OpenAIProvider(app.state.credential_provider),
            "local": LocalProvider(app.state.credential_provider),
        }
    )
    app.state.provider_gateway = gateway
    normalizer = ResponseNormalizer()
    playwright_worker = None
    if resolved_settings.playwright_worker_command:
        playwright_worker = SubprocessPlaywrightWorkerClient(
            resolved_settings.playwright_worker_command,
            timeout_seconds=resolved_settings.playwright_worker_timeout_seconds,
        )
    validator = ValidationCoordinator(playwright_worker=playwright_worker)

    # Testgen components (all feature-flag gated, default off)
    from totalrecall.testgen.guardrails.input_guardrail import (
        NullInputGuardrail,
        RuleBasedInputGuardrail,
    )
    from totalrecall.testgen.guardrails.output_guardrail import (
        NullOutputGuardrail,
        RuleBasedOutputGuardrail,
    )
    from totalrecall.testgen.jira.factory import build_jira_adapter
    from totalrecall.testgen.pack.normalizer import TestCasePackNormalizer
    from totalrecall.testgen.prompts.testgen_builder import TestGenPromptBuilder
    from totalrecall.testgen.rag.factory import build_rag_store
    from totalrecall.testgen.reformulator_factory import build_reformulator
    from totalrecall.testgen.routing.router import TestTypeRouter
    from totalrecall.testgen.tone.factory import build_tone_checker

    reformulator = build_reformulator(feature_flags, gateway)
    jira_adapter = build_jira_adapter(feature_flags, app.state.credential_provider)
    rag_store = build_rag_store(feature_flags, app.state.credential_provider)

    input_guardrail = (
        RuleBasedInputGuardrail()
        if feature_flags.get_bool("guardrails.input_enabled", False)
        else NullInputGuardrail()
    )
    output_guardrail = (
        RuleBasedOutputGuardrail()
        if feature_flags.get_bool("guardrails.output_enabled", False)
        else NullOutputGuardrail()
    )
    tone_checker = build_tone_checker(feature_flags, gateway)

    app.state.generation_orchestrator = GenerationOrchestrator(
        planner=planner,
        prompt_builder=prompt_builder,
        gateway=gateway,
        normalizer=normalizer,
        validator=validator,
        skill_registry=skill_registry,
        reformulator=reformulator,
        input_guardrail=input_guardrail,
        output_guardrail=output_guardrail,
        jira_adapter=jira_adapter,
        rag_store=rag_store,
        test_type_router=TestTypeRouter(),
        testgen_prompt_builder=TestGenPromptBuilder(),
        tone_checker=tone_checker,
        testgen_normalizer=TestCasePackNormalizer(),
    )

    app.state.metrics = GenerationMetrics()
    app.state.rate_limit_provider = RateLimitProvider.from_config(resolved_settings.rate_limits)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(system.router, prefix="/v1")
    app.include_router(generations.router, prefix="/v1")
    app.include_router(catalogue.router, prefix="/v1")
    app.include_router(memories.router, prefix="/v1")
    app.include_router(learning.router, prefix="/v1")
    app.include_router(skills.router, prefix="/v1")
    app.include_router(credentials.router, prefix="/v1")
    app.include_router(monitoring.router, prefix="/v1")

    return app


app = create_app()
