"""Unit tests for the learning promotion module."""

from totalrecall.catalogue.models import CatalogueCategory, CatalogueSource, CatalogueStatus
from totalrecall.learning.models import LearningDelta, LearningDeltaState, LearningDiscovery, LearningDiscoveryType
from totalrecall.learning.promotion import discovery_to_entry, should_promote


def _make_discovery(discovery_type: LearningDiscoveryType) -> LearningDiscovery:
    return LearningDiscovery(
        discovery_id="disc_001",
        discovery_type=discovery_type,
        delta=LearningDelta(state=LearningDeltaState.NEW, current_hash="abc123"),
        summary="page_object_class: LoginPage (python)",
        source=CatalogueSource(
            type="file_scan",
            reference="/test/page.py",
            file_path="/test/page.py",
            symbol_name="LoginPage",
        ),
        proposed_tags={"framework": "playwright"},
    )


def test_should_promote_static_skill_candidate() -> None:
    assert should_promote(_make_discovery(LearningDiscoveryType.STATIC_SKILL_CANDIDATE)) is True


def test_should_promote_dynamic_memory() -> None:
    assert should_promote(_make_discovery(LearningDiscoveryType.DYNAMIC_MEMORY)) is True


def test_should_not_promote_catalogue_reference() -> None:
    assert should_promote(_make_discovery(LearningDiscoveryType.CATALOGUE_REFERENCE)) is False


def test_discovery_to_entry_maps_static_skill_candidate() -> None:
    discovery = _make_discovery(LearningDiscoveryType.STATIC_SKILL_CANDIDATE)
    entry = discovery_to_entry(discovery, "tenant_1", "app_1", "actor_admin")

    assert entry.entity_id == "disc_001"
    assert entry.tenant_id == "tenant_1"
    assert entry.application_id == "app_1"
    assert entry.category == CatalogueCategory.STATIC_SKILL
    assert entry.status == CatalogueStatus.ACTIVE
    assert entry.summary == "page_object_class: LoginPage (python)"
    assert entry.tags == {"framework": "playwright"}
    assert entry.approved_by == "actor_admin"
    assert entry.approved_at is not None


def test_discovery_to_entry_maps_dynamic_memory() -> None:
    discovery = _make_discovery(LearningDiscoveryType.DYNAMIC_MEMORY)
    entry = discovery_to_entry(discovery, "tenant_1", "app_1", "actor_admin")

    assert entry.category == CatalogueCategory.DYNAMIC_MEMORY
    assert entry.status == CatalogueStatus.ACTIVE


def test_discovery_to_entry_copies_source() -> None:
    discovery = _make_discovery(LearningDiscoveryType.STATIC_SKILL_CANDIDATE)
    entry = discovery_to_entry(discovery, "tenant_1", "app_1", "actor_admin")

    assert entry.source is not None
    assert entry.source.file_path == "/test/page.py"
    assert entry.source.symbol_name == "LoginPage"
