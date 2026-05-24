from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import Field

from totalrecall.api.dependencies import get_tenant_context
from totalrecall.auth.models import TenantContext
from totalrecall.auth.permissions import MANAGE_CREDENTIALS, has_permission
from totalrecall.config.runtime_credentials import RuntimeCredentialStore
from totalrecall.config.runtime_flags import RuntimeFeatureFlagStore
from totalrecall.config.settings import Settings
from totalrecall.contracts import ContractModel
from totalrecall.selfhost.mem0 import Mem0SelfHostManager

router = APIRouter(tags=["mem0"])


class Mem0SelfHostStartRequest(ContractModel):
    openai_api_key: str = Field(min_length=1)
    mem0_admin_api_key: str = Field(min_length=1)
    mem0_jwt_secret: str = Field(min_length=16)
    mem0_host: str = Field(default="http://mem0:8000", min_length=1)
    start_containers: bool = True
    activate: bool = True


class Mem0SelfHostStartResponse(ContractModel):
    configured: bool
    started: bool
    start_status: str
    message: str
    env_file: str
    mem0_host: str
    command: list[str]
    runtime_flags: dict[str, object] = Field(default_factory=dict)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


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


@router.post("/mem0/self-hosted/start", response_model=Mem0SelfHostStartResponse)
def configure_and_start_self_hosted_mem0(
    body: Annotated[Mem0SelfHostStartRequest, Body()],
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    settings: Annotated[Settings, Depends(_settings)],
    store: Annotated[RuntimeCredentialStore, Depends(_credential_store)],
    feature_flags: Annotated[RuntimeFeatureFlagStore, Depends(_feature_flag_store)],
) -> Mem0SelfHostStartResponse:
    _require_manage_credentials(context)
    try:
        store.upsert("openai_api_key", body.openai_api_key)
        store.upsert("mem0_api_key", body.mem0_admin_api_key)
        store.upsert("mem0_jwt_secret", body.mem0_jwt_secret)
        store.upsert("mem0_host", body.mem0_host)

        runtime_flags: dict[str, object] = {}
        if body.activate:
            feature_flags.set("memory.adapter", "mem0_v1")
            feature_flags.set("memory.write_enabled", True)
            feature_flags.set("memory.fail_open_on_search", True)
            runtime_flags = {
                "memory.adapter": "mem0_v1",
                "memory.write_enabled": True,
                "memory.fail_open_on_search": True,
            }

        manager = Mem0SelfHostManager(
            local_secrets_dir=settings.local_secrets_dir,
            project_dir=settings.docker_compose_project_dir,
            docker_control_enabled=settings.admin_docker_control_enabled,
            compose_command=settings.docker_compose_command,
            timeout_seconds=settings.docker_control_timeout_seconds,
        )
        result = manager.configure(
            openai_api_key=body.openai_api_key,
            mem0_admin_api_key=body.mem0_admin_api_key,
            mem0_jwt_secret=body.mem0_jwt_secret,
            start_containers=body.start_containers,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return Mem0SelfHostStartResponse(
        configured=True,
        started=result.started,
        start_status=result.start_status,
        message=result.message,
        env_file=str(result.env_file),
        mem0_host=body.mem0_host,
        command=result.command,
        runtime_flags=runtime_flags,
    )
