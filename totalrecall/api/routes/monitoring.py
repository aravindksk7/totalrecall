from importlib.util import find_spec
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from totalrecall.api.dependencies import get_feature_flags, get_tenant_context
from totalrecall.auth.models import TenantContext
from totalrecall.config.feature_flags import FeatureFlagProvider
from totalrecall.config.runtime_credentials import RuntimeCredentialStore
from totalrecall.contracts import ContractModel
from totalrecall.memory.models import MemoryCapabilities, MemoryHealth, MemoryHealthStatus
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.observability.metrics import GenerationMetrics
from totalrecall.providers.gateway import ProviderGateway

router = APIRouter(tags=["monitoring"])


class MemoryOperationStats(ContractModel):
    search_total: int = 0
    search_success_total: int = 0
    search_failure_total: int = 0
    search_cache_hit_total: int = 0
    average_search_latency_ms: float = 0.0
    get_total: int = 0
    get_success_total: int = 0
    get_failure_total: int = 0
    average_get_latency_ms: float = 0.0
    upsert_total: int = 0
    upsert_success_total: int = 0
    upsert_failure_total: int = 0
    average_upsert_latency_ms: float = 0.0
    delete_total: int = 0
    delete_success_total: int = 0
    delete_failure_total: int = 0
    average_delete_latency_ms: float = 0.0
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_error_type: str | None = None


class Mem0MonitorStatus(ContractModel):
    credential_configured: bool
    active: bool
    sdk_available: bool
    status: str
    write_enabled: bool
    fail_open_on_search: bool
    supports_search: bool
    supports_get: bool
    supports_upsert: bool
    supports_delete: bool


class MemoryMonitorSnapshot(ContractModel):
    active_adapter: str
    configured_adapter: str
    health: MemoryHealth
    capabilities: MemoryCapabilities
    operations: MemoryOperationStats
    mem0: Mem0MonitorStatus


class ProviderMonitorStatus(ContractModel):
    provider_id: str
    registered: bool
    credential_configured: bool
    status: str
    model: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    error: str | None = None


class TokenEfficiencySnapshot(ContractModel):
    generations_total: int = 0
    input_tokens_total: int = 0
    output_tokens_total: int = 0
    estimated_tokens_saved_total: int = 0
    last_context_plan_id: str | None = None
    last_estimated_input_tokens: int = 0
    last_baseline_input_tokens: int = 0
    last_estimated_tokens_saved: int = 0
    last_token_savings_percent: float = 0.0
    last_selected_skill_count: int = 0
    last_selected_memory_count: int = 0
    last_excluded_memory_count: int = 0
    last_max_input_tokens: int = 0


class MonitoringSummary(ContractModel):
    status: str
    tenant_id: str
    actor_id: str
    memory: MemoryMonitorSnapshot
    providers: list[ProviderMonitorStatus]
    token_efficiency: TokenEfficiencySnapshot
    generation_metrics: dict[str, Any]


def _memory_wrapper(request: Request) -> MemoryWrapper:
    return request.app.state.memory_wrapper


def _credential_store(request: Request) -> RuntimeCredentialStore:
    return request.app.state.runtime_credential_store


def _provider_gateway(request: Request) -> ProviderGateway:
    return request.app.state.provider_gateway


def _generation_metrics(request: Request) -> GenerationMetrics | None:
    return getattr(request.app.state, "metrics", None)


def _credential_configured(store: RuntimeCredentialStore, key: str) -> bool:
    try:
        return store.has(key)
    except KeyError:
        return False


def _memory_snapshot(
    wrapper: MemoryWrapper,
    feature_flags: FeatureFlagProvider,
    store: RuntimeCredentialStore,
) -> MemoryMonitorSnapshot:
    health = wrapper.health()
    capabilities = wrapper.capabilities()
    configured_adapter = feature_flags.get_string("memory.adapter", "null")
    mem0_active = configured_adapter == "mem0_v1" or health.adapter_version == "mem0_v1"
    mem0_status = health.status.value if mem0_active else "inactive"
    return MemoryMonitorSnapshot(
        active_adapter=health.adapter_version,
        configured_adapter=configured_adapter,
        health=health,
        capabilities=capabilities,
        operations=MemoryOperationStats(**wrapper.operation_stats()),
        mem0=Mem0MonitorStatus(
            credential_configured=_credential_configured(store, "mem0_api_key"),
            active=mem0_active,
            sdk_available=find_spec("mem0") is not None,
            status=mem0_status,
            write_enabled=feature_flags.get_bool("memory.write_enabled", False),
            fail_open_on_search=feature_flags.get_bool("memory.fail_open_on_search", False),
            supports_search=capabilities.supports_search,
            supports_get=capabilities.supports_get,
            supports_upsert=capabilities.supports_upsert,
            supports_delete=capabilities.supports_delete,
        ),
    )


