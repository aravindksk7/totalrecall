from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mem0_compose_overlay_runs_mem0_as_self_hosted_service() -> None:
    compose = (ROOT / "docker-compose.mem0.yml").read_text(encoding="utf-8")

    assert "totalrecall-mem0-api-server:latest" in compose
    assert "docker/mem0-api.Dockerfile" in compose
    assert "MEM0_REF" in compose
    assert "mem0-postgres:" in compose
    assert '"8888:8000"' in compose
    assert "HISTORY_DB_PATH: ${MEM0_HISTORY_DB_PATH:-/app/history/history.db}" in compose
    assert "mem0-history-data:/app/history" in compose
    assert "mem0-history-data:" in compose
    assert "alembic upgrade head" in compose
    assert "http://localhost:8000/auth/setup-status" in compose


def test_mem0_compose_overlay_wires_totalrecall_to_internal_mem0_host() -> None:
    compose = (ROOT / "docker-compose.mem0.yml").read_text(encoding="utf-8")

    assert (
        'TOTALRECALL_FEATURE_FLAGS: \'{"memory.adapter":"mem0_v1",'
        '"memory.write_enabled":true,"memory.fail_open_on_search":true}\''
    ) in compose
    assert (
        'TOTALRECALL_CREDENTIAL_REFS: \'{"mem0_api_key":"env:MEM0_API_KEY",'
        '"mem0_host":"env:MEM0_HOST"}\''
    ) in compose
    assert (
        "MEM0_API_KEY: ${MEM0_ADMIN_API_KEY:-dev-totalrecall-mem0-admin-key}"
        in compose
    )
    assert "MEM0_HOST: http://mem0:8000" in compose


def test_mem0_postgres_init_script_creates_app_database_idempotently() -> None:
    script = (ROOT / "docker" / "mem0-init-db.sh").read_text(encoding="utf-8")

    assert "APP_DB_NAME" in script
    assert "WHERE NOT EXISTS" in script
    assert "\\gexec" in script


def test_mem0_api_dockerfile_builds_from_official_source_tarball() -> None:
    dockerfile = (ROOT / "docker" / "mem0-api.Dockerfile").read_text(encoding="utf-8")

    assert "github.com/mem0ai/mem0/archive/refs/heads/${MEM0_REF}.tar.gz" in dockerfile
    assert "/src/mem0/server/requirements.txt" in dockerfile
    assert "pip install --no-cache-dir -e .[graph]" in dockerfile


def test_docs_describe_self_hosted_mem0_docker_overlay() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for expected in (
        "docker-compose.mem0.yml",
        "OPENAI_API_KEY",
        "MEM0_ADMIN_API_KEY",
        "MEM0_JWT_SECRET",
        "http://localhost:8888",
        "http://mem0:8000",
    ):
        assert expected in readme
        assert expected in env_example or expected == "docker-compose.mem0.yml"
