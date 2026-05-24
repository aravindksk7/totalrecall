import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mem0SelfHostStartResult:
    env_file: Path
    start_status: str
    started: bool
    message: str
    command: list[str]


class Mem0SelfHostManager:
    def __init__(
        self,
        *,
        local_secrets_dir: Path,
        project_dir: Path,
        docker_control_enabled: bool,
        compose_command: list[str],
        timeout_seconds: int,
    ) -> None:
        self._local_secrets_dir = local_secrets_dir
        self._project_dir = project_dir
        self._docker_control_enabled = docker_control_enabled
        self._compose_command = compose_command
        self._timeout_seconds = timeout_seconds

    def configure(
        self,
        *,
        openai_api_key: str,
        mem0_admin_api_key: str,
        mem0_jwt_secret: str,
        start_containers: bool,
    ) -> Mem0SelfHostStartResult:
        env_file = self.write_env_file(
            openai_api_key=openai_api_key,
            mem0_admin_api_key=mem0_admin_api_key,
            mem0_jwt_secret=mem0_jwt_secret,
        )
        command = self._start_command(env_file)
        if not start_containers:
            return Mem0SelfHostStartResult(
                env_file=env_file,
                start_status="skipped",
                started=False,
                message="Saved self-hosted Mem0 environment values. Container startup was skipped.",
                command=command,
            )
        if not self._docker_control_enabled:
            return Mem0SelfHostStartResult(
                env_file=env_file,
                start_status="disabled",
                started=False,
                message=(
                    "Saved self-hosted Mem0 environment values. Docker startup is disabled; "
                    "set TOTALRECALL_ADMIN_DOCKER_CONTROL_ENABLED=true to allow admin UI startup."
                ),
                command=command,
            )

        project_dir = self._project_dir.resolve()
        if not (project_dir / "docker-compose.yml").is_file():
            return Mem0SelfHostStartResult(
                env_file=env_file,
                start_status="failed",
                started=False,
                message=f"docker-compose.yml was not found under {project_dir}.",
                command=command,
            )
        if not (project_dir / "docker-compose.mem0.yml").is_file():
            return Mem0SelfHostStartResult(
                env_file=env_file,
                start_status="failed",
                started=False,
                message=f"docker-compose.mem0.yml was not found under {project_dir}.",
                command=command,
            )

        try:
            completed = subprocess.run(
                command,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
                env={**os.environ, "COMPOSE_BAKE": os.environ.get("COMPOSE_BAKE", "false")},
            )
        except FileNotFoundError:
            return Mem0SelfHostStartResult(
                env_file=env_file,
                start_status="failed",
                started=False,
                message="Docker Compose command was not found in the API process PATH.",
                command=command,
            )
        except subprocess.TimeoutExpired:
            return Mem0SelfHostStartResult(
                env_file=env_file,
                start_status="failed",
                started=False,
                message=f"Docker Compose startup timed out after {self._timeout_seconds} seconds.",
                command=command,
            )

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip().splitlines()
            message = detail[-1] if detail else "Docker Compose startup failed."
            return Mem0SelfHostStartResult(
                env_file=env_file,
                start_status="failed",
                started=False,
                message=message,
                command=command,
            )
        return Mem0SelfHostStartResult(
            env_file=env_file,
            start_status="started",
            started=True,
            message="Self-hosted Mem0 containers are starting.",
            command=command,
        )

    def write_env_file(
        self,
        *,
        openai_api_key: str,
        mem0_admin_api_key: str,
        mem0_jwt_secret: str,
    ) -> Path:
        values = {
            "OPENAI_API_KEY": openai_api_key,
            "MEM0_ADMIN_API_KEY": mem0_admin_api_key,
            "MEM0_JWT_SECRET": mem0_jwt_secret,
            "MEM0_AUTH_DISABLED": "false",
            "MEM0_DASHBOARD_URL": "http://localhost:3000",
        }
        lines = [_env_line(key, value) for key, value in values.items()]
        self._local_secrets_dir.mkdir(parents=True, exist_ok=True)
        path = self._local_secrets_dir / "mem0-selfhost.env"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _restrict_file_permissions(path)
        return path

    def _start_command(self, env_file: Path) -> list[str]:
        return [
            *self._compose_command,
            "--env-file",
            str(env_file),
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.mem0.yml",
            "up",
            "-d",
            "mem0",
            "mem0-postgres",
        ]


def _env_line(key: str, value: str) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError(f"{key} must not be empty.")
    if "\n" in clean or "\r" in clean:
        raise ValueError(f"{key} must not contain line breaks.")
    escaped = clean.replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}="{escaped}"'


def _restrict_file_permissions(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
