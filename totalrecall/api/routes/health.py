from typing import Annotated

from fastapi import APIRouter, Depends

from totalrecall import __version__
from totalrecall.api.dependencies import get_settings
from totalrecall.config.settings import Settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "environment": settings.environment,
        "version": __version__,
    }
