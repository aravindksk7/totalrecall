from typing import Annotated

import asyncpg
from fastapi import Header, HTTPException, Request, status

from totalrecall.auth.models import TenantContext
from totalrecall.auth.provider import AuthError, ConfigAuthProvider
from totalrecall.config.credentials import CredentialProvider
from totalrecall.config.feature_flags import FeatureFlagProvider
from totalrecall.config.settings import Settings
from totalrecall.memory.tombstone import TombstoneFilter
from totalrecall.storage.audit_repo import PostgresAuditRepository
from totalrecall.storage.catalogue_repo import PostgresCatalogueRepository
from totalrecall.storage.context_repo import PostgresContextSnapshotRepository
from totalrecall.storage.learning_repo import PostgresLearningRepository
from totalrecall.storage.skill_governance_repo import PostgresSkillGovernanceRepository
from totalrecall.storage.tombstone_repo import PostgresTombstoneRepository


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_feature_flags(request: Request) -> FeatureFlagProvider:
    return request.app.state.feature_flags


def get_credential_provider(request: Request) -> CredentialProvider:
    return request.app.state.credential_provider


def get_auth_provider(request: Request) -> ConfigAuthProvider:
    return request.app.state.auth_provider


def get_tombstone_filter(request: Request) -> TombstoneFilter:
    return request.app.state.tombstone_filter


def _require_pool(request: Request) -> asyncpg.Pool:
    pool = request.app.state.pool
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available.",
        )
    return pool


def get_tombstone_repo(request: Request) -> PostgresTombstoneRepository:
    repo = request.app.state.tombstone_repo
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available.",
        )
    return repo


def get_audit_repo(request: Request) -> PostgresAuditRepository:
    repo = request.app.state.audit_repo
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available.",
        )
    return repo


def get_catalogue_repo(request: Request) -> PostgresCatalogueRepository:
    repo = request.app.state.catalogue_repo
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available.",
        )
    return repo


def get_optional_audit_repo(request: Request) -> PostgresAuditRepository | None:
    return getattr(request.app.state, "audit_repo", None)


def get_optional_context_snapshot_repo(
    request: Request,
) -> PostgresContextSnapshotRepository | None:
    return getattr(request.app.state, "context_snapshot_repo", None)


def get_optional_skill_governance_repo(
    request: Request,
) -> PostgresSkillGovernanceRepository | None:
    return getattr(request.app.state, "skill_governance_repo", None)


def get_learning_repo(request: Request) -> PostgresLearningRepository:
    repo = request.app.state.learning_repo
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available.",
        )
    return repo


def get_tenant_context(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> TenantContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        return get_auth_provider(request).authenticate(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

