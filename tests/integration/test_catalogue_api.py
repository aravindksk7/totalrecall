"""Integration tests for GET /v1/catalogue and GET /v1/catalogue/{entity_id}."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from totalrecall.api.dependencies import get_catalogue_repo
from totalrecall.auth.models import AuthTokenConfig
from totalrecall.catalogue.models import (
    CatalogueCategory,
    CatalogueEntry,
    CatalogueSearchResult,
    CatalogueStatus,
)
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


def _make_settings() -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        auth_tokens={
            "test-admin": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
            "test-reader": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_reader",
                roles=["reader"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )


def _make_entry(entity_id: str = "entry_001") -> CatalogueEntry:
    return CatalogueEntry(
        entity_id=entity_id,
        tenant_id="tenant_test",
        application_id="app_test",
        category=CatalogueCategory.STATIC_SKILL,
        status=CatalogueStatus.ACTIVE,
        summary="Login page object",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_mock_repo(
    search_result: CatalogueSearchResult | None = None,
    get_result: CatalogueEntry | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.search = AsyncMock(
        return_value=search_result or CatalogueSearchResult(items=[], total=0)
    )
    repo.get = AsyncMock(return_value=get_result)
    return repo


@pytest.fixture
def client() -> Generator[TestClient]:
    settings = _make_settings()
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_with_entries() -> Generator[TestClient]:
    settings = _make_settings()
    app = create_app(settings)
    entry = _make_entry()
    mock_repo = _make_mock_repo(
        search_result=CatalogueSearchResult(items=[entry], total=1),
        get_result=entry,
    )
    app.dependency_overrides[get_catalogue_repo] = lambda: mock_repo
    with TestClient(app) as test_client:
        yield test_client


def test_search_catalogue_returns_503_when_db_unavailable(client) -> None:
    response = client.get("/v1/catalogue", headers={"Authorization": "Bearer test-admin"})

    assert response.status_code == 503


def test_search_catalogue_rejects_missing_auth(client_with_entries) -> None:
    response = client_with_entries.get("/v1/catalogue")

    assert response.status_code == 401


def test_search_catalogue_returns_200_with_items(client_with_entries) -> None:
    response = client_with_entries.get(
        "/v1/catalogue", headers={"Authorization": "Bearer test-admin"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["entity_id"] == "entry_001"


def test_search_catalogue_reader_can_access(client_with_entries) -> None:
    response = client_with_entries.get(
        "/v1/catalogue", headers={"Authorization": "Bearer test-reader"}
    )

    assert response.status_code == 200


def test_search_catalogue_passes_filters_to_repo() -> None:
    settings = _make_settings()
    app = create_app(settings)
    mock_repo = _make_mock_repo()
    app.dependency_overrides[get_catalogue_repo] = lambda: mock_repo

    with TestClient(app) as client:
        response = client.get(
            "/v1/catalogue",
            params={"application_id": "app_test", "limit": 10, "offset": 5},
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 200
    called_filters = mock_repo.search.call_args[0][0]
    assert called_filters.application_id == "app_test"
    assert called_filters.limit == 10
    assert called_filters.offset == 5
    assert called_filters.tenant_id == "tenant_test"


def test_search_catalogue_returns_empty_list(client_with_entries) -> None:
    settings = _make_settings()
    app = create_app(settings)
    empty_repo = _make_mock_repo(search_result=CatalogueSearchResult(items=[], total=0))
    app.dependency_overrides[get_catalogue_repo] = lambda: empty_repo

    with TestClient(app) as client:
        response = client.get("/v1/catalogue", headers={"Authorization": "Bearer test-admin"})

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_get_catalogue_entry_returns_200_when_found(client_with_entries) -> None:
    response = client_with_entries.get(
        "/v1/catalogue/entry_001", headers={"Authorization": "Bearer test-admin"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entity_id"] == "entry_001"
    assert body["category"] == "static_skill"
    assert body["status"] == "active"


def test_get_catalogue_entry_returns_404_when_not_found() -> None:
    settings = _make_settings()
    app = create_app(settings)
    mock_repo = _make_mock_repo(get_result=None)
    app.dependency_overrides[get_catalogue_repo] = lambda: mock_repo

    with TestClient(app) as client:
        response = client.get(
            "/v1/catalogue/missing_entry", headers={"Authorization": "Bearer test-admin"}
        )

    assert response.status_code == 404
    assert "missing_entry" in response.json()["detail"]


def test_get_catalogue_entry_returns_503_when_db_unavailable(client) -> None:
    response = client.get(
        "/v1/catalogue/entry_001", headers={"Authorization": "Bearer test-admin"}
    )

    assert response.status_code == 503


def test_get_catalogue_entry_rejects_missing_auth(client_with_entries) -> None:
    response = client_with_entries.get("/v1/catalogue/entry_001")

    assert response.status_code == 401
