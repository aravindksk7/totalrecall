import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol


class CredentialNotFoundError(Exception):
    pass


class CredentialProvider(Protocol):
    def get(self, key: str) -> str:
        """Resolve a named credential value."""


class EnvLocalCredentialProvider:
    def __init__(self, credential_refs: dict[str, str], local_secrets_dir: Path) -> None:
        self._credential_refs = dict(credential_refs)
        self._local_secrets_dir = local_secrets_dir

    def get(self, key: str) -> str:
        ref = self._credential_refs.get(key)
        if ref is None:
            raise CredentialNotFoundError(f"Credential reference missing for {key}.")

        if ref.startswith("env:"):
            env_name = ref.removeprefix("env:")
            value = os.getenv(env_name)
            if not value:
                raise CredentialNotFoundError(f"Environment credential {env_name} is not set.")
            return value

        if ref.startswith("local:"):
            secret_name = ref.removeprefix("local:")
            secret_path = self._local_secrets_dir / secret_name
            if not secret_path.is_file():
                raise CredentialNotFoundError(f"Local credential {secret_name} is not available.")
            return secret_path.read_text(encoding="utf-8").strip()

        if ref.startswith("file:"):
            secret_path = Path(ref.removeprefix("file:"))
            if not secret_path.is_absolute():
                secret_path = self._local_secrets_dir / secret_path
            if not secret_path.is_file():
                raise CredentialNotFoundError(f"File credential {secret_path} is not available.")
            return secret_path.read_text(encoding="utf-8").strip()

        raise CredentialNotFoundError(f"Unsupported credential reference for {key}.")


class ExternalCredentialProvider:
    """Resolve credentials from an external secret-manager HTTP adapter.

    This adapter keeps cloud SDKs out of the core service. A Vault, AWS Secrets
    Manager, GCP Secret Manager, or Azure Key Vault sidecar/proxy can expose the
    small HTTP contract:

    GET {base_url}/secrets/{secret_name}
    -> {"value": "..."} or a plaintext response body.
    """

    def __init__(
        self,
        credential_refs: dict[str, str],
        base_url: str,
        *,
        auth_token: str | None = None,
        timeout_seconds: int = 5,
        opener=urllib.request.urlopen,
    ) -> None:
        if not base_url:
            raise ValueError("External credential base URL must not be empty")
        if timeout_seconds < 1:
            raise ValueError("External credential timeout must be >= 1 second")
        self._credential_refs = dict(credential_refs)
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def get(self, key: str) -> str:
        ref = self._credential_refs.get(key)
        if ref is None:
            raise CredentialNotFoundError(f"Credential reference missing for {key}.")
        if not (ref.startswith("external:") or ref.startswith("cloud:")):
            raise CredentialNotFoundError(f"Unsupported credential reference for {key}.")

        secret_name = ref.split(":", 1)[1]
        if not secret_name:
            raise CredentialNotFoundError(f"External credential name missing for {key}.")

        encoded_name = urllib.parse.quote(secret_name, safe="")
        request = urllib.request.Request(f"{self._base_url}/secrets/{encoded_name}")
        if self._auth_token:
            request.add_header("Authorization", f"Bearer {self._auth_token}")

        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8").strip()
        except (OSError, urllib.error.URLError) as exc:
            raise CredentialNotFoundError(
                f"External credential {secret_name} is not available."
            ) from exc

        if not raw:
            raise CredentialNotFoundError(f"External credential {secret_name} is empty.")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw

        if isinstance(payload, dict) and isinstance(payload.get("value"), str):
            value = payload["value"].strip()
            if value:
                return value
        raise CredentialNotFoundError(
            f"External credential {secret_name} response did not contain a value."
        )


class CredentialProviderChain:
    def __init__(self, providers: list[CredentialProvider]) -> None:
        if not providers:
            raise ValueError("CredentialProviderChain requires at least one provider")
        self._providers = list(providers)

    def get(self, key: str) -> str:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return provider.get(key)
            except CredentialNotFoundError as exc:
                errors.append(str(exc))
        raise CredentialNotFoundError("; ".join(errors))