def _providers_snapshot(
    gateway: ProviderGateway,
    store: RuntimeCredentialStore,
) -> list[ProviderMonitorStatus]:
    registered_ids = set(gateway.registered_ids())
    definition_provider_ids = {
        definition.provider_id
        for definition in store.definitions()
        if definition.provider_id is not None
    }
    provider_ids = sorted(registered_ids | definition_provider_ids)
    statuses: list[ProviderMonitorStatus] = []
    for provider_id in provider_ids:
        credential_configured = any(
            definition.provider_id == provider_id and _credential_configured(store, definition.key)
            for definition in store.definitions()
        )
        if provider_id not in registered_ids:
            statuses.append(
                ProviderMonitorStatus(
                    provider_id=provider_id,
                    registered=False,
                    credential_configured=credential_configured,
                    status="unregistered",
                )
            )
            continue

        if not credential_configured and provider_id != "stub":
            statuses.append(
                ProviderMonitorStatus(
                    provider_id=provider_id,
                    registered=True,
                    credential_configured=False,
                    status="unconfigured",
                )
            )
            continue

        health = gateway.health(provider_id)
        statuses.append(
            ProviderMonitorStatus(
                provider_id=provider_id,
                registered=True,
                credential_configured=credential_configured,
                status=health.status.value,
                model=health.model,
                latency_ms=health.latency_ms,
                error=health.error.message if health.error else None,
            )
        )
    return statuses


def _token_efficiency_snapshot(metrics: GenerationMetrics | None) -> TokenEfficiencySnapshot:
    if metrics is None:
        return TokenEfficiencySnapshot()
    snapshot = metrics.snapshot()
    allowed = set(TokenEfficiencySnapshot.model_fields)
    return TokenEfficiencySnapshot(
        **{key: value for key, value in snapshot.items() if key in allowed}
    )


def _overall_status(
    memory: MemoryMonitorSnapshot,
    providers: list[ProviderMonitorStatus],
) -> str:
    if memory.health.status == MemoryHealthStatus.UNAVAILABLE:
        return "unavailable"
    configured_provider_degraded = any(
        provider.credential_configured
        and provider.registered
        and provider.status not in {"ok", "unregistered"}
        for provider in providers
    )
    if memory.health.degraded or memory.mem0.status == "degraded" or configured_provider_degraded:
        return "degraded"
    return "healthy"


@router.get("/monitoring/memory", response_model=MemoryMonitorSnapshot)
def memory_monitoring(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    request: Request,
    feature_flags: Annotated[FeatureFlagProvider, Depends(get_feature_flags)],
    wrapper: Annotated[MemoryWrapper, Depends(_memory_wrapper)],
    store: Annotated[RuntimeCredentialStore, Depends(_credential_store)],
) -> MemoryMonitorSnapshot:
    _ = context
    return _memory_snapshot(wrapper, feature_flags, store)


@router.get("/monitoring/providers", response_model=list[ProviderMonitorStatus])
def provider_monitoring(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    gateway: Annotated[ProviderGateway, Depends(_provider_gateway)],
    store: Annotated[RuntimeCredentialStore, Depends(_credential_store)],
) -> list[ProviderMonitorStatus]:
    _ = context
    return _providers_snapshot(gateway, store)


@router.get("/monitoring/token-efficiency", response_model=TokenEfficiencySnapshot)
def token_efficiency_monitoring(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    metrics: Annotated[GenerationMetrics | None, Depends(_generation_metrics)],
) -> TokenEfficiencySnapshot:
    _ = context
    return _token_efficiency_snapshot(metrics)


@router.get("/monitoring/summary", response_model=MonitoringSummary)
def monitoring_summary(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    request: Request,
    feature_flags: Annotated[FeatureFlagProvider, Depends(get_feature_flags)],
    wrapper: Annotated[MemoryWrapper, Depends(_memory_wrapper)],
    store: Annotated[RuntimeCredentialStore, Depends(_credential_store)],
    gateway: Annotated[ProviderGateway, Depends(_provider_gateway)],
    metrics: Annotated[GenerationMetrics | None, Depends(_generation_metrics)],
) -> MonitoringSummary:
    memory = _memory_snapshot(wrapper, feature_flags, store)
    providers = _providers_snapshot(gateway, store)
    token_efficiency = _token_efficiency_snapshot(metrics)
    generation_metrics = metrics.snapshot() if metrics is not None else {}
    return MonitoringSummary(
        status=_overall_status(memory, providers),
        tenant_id=context.tenant_id,
        actor_id=context.actor_id,
        memory=memory,
        providers=providers,
        token_efficiency=token_efficiency,
        generation_metrics=generation_metrics,
    )
