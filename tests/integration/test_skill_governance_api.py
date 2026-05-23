"""Integration tests for GET /v1/skills and POST /v1/skills/{id}/promote|deprecate."""

from fastapi.testclient import TestClient

from totalrecall.auth.models import AuthTokenConfig
from totalrecall.config.settings import Settings
from totalrecall.main import create_app


def _settings() -> Settings:
    return Settings(
        environment="test",
        enable_database=False,
        auth_tokens={
            "admin-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_admin",
                roles=["admin"],
            ),
            "reader-token": AuthTokenConfig(
                tenant_id="tenant_test",
                actor_id="actor_reader",
                roles=["reader"],
            ),
        },
        feature_flags={"memory.adapter": "stub"},
    )


def test_list_skills_returns_200() -> None:
    with TestClient(create_app(_settings())) as client:
        resp = client.get(
            "/v1/skills",
            headers={"Authorization": "Bearer admin-token"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "skills" in body
    assert "total" in body


def test_list_skills_includes_loaded_skills() -> None:
    with TestClient(create_app(_settings())) as client:
        resp = client.get(
            "/v1/skills",
            headers={"Authorization": "Bearer admin-token"},
        )
    skills = resp.json()["skills"]
    skill_ids = [s["skill_id"] for s in skills]
    assert "playwright-typescript-pom" in skill_ids


def test_promote_skill_requires_publish_permission() -> None:
    with TestClient(create_app(_settings())) as client:
        resp = client.post(
            "/v1/skills/playwright-typescript-pom/promote",
            json={},
            headers={"Authorization": "Bearer reader-token"},
        )
    assert resp.status_code == 403


def test_promote_unknown_skill_returns_404() -> None:
    with TestClient(create_app(_settings())) as client:
        resp = client.post(
            "/v1/skills/nonexistent_skill/promote",
            json={},
            headers={"Authorization": "Bearer admin-token"},
        )
    assert resp.status_code == 404


def test_promote_skill_as_admin_returns_200() -> None:
    with TestClient(create_app(_settings())) as client:
        resp = client.post(
            "/v1/skills/playwright-typescript-pom/promote",
            json={"notes": "approved for release"},
            headers={"Authorization": "Bearer admin-token"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["skill_id"] == "playwright-typescript-pom"
    assert body["status"] == "active"
    assert body["promoted_by"] == "actor_admin"


def test_promote_updates_effective_status_in_list() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        client.post(
            "/v1/skills/playwright-typescript-pom/promote",
            json={},
            headers={"Authorization": "Bearer admin-token"},
        )
        resp = client.get(
            "/v1/skills",
            headers={"Authorization": "Bearer admin-token"},
        )
    skills = {s["skill_id"]: s for s in resp.json()["skills"]}
    assert skills["playwright-typescript-pom"]["status"] == "active"


def test_deprecate_skill_as_admin_returns_200() -> None:
    with TestClient(create_app(_settings())) as client:
        resp = client.post(
            "/v1/skills/playwright-typescript-pom/deprecate",
            json={},
            headers={"Authorization": "Bearer admin-token"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "deprecated"


def test_deprecate_requires_publish_permission() -> None:
    with TestClient(create_app(_settings())) as client:
        resp = client.post(
            "/v1/skills/playwright-typescript-pom/deprecate",
            json={},
            headers={"Authorization": "Bearer reader-token"},
        )
    assert resp.status_code == 403
