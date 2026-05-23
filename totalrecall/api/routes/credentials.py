from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import Field

from totalrecall.api.dependencies import get_tenant_context
from totalrecall.auth.models import TenantContext
from totalrecall.auth.permissions import MANAGE_CREDENTIALS, has_permission
from totalrecall.config.runtime_credentials import RuntimeCredentialStore
from totalrecall.config.runtime_flags import RuntimeFeatureFlagStore
from totalrecall.contracts import ContractModel

router = APIRouter(tags=["credentials"])


class RuntimeCredentialStatus(ContractModel):
    key: str
    label: str
    platform: str
    usage: str
    provider_id: str | None = None
    memory_adapter: str | None = None
    env_var: str | None = None
    secret: bool
    configured: bool
    ref: str | None = None
    updated_at: str | None = None
    notes: str = ""


class RuntimeCredentialList(ContractModel):
    credentials: list[RuntimeCredentialStatus]
    total: int


class RuntimeCredentialUpsert(ContractModel):
    value: str
    activate: bool = False


class RuntimeCredentialMutationResponse(ContractModel):
    key: str
    configured: bool
    ref: str | None = None
    updated_at: str | None = None
    activated: bool = False
    runtime_flags: dict[str, object] = Field(default_factory=dict)


def _credential_store(request: Request) -> RuntimeCredentialStore:
    return request.app.state.runtime_credential_store


def _feature_flag_store(request: Request) -> RuntimeFeatureFlagStore:
    return request.app.state.runtime_feature_flag_store


def _require_manage_credentials(context: TenantContext) -> None:
    if not has_permission(context.roles, MANAGE_CREDENTIALS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{MANAGE_CREDENTIALS}' required.",
        )


@router.get("/credentials", response_model=RuntimeCredentialList)
def list_runtime_credentials(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    store: Annotated[RuntimeCredentialStore, Depends(_credential_store)],
) -> RuntimeCredentialList:
    _require_manage_credentials(context)
    credentials = [RuntimeCredentialStatus(**item) for item in store.list_statuses()]
    return RuntimeCredentialList(credentials=credentials, total=len(credentials))


@router.put("/credentials/{credential_key}", response_model=RuntimeCredentialMutationResponse)
def upsert_runtime_credential(
    credential_key: str,
    body: Annotated[RuntimeCredentialUpsert, Body()],
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    store: Annotated[RuntimeCredentialStore, Depends(_credential_store)],
    feature_flags: Annotated[RuntimeFeatureFlagStore, Depends(_feature_flag_store)],
) -> RuntimeCredentialMutationResponse:
    _require_manage_credentials(context)
    try:
        result = store.upsert(credential_key, body.value)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    runtime_flags: dict[str, object] = {}
    activated = False
    if body.activate and credential_key == "mem0_api_key":
        feature_flags.set("memory.adapter", "mem0_v1")
        feature_flags.set("memory.write_enabled", True)
        feature_flags.set("memory.fail_open_on_search", True)
        runtime_flags = {
            "memory.adapter": "mem0_v1",
            "memory.write_enabled": True,
            "memory.fail_open_on_search": True,
        }
        activated = True

    return RuntimeCredentialMutationResponse(
        key=result["key"],
        configured=True,
        ref=result["ref"],
        updated_at=result["updated_at"],
        activated=activated,
        runtime_flags=runtime_flags,
    )


@router.delete("/credentials/{credential_key}", response_model=RuntimeCredentialMutationResponse)
def delete_runtime_credential(
    credential_key: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    store: Annotated[RuntimeCredentialStore, Depends(_credential_store)],
) -> RuntimeCredentialMutationResponse:
    _require_manage_credentials(context)
    try:
        result = store.delete(credential_key)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RuntimeCredentialMutationResponse(
        key=result["key"],
        configured=False,
    )
