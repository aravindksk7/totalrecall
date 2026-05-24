from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from totalrecall.auth.models import AuthTokenConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TOTALRECALL_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    service_name: str = "totalrecall"
    environment: str = "local"
    database_url: str = "postgresql://totalrecall:totalrecall@localhost:5432/totalrecall"
    migrations_path: Path = Path("migrations")
    local_secrets_dir: Path = Path("local-secrets")
    auth_tokens: dict[str, AuthTokenConfig] = Field(default_factory=dict)
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        description="Browser origins allowed to call the API with Authorization headers.",
    )
    feature_flags: dict[str, Any] = Field(
        default_factory=lambda: {
            "memory.adapter": "mem0_v1",
            "memory.write_enabled": True,
            "memory.fail_open_on_search": True,
            "reformulator.adapter": "keyword",
            "jira.enabled": False,
            "rag.enabled": False,
            "guardrails.input_enabled": False,
            "guardrails.output_enabled": False,
            "tone_check.enabled": False,
        }
    )
    credential_refs: dict[str, str] = Field(
        default_factory=lambda: {
            "mem0_api_key": "local:mem0_api_key",
            "mem0_host": "env:MEM0_HOST",
        }
    )
    external_credential_base_url: str | None = Field(
        default=None,
        description=(
            "Optional HTTP adapter base URL for external/cloud secret managers. "
            "Used for credential refs with external: or cloud: prefixes."
        ),
    )
    external_credential_auth_token: str | None = Field(default=None)
    external_credential_timeout_seconds: int = Field(default=5, ge=1)
    skills_dir: Path = Path("skills")
    learning_path_mappings: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional host-to-runtime path mappings for learning scans. "
            "Example: {\"C:\\\\ENV\": \"/learning-workspace\"}."
        ),
    )
    enable_database: bool = True
    cache_ttl_seconds: int = Field(
        default=300,
        ge=1,
        description="TTL for in-process memory search cache entries (seconds).",
    )
    rate_limits: dict[str, dict] = Field(
        default_factory=dict,
        description=(
            "Per-tenant and default rate-limit policies. "
            "Key 'default' applies to any unconfigured tenant. "
            "e.g. {\"default\": {\"max_requests\": 60, \"window_seconds\": 60}}"
        ),
    )
    external_feature_flags_url: str | None = Field(
        default=None,
        description=(
            "Optional OpenFeature-compatible HTTP endpoint returning "
            "{\"values\": {...}} or a raw flag object."
        ),
    )
    external_feature_flags_auth_token: str | None = Field(default=None)
    external_feature_flags_timeout_seconds: int = Field(default=5, ge=1)
    external_feature_flags_cache_ttl_seconds: int = Field(default=30, ge=0)
    playwright_worker_command: list[str] = Field(
        default_factory=list,
        description=(
            "Optional command for the Playwright validation worker. "
            "When empty, TypeScript worker validation is skipped."
        ),
    )
    playwright_worker_timeout_seconds: int = Field(default=10, ge=1)
    admin_docker_control_enabled: bool = Field(
        default=False,
        description=(
            "Allows admin-authenticated API requests to run Docker Compose for local "
            "self-hosted dependencies. Keep disabled outside local developer machines."
        ),
    )
    docker_compose_project_dir: Path = Field(
        default=Path("."),
        description="Directory containing docker-compose.yml and docker-compose.mem0.yml.",
    )
    docker_compose_command: list[str] = Field(
        default_factory=lambda: ["docker", "compose"],
        description="Command used when admin Docker control is enabled.",
    )
    docker_control_timeout_seconds: int = Field(default=180, ge=1)
