from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from totalrecall.api.dependencies import get_catalogue_repo, get_tenant_context
from totalrecall.auth.models import TenantContext
from totalrecall.catalogue.models import (
    CatalogueCategory,
    CatalogueEntry,
    CatalogueSearchFilters,
    CatalogueSearchResult,
    CatalogueStatus,
)
from totalrecall.storage.catalogue_repo import PostgresCatalogueRepository

router = APIRouter(tags=["catalogue"])


@router.get("/catalogue", response_model=CatalogueSearchResult)
async def search_catalogue(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    repo: Annotated[PostgresCatalogueRepository, Depends(get_catalogue_repo)],
    application_id: str | None = Query(default=None),  # noqa: B008
    category: CatalogueCategory | None = Query(default=None),  # noqa: B008
    status: CatalogueStatus | None = Query(default=None),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CatalogueSearchResult:
    filters = CatalogueSearchFilters(
        tenant_id=context.tenant_id,
        application_id=application_id,
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )
    return await repo.search(filters)


@router.get("/catalogue/{entity_id}", response_model=CatalogueEntry)
async def get_catalogue_entry(
    entity_id: str,
    context: Annotated[TenantContext, Depends(get_tenant_context)],
    repo: Annotated[PostgresCatalogueRepository, Depends(get_catalogue_repo)],
) -> CatalogueEntry:
    entry = await repo.get(context.tenant_id, entity_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catalogue entry '{entity_id}' not found.",
        )
    return entry
