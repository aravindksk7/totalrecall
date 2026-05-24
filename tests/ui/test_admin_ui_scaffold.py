import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN_UI = ROOT / "ui" / "admin"


def test_admin_ui_package_files_exist() -> None:
    expected = [
        "package.json",
        "tsconfig.json",
        "README.md",
        "index.html",
        "src/app.ts",
        "src/styles.css",
        "dist/app.js",
    ]

    for relative_path in expected:
        assert (ADMIN_UI / relative_path).exists(), relative_path


def test_admin_ui_package_declares_static_typescript_build() -> None:
    package = json.loads((ADMIN_UI / "package.json").read_text(encoding="utf-8"))

    assert package["name"] == "@totalrecall/admin-ui"
    assert package["scripts"]["build"] == "tsc -p tsconfig.json"
    assert package["private"] is True


def test_admin_index_exposes_required_governance_views() -> None:
    html = (ADMIN_UI / "index.html").read_text(encoding="utf-8")

    assert './dist/app.js' in html
    views = (
        "generate",
        "credentials",
        "monitoring",
        "catalogue",
        "memory",
        "learning",
        "flags",
    )
    for view in views:
        assert f'data-view="{view}"' in html
        assert f'id="view-{view}"' in html


def test_admin_ui_calls_backend_apis_not_storage_directly() -> None:
    source = (ADMIN_UI / "src" / "app.ts").read_text(encoding="utf-8")

    for endpoint in (
        "/generations",
        "/credentials",
        "/mem0/self-hosted/start",
        "/monitoring/summary",
        "/catalogue",
        "/memories/",
        "/learning/runs",
        "/flags",
        "/metrics",
    ):
        assert endpoint in source

    forbidden = ("asyncpg", "postgres", "migrations", "tombstone_repo", "learning_repo")
    assert not any(term in source.lower() for term in forbidden)


def test_memory_delete_requires_explicit_confirmation() -> None:
    html = (ADMIN_UI / "index.html").read_text(encoding="utf-8")
    source = (ADMIN_UI / "src" / "app.ts").read_text(encoding="utf-8")

    assert 'id="memory-confirm"' in html
    assert 'id="memory-delete-button"' in html
    assert "confirmed" in source
    assert 'method: "DELETE"' in source


def test_generation_form_posts_to_orchestrator_endpoint() -> None:
    html = (ADMIN_UI / "index.html").read_text(encoding="utf-8")
    source = (ADMIN_UI / "src" / "app.ts").read_text(encoding="utf-8")

    for element_id in (
        "generation-form",
        "generation-prompt",
        "generation-jira-key",
        "generation-domain",
        "generation-result",
    ):
        assert f'id="{element_id}"' in html

    assert "/generations" in source
    assert "selectedTestTypes" in source
    assert "renderGenerationResult" in source


def test_credentials_form_manages_runtime_provider_tokens() -> None:
    html = (ADMIN_UI / "index.html").read_text(encoding="utf-8")
    source = (ADMIN_UI / "src" / "app.ts").read_text(encoding="utf-8")

    for element_id in (
        "mem0-setup-form",
        "mem0-setup-api-key",
        "mem0-setup-host",
        "mem0-setup-activate",
        "mem0-selfhost-form",
        "mem0-selfhost-openai-api-key",
        "mem0-selfhost-admin-api-key",
        "mem0-selfhost-jwt-secret",
        "mem0-selfhost-host",
        "mem0-selfhost-start",
        "mem0-selfhost-activate",
        "mem0-selfhost-result",
        "credential-form",
        "credential-key",
        "credential-value",
        "credential-activate",
        "credential-results",
    ):
        assert f'id="{element_id}"' in html

    for credential_key in (
        "mem0_api_key",
        "mem0_host",
        "mem0_jwt_secret",
        "openai_api_key",
        "anthropic_api_key",
        "gemini_api_key",
        "local_llm_base_url",
    ):
        assert credential_key in html

    assert "/credentials" in source
    assert "/mem0/self-hosted/start" in source
    assert "saveRuntimeCredential" in source
    assert "configureMem0" in source
    assert "startSelfHostedMem0" in source
    assert "renderCredentials" in source


def test_monitoring_view_loads_mem0_and_token_efficiency_state() -> None:
    html = (ADMIN_UI / "index.html").read_text(encoding="utf-8")
    source = (ADMIN_UI / "src" / "app.ts").read_text(encoding="utf-8")

    for element_id in (
        "load-monitoring",
        "monitoring-refresh-interval",
        "monitoring-status-cards",
        "monitoring-memory-list",
        "monitoring-token-list",
        "monitoring-provider-results",
        "monitoring-raw",
    ):
        assert f'id="{element_id}"' in html

    assert "/monitoring/summary" in source
    assert "renderMonitoring" in source
    assert "updateMonitoringRefresh" in source


def test_learning_view_surfaces_run_warnings() -> None:
    source = (ADMIN_UI / "src" / "app.ts").read_text(encoding="utf-8")
    styles = (ADMIN_UI / "src" / "styles.css").read_text(encoding="utf-8")

    assert "renderLearningWarnings" in source
    assert "report.warnings" in source
    assert "item.warnings" in source
    assert ".warning-list" in styles


def test_admin_ui_requires_token_before_authenticated_requests() -> None:
    html = (ADMIN_UI / "index.html").read_text(encoding="utf-8")
    source = (ADMIN_UI / "src" / "app.ts").read_text(encoding="utf-8")

    assert 'placeholder="Docker: dev-token"' in html
    assert "requiresBearerToken" in source
    assert "Bearer token is required" in source
