"""Integration tests for POST/GET /v1/learning/runs."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from totalrecall.api.dependencies import get_audit_repo, get_catalogue_repo, get_learning_repo
from totalrecall.auth.models import AuthTokenConfig
from totalrecall.catalogue.models import CatalogueSource
from totalrecall.config.settings import Settings
from totalrecall.learning.models import (
    LearningDelta,
    LearningDeltaState,
    LearningDiscovery,
    LearningDiscoveryType,
    LearningReport,
    LearningRun,
    LearningRunStatus,
    LearningScope,
    LearningTriggerType,
)
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
            "test-maintainer": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_maint",
                roles=["maintainer"],
            ),
            "test-reader": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_reader",
                roles=["reader"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )


def _make_learning_repo(
    report: LearningReport | None = None,
    run_list: list[LearningReport] | None = None,
    previous_hashes: dict | None = None,
    discovery_result: tuple | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.save_report = AsyncMock(return_value=None)
    repo.get_run = AsyncMock(return_value=report)
    repo.list_runs = AsyncMock(return_value=run_list or [])
    repo.get_previous_hashes = AsyncMock(return_value=previous_hashes or {})
    repo.approve_discovery = AsyncMock(return_value=True)
    repo.reject_discovery = AsyncMock(return_value=True)
    repo.get_discovery = AsyncMock(return_value=discovery_result)
    return repo


def _make_audit_repo() -> MagicMock:
    repo = MagicMock()
    repo.record = AsyncMock(return_value="event_001")
    return repo


def _make_catalogue_repo() -> MagicMock:
    repo = MagicMock()
    repo.upsert = AsyncMock(return_value=None)
    return repo


def _make_fake_report(run_id: str = "run_001") -> LearningReport:
    source = CatalogueSource(type="file_scan", reference="/test/page.py")
    discovery = LearningDiscovery(
        discovery_id="disc_001",
        discovery_type=LearningDiscoveryType.STATIC_SKILL_CANDIDATE,
        delta=LearningDelta(state=LearningDeltaState.NEW, current_hash="abc123"),
        summary="page_object_class: LoginPage (python)",
        source=source,
    )
    run = LearningRun(
        run_id=run_id,
        tenant_id="tenant_test",
        application_id="app_test",
        scope=LearningScope(repository="local", branch="main", path="/tmp"),
        trigger_type=LearningTriggerType.MANUAL,
        status=LearningRunStatus.COMPLETED,
        discoveries=[discovery],
    )
    return LearningReport(
        run=run,
        discovered_count=1,
        changed_count=0,
        removed_count=0,
        unchanged_count=0,
        rejected_count=0,
    )


@pytest.fixture
def client_with_repos(tmp_path) -> Generator[TestClient]:
    settings = _make_settings()
    app = create_app(settings)
    learning_repo = _make_learning_repo()
    audit_repo = _make_audit_repo()
    catalogue_repo = _make_catalogue_repo()
    app.dependency_overrides[get_learning_repo] = lambda: learning_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_catalogue_repo] = lambda: catalogue_repo
    with TestClient(app) as tc:
        yield tc


def test_trigger_run_returns_503_when_db_unavailable() -> None:
    settings = _make_settings()
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/runs",
            json={
                "application_id": "app_test",
                "scope": {"repository": "local", "branch": "main", "path": "/tmp"},
            },
            headers={"Authorization": "Bearer test-admin"},
        )
    assert response.status_code == 503


def test_trigger_run_rejects_missing_auth(client_with_repos, tmp_path) -> None:
    response = client_with_repos.post(
        "/v1/learning/runs",
        json={
            "application_id": "app_test",
            "scope": {"repository": "local", "branch": "main", "path": str(tmp_path)},
        },
    )
    assert response.status_code == 401


def test_trigger_run_rejects_reader_without_permission(client_with_repos, tmp_path) -> None:
    response = client_with_repos.post(
        "/v1/learning/runs",
        json={
            "application_id": "app_test",
            "scope": {"repository": "local", "branch": "main", "path": str(tmp_path)},
        },
        headers={"Authorization": "Bearer test-reader"},
    )
    assert response.status_code == 403


def test_trigger_run_succeeds_for_maintainer(tmp_path) -> None:
    settings = _make_settings()
    app = create_app(settings)
    (tmp_path / "page.py").write_text("class LoginPage:\n    pass\n")
    learning_repo = _make_learning_repo()
    audit_repo = _make_audit_repo()
    app.dependency_overrides[get_learning_repo] = lambda: learning_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/runs",
            json={
                "application_id": "app_test",
                "scope": {"repository": "local", "branch": "main", "path": str(tmp_path)},
            },
            headers={"Authorization": "Bearer test-maintainer"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["run"]["status"] == "completed"
    assert body["discovered_count"] >= 1


def test_trigger_run_maps_host_path_before_scanning(tmp_path) -> None:
    mapped_root = tmp_path / "test-env-management" / "tests"
    mapped_root.mkdir(parents=True)
    (mapped_root / "login.spec.ts").write_text(
        "class LoginPage {}\ntest('login works', async () => {})\n",
        encoding="utf-8",
    )
    settings = _make_settings()
    settings.learning_path_mappings = {"C:\\ENV": str(tmp_path)}
    app = create_app(settings)
    learning_repo = _make_learning_repo()
    audit_repo = _make_audit_repo()
    app.dependency_overrides[get_learning_repo] = lambda: learning_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/runs",
            json={
                "application_id": "app_test",
                "scope": {
                    "repository": "local",
                    "branch": "main",
                    "path": "C:\\ENV\\test-env-management\\tests",
                    "framework": "playwright",
                },
            },
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["run"]["status"] == "completed"
    assert body["run"]["scope"]["path"] == str(mapped_root)
    assert body["discovered_count"] >= 1
    assert "Mapped learning path from C:\\ENV\\test-env-management\\tests" in body["warnings"][0]


def test_trigger_run_saves_to_repo(tmp_path) -> None:
    settings = _make_settings()
    app = create_app(settings)
    learning_repo = _make_learning_repo()
    audit_repo = _make_audit_repo()
    app.dependency_overrides[get_learning_repo] = lambda: learning_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        client.post(
            "/v1/learning/runs",
            json={
                "application_id": "app_test",
                "scope": {"repository": "local", "branch": "main", "path": str(tmp_path)},
            },
            headers={"Authorization": "Bearer test-admin"},
        )

    learning_repo.save_report.assert_awaited_once()


def test_get_run_returns_404_when_not_found(client_with_repos) -> None:
    response = client_with_repos.get(
        "/v1/learning/runs/unknown_run",
        headers={"Authorization": "Bearer test-admin"},
    )
    assert response.status_code == 404


def test_get_run_returns_report_when_found() -> None:
    settings = _make_settings()
    app = create_app(settings)
    fake_report = _make_fake_report("run_xyz")
    learning_repo = _make_learning_repo(report=fake_report)
    audit_repo = _make_audit_repo()
    app.dependency_overrides[get_learning_repo] = lambda: learning_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        response = client.get(
            "/v1/learning/runs/run_xyz",
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["run_id"] == "run_xyz"
    assert body["discovered_count"] == 1


def test_list_runs_returns_empty_list(client_with_repos) -> None:
    response = client_with_repos.get(
        "/v1/learning/runs",
        headers={"Authorization": "Bearer test-admin"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_approve_discovery_requires_permission(client_with_repos) -> None:
    response = client_with_repos.post(
        "/v1/learning/runs/run_001/approve/disc_001",
        json={},
        headers={"Authorization": "Bearer test-reader"},
    )
    assert response.status_code == 403


def test_approve_discovery_succeeds_for_admin(client_with_repos) -> None:
    response = client_with_repos.post(
        "/v1/learning/runs/run_001/approve/disc_001",
        json={"reason": "looks good"},
        headers={"Authorization": "Bearer test-admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approved"] is True
    assert body["discovery_id"] == "disc_001"


def test_reject_discovery_succeeds_for_maintainer(client_with_repos) -> None:
    response = client_with_repos.post(
        "/v1/learning/runs/run_001/reject/disc_001",
        json={"reason": "not relevant"},
        headers={"Authorization": "Bearer test-maintainer"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rejected"] is True


def test_approve_discovery_promotes_static_skill_to_catalogue() -> None:
    settings = _make_settings()
    app = create_app(settings)

    source = CatalogueSource(type="file_scan", reference="/test/page.py")
    discovery = LearningDiscovery(
        discovery_id="disc_001",
        discovery_type=LearningDiscoveryType.STATIC_SKILL_CANDIDATE,
        delta=LearningDelta(state=LearningDeltaState.NEW, current_hash="abc123"),
        summary="page_object_class: LoginPage (python)",
        source=source,
    )

    learning_repo = _make_learning_repo(discovery_result=(discovery, "app_test"))
    audit_repo = _make_audit_repo()
    catalogue_repo = _make_catalogue_repo()
    app.dependency_overrides[get_learning_repo] = lambda: learning_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_catalogue_repo] = lambda: catalogue_repo

    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/runs/run_001/approve/disc_001",
            json={"reason": "looks good"},
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["approved"] is True
    assert body["promoted"] is True
    catalogue_repo.upsert.assert_awaited_once()


def test_approve_discovery_does_not_promote_catalogue_reference() -> None:
    settings = _make_settings()
    app = create_app(settings)

    source = CatalogueSource(type="file_scan", reference="/test/test_login.py")
    discovery = LearningDiscovery(
        discovery_id="disc_002",
        discovery_type=LearningDiscoveryType.CATALOGUE_REFERENCE,
        delta=LearningDelta(state=LearningDeltaState.NEW, current_hash="def456"),
        summary="test_function: test_login_redirects (python)",
        source=source,
    )

    learning_repo = _make_learning_repo(discovery_result=(discovery, "app_test"))
    audit_repo = _make_audit_repo()
    catalogue_repo = _make_catalogue_repo()
    app.dependency_overrides[get_learning_repo] = lambda: learning_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_catalogue_repo] = lambda: catalogue_repo

    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/runs/run_001/approve/disc_002",
            json={},
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 200
    assert response.json()["promoted"] is False
    catalogue_repo.upsert.assert_not_called()


# --- Discovery search and bulk action tests ---


def _make_search_repo(results=None, bulk_result=None) -> MagicMock:
    from totalrecall.learning.models import BulkDecisionResult

    repo = _make_learning_repo()
    repo.search_discoveries = AsyncMock(return_value=results or [])
    default_bulk = BulkDecisionResult(processed=1, skipped=0, discovery_ids=["disc_001"])
    repo.bulk_approve_discoveries = AsyncMock(return_value=bulk_result or default_bulk)
    repo.bulk_reject_discoveries = AsyncMock(return_value=bulk_result or default_bulk)
    return repo


def test_search_discoveries_returns_empty_list(tmp_path) -> None:
    settings = _make_settings()
    app = create_app(settings)
    repo = _make_search_repo()
    app.dependency_overrides[get_learning_repo] = lambda: repo

    with TestClient(app) as client:
        response = client.get(
            "/v1/learning/discoveries",
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 200
    assert response.json() == []


def test_search_discoveries_passes_filters_to_repo(tmp_path) -> None:
    from totalrecall.learning.models import DiscoverySearchResult, LearningDiscoveryStatus, LearningDiscoveryType, LearningDeltaState

    settings = _make_settings()
    app = create_app(settings)
    item = DiscoverySearchResult(
        discovery_id="disc_001",
        run_id="run_001",
        application_id="app_test",
        discovery_type=LearningDiscoveryType.STATIC_SKILL_CANDIDATE,
        status=LearningDiscoveryStatus.DISCOVERED,
        summary="LoginPage login validation",
        confidence=0.9,
        delta_state=LearningDeltaState.NEW,
    )
    repo = _make_search_repo(results=[item])
    app.dependency_overrides[get_learning_repo] = lambda: repo

    with TestClient(app) as client:
        response = client.get(
            "/v1/learning/discoveries?q=login&status=discovered&confidence_min=0.5&limit=10",
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["discovery_id"] == "disc_001"
    assert body[0]["summary"] == "LoginPage login validation"
    repo.search_discoveries.assert_awaited_once()
    call_kwargs = repo.search_discoveries.call_args.kwargs
    assert call_kwargs["q"] == "login"
    assert call_kwargs["status"] == "discovered"
    assert call_kwargs["confidence_min"] == pytest.approx(0.5)
    assert call_kwargs["limit"] == 10


def test_search_discoveries_requires_auth(tmp_path) -> None:
    settings = _make_settings()
    app = create_app(settings)
    repo = _make_search_repo()
    app.dependency_overrides[get_learning_repo] = lambda: repo

    with TestClient(app) as client:
        response = client.get("/v1/learning/discoveries")

    assert response.status_code == 401


def test_bulk_approve_requires_permission() -> None:
    settings = _make_settings()
    app = create_app(settings)
    repo = _make_search_repo()
    audit_repo = _make_audit_repo()
    catalogue_repo = _make_catalogue_repo()
    app.dependency_overrides[get_learning_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_catalogue_repo] = lambda: catalogue_repo

    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/discoveries/bulk-approve",
            json={"discovery_ids": ["disc_001"]},
            headers={"Authorization": "Bearer test-reader"},
        )

    assert response.status_code == 403


def test_bulk_approve_returns_processed_count() -> None:
    from totalrecall.learning.models import BulkDecisionResult

    settings = _make_settings()
    app = create_app(settings)
    bulk_result = BulkDecisionResult(processed=2, skipped=1, discovery_ids=["disc_001", "disc_002"])
    repo = _make_search_repo(bulk_result=bulk_result)
    audit_repo = _make_audit_repo()
    catalogue_repo = _make_catalogue_repo()
    app.dependency_overrides[get_learning_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_catalogue_repo] = lambda: catalogue_repo

    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/discoveries/bulk-approve",
            json={"discovery_ids": ["disc_001", "disc_002", "disc_003"], "reason": "batch approval"},
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 2
    assert body["skipped"] == 1
    repo.bulk_approve_discoveries.assert_awaited_once()


def test_bulk_approve_rejects_empty_list() -> None:
    settings = _make_settings()
    app = create_app(settings)
    repo = _make_search_repo()
    audit_repo = _make_audit_repo()
    catalogue_repo = _make_catalogue_repo()
    app.dependency_overrides[get_learning_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_catalogue_repo] = lambda: catalogue_repo

    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/discoveries/bulk-approve",
            json={"discovery_ids": []},
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 400


def test_bulk_reject_returns_processed_count() -> None:
    from totalrecall.learning.models import BulkDecisionResult

    settings = _make_settings()
    app = create_app(settings)
    bulk_result = BulkDecisionResult(processed=3, skipped=0, discovery_ids=["d1", "d2", "d3"])
    repo = _make_search_repo(bulk_result=bulk_result)
    audit_repo = _make_audit_repo()
    app.dependency_overrides[get_learning_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo

    with TestClient(app) as client:
        response = client.post(
            "/v1/learning/discoveries/bulk-reject",
            json={"discovery_ids": ["d1", "d2", "d3"], "reason": "not relevant"},
            headers={"Authorization": "Bearer test-admin"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 3
    assert body["skipped"] == 0
    repo.bulk_reject_discoveries.assert_awaited_once()


def test_bulk_approve_records_audit_event() -> None:
    settings = _make_settings()
    app = create_app(settings)
    repo = _make_search_repo()
    audit_repo = _make_audit_repo()
    catalogue_repo = _make_catalogue_repo()
    app.dependency_overrides[get_learning_repo] = lambda: repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_catalogue_repo] = lambda: catalogue_repo

    with TestClient(app) as client:
        client.post(
            "/v1/learning/discoveries/bulk-approve",
            json={"discovery_ids": ["disc_001"]},
            headers={"Authorization": "Bearer test-admin"},
        )

    audit_repo.record.assert_awaited_once()
    call_kwargs = audit_repo.record.call_args.kwargs
    assert call_kwargs["event_type"] == "learning.discoveries.bulk_approved"
