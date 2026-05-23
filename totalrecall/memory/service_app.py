from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status

from totalrecall import __version__
from totalrecall.api.dependencies import get_tenant_context
from totalrecall.auth.models import TenantContext
from totalrecall.auth.permissions import DELETE_MEMORY, WRITE_MEMORY, has_permission
from totalrecall.auth.provider import ConfigAuthProvider
from totalrecall.cache.provider import TTLCache
from totalrecall.config.factory import build_credential_provider, build_feature_flag_provider
from totalrecall.config.runtime_credentials import RuntimeCredentialStore
from totalrecall.config.runtime_flags import RuntimeFeatureFlagStore
from totalrecall.config.settings import Settings
from totalrecall.memory.factory import build_memory_wrapper
from totalrecall.memory.models import (
    MemoryCapabilities,
    MemoryDeleteRequest,
    MemoryDeleteResult,
    MemoryEntry,
    MemoryGetRequest,
    MemoryHealth,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryUpsertRequest,
)
from totalrecall.memory.tombstone import TombstoneFilter
from totalrecall.memory.wrapper.service import MemoryWrapper
from totalrecall.observability.middleware import RequestIdMiddleware
from totalrecall.storage.pool import close_pool, create_pool
from totalrecall.storage.tombstone_repo import PostgresTombstoneRepository

router = APIRouter(tags=["memory-wrapper"])


def _get_memory_wrapper(request: Request) -> MemoryWrapper:
    return request.app.state.memory_wrapper


def _require_tenant(context: TenantContext, tenant_id: str) -> None:
    if context.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request tenant_id does not match authenticated tenant.",
        )


def _require_permission(context: TenantContext, permission: str) -> None:
    if not has_permission(context.roles, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{permission}' required.",
        )


@router.post("/memory/search", response_model=MemorySearchResult)
def search_memory(
    body: MemorySearchRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    wrapper: Annotated[MemoryWrapper, Depends(_get_memory_wrapper)],
) -> MemorySearchResult:
    _require_tenant(context, body.tenant_id)
    return wrapper.search(body)


@router.post("/memory/get", response_model=MemoryEntry | None)
def get_memory(
    body: MemoryGetRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    wrapper: Annotated[MemoryWrapper, Depends(_get_memory_wrapper)],
) -> MemoryEntry | None:
    _require_tenant(context, body.tenant_id)
    return wrapper.get(body)


@router.post("/memory/upsert", response_model=MemoryEntry)
def upsert_memory(
    body: MemoryUpsertRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    wrapper: Annotated[MemoryWrapper, Depends(_get_memory_wrapper)],
) -> MemoryEntry:
    _require_tenant(context, body.memory.tenant_id)
    _require_permission(context, WRITE_MEMORY)
    return wrapper.upsert(body)


@router.post("/memory/delete", response_model=MemoryDeleteResult)
def delete_memory(
    body: MemoryDeleteRequest,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    wrapper: Annotated[MemoryWrapper, Depends(_get_memory_wrapper)],
) -> MemoryDeleteResult:
    _require_tenant(context, body.tenant_id)
    _require_permission(context, DELETE_MEMORY)
    if body.deleted_by != context.actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="deleted_by must match authenticated actor.",
        )
    return wrapper.delete(body)


@router.get("/memory/health", response_model=MemoryHealth)
def memory_health(
    wrapper: Annotated[MemoryWrapper, Depends(_get_memory_wrapper)],
) -> MemoryHealth:
    return wrapper.health()


@router.get("/memory/capabilities", response_model=MemoryCapabilities)
def memory_capabilities(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    wrapper: Annotated[MemoryWrapper, Depends(_get_memory_wrapper)],
) -> MemoryCapabilities:
    _ = context
    return wrapper.capabilities()


def create_memory_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        pool = None
        if resolved_settings.enable_database:
            pool = await create_pool(resolved_settings.database_url)
        app.state.pool = pool

        if pool is not None:
            tombstone_repo = PostgresTombstoneRepository(pool)
            existing = await tombstone_repo.load_all()
            app.state.tombstone_filter.load_bulk(existing)
            app.state.tombstone_repo = tombstone_repo
        else:
            app.state.tombstone_repo = None

        yield

        await close_pool(pool)

    app = FastAPI(
        title=f"{resolved_settings.service_name}-memory-wrapper",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.runtime_credential_store = RuntimeCredentialStore(
        resolved_settings.local_secrets_dir
    )
    app.state.runtime_feature_flag_store = RuntimeFeatureFlagStore(
        resolved_settings.local_secrets_dir
    )
    app.state.feature_flags = build_feature_flag_provider(
        resolved_settings,
        app.state.runtime_feature_flag_store,
    )
    app.state.credential_provider = build_credential_provider(
        resolved_settings,
        app.state.runtime_credential_store,
    )
    app.state.auth_provider = ConfigAuthProvider(resolved_settings.auth_tokens)
    app.state.tombstone_filter = TombstoneFilter()
    app.state.cache = TTLCache(ttl_seconds=resolved_settings.cache_ttl_seconds)
    app.state.memory_wrapper = build_memory_wrapper(
        settings=resolved_settings,
        feature_flags=app.state.feature_flags,
        credential_provider=app.state.credential_provider,
        tombstone_filter=app.state.tombstone_filter,
        cache=app.state.cache,
    )

    app.add_middleware(RequestIdMiddleware)

    @app.get("/health", response_model=MemoryHealth)
    def root_health() -> MemoryHealth:
        return app.state.memory_wrapper.health()

    app.include_router(router, prefix="/v1")
    return app


app = create_memory_app()
