from typing import Annotated

from fastapi import APIRouter, Depends, Request

from totalrecall.api.dependencies import get_feature_flags, get_tenant_context
from totalrecall.auth.models import TenantContext
from totalrecall.config.feature_flags import ConfigFeatureFlagProvider

router = APIRouter(tags=["system"])


@router.get("/whoami")
def whoami(context: Annotated[TenantContext, Depends(get_tenant_context)]) -> dict[str, object]:
    return context.model_dump(mode="json")


@router.get("/flags")
def flags(
    request: Request,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    feature_flags: Annotated[ConfigFeatureFlagProvider, Depends(get_feature_flags)],
) -> dict[str, object]:
    return {
        "tenant_id": context.tenant_id,
        "actor_id": context.actor_id,
        "request_id": request.state.request_id,
        "flags": feature_flags.snapshot().model_dump(mode="json"),
    }


@router.get("/metrics")
def metrics(request: Request) -> dict[str, object]:
    """Return in-process generation counters (no auth required — same level as /health)."""
    m = getattr(request.app.state, "metrics", None)
    if m is None:
        return {}
    return m.snapshot()
