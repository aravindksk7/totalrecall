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
    for view in ("catalogue", "memory", "learning", "flags"):
        assert f'data-view="{view}"' in html
        assert f'id="view-{view}"' in html


def test_admin_ui_calls_backend_apis_not_storage_directly() -> None:
    source = (ADMIN_UI / "src" / "app.ts").read_text(encoding="utf-8")

    for endpoint in (
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
