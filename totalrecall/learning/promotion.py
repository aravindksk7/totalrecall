"""Promotion helpers: approved LearningDiscovery → active CatalogueEntry."""

from datetime import UTC, datetime

from totalrecall.catalogue.models import CatalogueCategory, CatalogueEntry, CatalogueStatus
from totalrecall.learning.models import LearningDiscovery, LearningDiscoveryType

_TYPE_TO_CATEGORY: dict[LearningDiscoveryType, CatalogueCategory] = {
    LearningDiscoveryType.STATIC_SKILL_CANDIDATE: CatalogueCategory.STATIC_SKILL,
    LearningDiscoveryType.DYNAMIC_MEMORY: CatalogueCategory.DYNAMIC_MEMORY,
    LearningDiscoveryType.CATALOGUE_REFERENCE: CatalogueCategory.LEARNING_REFERENCE,
}

_PROMOTABLE = frozenset(
    {
        LearningDiscoveryType.STATIC_SKILL_CANDIDATE,
        LearningDiscoveryType.DYNAMIC_MEMORY,
    }
)


def should_promote(discovery: LearningDiscovery) -> bool:
    return discovery.discovery_type in _PROMOTABLE


def discovery_to_entry(
    discovery: LearningDiscovery,
    tenant_id: str,
    application_id: str,
    approved_by: str,
) -> CatalogueEntry:
    now = datetime.now(UTC)
    return CatalogueEntry(
        entity_id=discovery.discovery_id,
        tenant_id=tenant_id,
        application_id=application_id,
        category=_TYPE_TO_CATEGORY[discovery.discovery_type],
        status=CatalogueStatus.ACTIVE,
        summary=discovery.summary,
        tags=discovery.proposed_tags,
        source=discovery.source,
        approved_by=approved_by,
        approved_at=now,
        created_at=now,
        updated_at=now,
    )
