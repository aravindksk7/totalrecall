"""Mem0 v1 adapter with Mem0 SDK usage isolated to this package.

No code outside totalrecall/memory/adapters/mem0_v1/ may import from mem0.
"""

from typing import Any

from totalrecall.config.credentials import CredentialProvider
from totalrecall.memory.models import (
    MemoryCapabilities,
    MemoryDeleteRequest,
    MemoryDeleteResult,
    MemoryEntry,
    MemoryGetRequest,
    MemoryHealth,
    MemoryHealthStatus,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStatus,
    MemoryUpsertRequest,
)

_MEM0_NOT_INSTALLED = (
    "The 'mem0ai' package is required to use Mem0V1Adapter. "
    "Install it with: uv add mem0ai"
)

_ADAPTER_VERSION = "mem0_v1"


def _mem0_user_id(tenant_id: str, application_id: str) -> str:
    """Scopes Mem0 user_id to the TotalRecall tenant+application namespace."""
    return f"{tenant_id}::{application_id}"


class Mem0V1Adapter:
    """Wraps the Mem0 SDK behind the MemoryAdapter contract.

    Credential reference: settings.credential_refs['mem0_api_key'] must resolve to a Mem0 API key.
    """

    adapter_version = _ADAPTER_VERSION

    def __init__(
        self,
        credential_provider: CredentialProvider,
        credential_ref: str = "mem0_api_key",
        host: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._credential_provider = credential_provider
        self._credential_ref = credential_ref
        self._host = host
        self._client: Any = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from mem0 import MemoryClient  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(_MEM0_NOT_INSTALLED) from exc
        api_key = self._credential_provider.get(self._credential_ref)
        self._client = MemoryClient(api_key=api_key, host=self._host)
        return self._client

    def search(self, request: MemorySearchRequest) -> MemorySearchResult:
        client = self._get_client()
        user_id = _mem0_user_id(request.tenant_id, request.application_id)
        query = request.query or " ".join(f"{k}:{v}" for k, v in request.filters.items())
        try:
            raw_response = client.search(
                query or "general",
                filters=_mem0_filters(user_id, request.filters),
                top_k=request.limit,
            )
        except Exception:
            return MemorySearchResult(items=[], adapter_version=self.adapter_version)

        entries = [
            self._mem0_to_entry(r, request.tenant_id, request.application_id)
            for r in _extract_mem0_results(raw_response)
        ]
        active = [e for e in entries if e.status == MemoryStatus.ACTIVE]
        return MemorySearchResult(items=active, adapter_version=self.adapter_version)

    def get(self, request: MemoryGetRequest) -> MemoryEntry | None:
        client = self._get_client()
        try:
            result = client.get(request.entity_id)
        except Exception:
            return None
        if result is None:
            return None
        return self._mem0_to_entry(result, request.tenant_id, request.application_id)

    def upsert(self, request: MemoryUpsertRequest) -> MemoryEntry:
        client = self._get_client()
        entry = request.memory
        user_id = _mem0_user_id(entry.tenant_id, entry.application_id)
        message = f"{entry.summary}: {entry.knowledge}"
        try:
            result = client.add(
                [{"role": "user", "content": message}],
                user_id=user_id,
                metadata=dict(entry.tags),
                output_format="v1.1",
            )
            raw_results = _extract_mem0_results(result)
            if raw_results:
                return self._mem0_to_entry(
                    raw_results[0],
                    entry.tenant_id,
                    entry.application_id,
                )
        except Exception:
            pass
        return entry

    def delete(self, request: MemoryDeleteRequest) -> MemoryDeleteResult:
        client = self._get_client()
        try:
            client.delete(request.entity_id)
            deleted = True
        except Exception:
            deleted = False
        return MemoryDeleteResult(
            entity_id=request.entity_id,
            deleted=deleted,
            adapter_version=self.adapter_version,
        )

    def health(self) -> MemoryHealth:
        try:
            self._get_client()
            return MemoryHealth(status=MemoryHealthStatus.OK, adapter_version=self.adapter_version)
        except ImportError:
            return MemoryHealth(
                status=MemoryHealthStatus.UNAVAILABLE,
                adapter_version=self.adapter_version,
                degraded=True,
            )
        except Exception:
            return MemoryHealth(
                status=MemoryHealthStatus.DEGRADED,
                adapter_version=self.adapter_version,
                degraded=True,
            )

    def capabilities(self) -> MemoryCapabilities:
        return MemoryCapabilities(
            adapter_version=self.adapter_version,
            supports_search=True,
            supports_get=True,
            supports_upsert=True,
            supports_delete=True,
            supports_shadow_read=False,
        )

    @staticmethod
    def _mem0_to_entry(raw: Any, tenant_id: str, application_id: str) -> MemoryEntry:
        mem_id = raw.get("id", "") if isinstance(raw, dict) else getattr(raw, "id", "")
        memory_text = (
            raw.get("memory", "") if isinstance(raw, dict) else getattr(raw, "memory", "")
        )
        metadata = (
            raw.get("metadata", {}) if isinstance(raw, dict) else getattr(raw, "metadata", {})
        ) or {}
        raw_status = (
            raw.get("status", MemoryStatus.ACTIVE)
            if isinstance(raw, dict)
            else getattr(raw, "status", MemoryStatus.ACTIVE)
        )
        status = (
            raw_status
            if isinstance(raw_status, MemoryStatus)
            else MemoryStatus(raw_status)
            if raw_status in {status.value for status in MemoryStatus}
            else MemoryStatus.ACTIVE
        )
        return MemoryEntry(
            entity_id=mem_id or "mem0_unknown",
            tenant_id=tenant_id,
            application_id=application_id,
            summary=memory_text[:120] if memory_text else "mem0 entry",
            knowledge=memory_text or "",
            tags=metadata if isinstance(metadata, dict) else {},
            status=status,
        )


def _mem0_filters(user_id: str, filters: dict[str, Any]) -> dict[str, Any]:
    if not filters:
        return {"user_id": user_id}

    tag_filters = [{key: value} for key, value in filters.items()]
    return {"AND": [{"user_id": user_id}, *tag_filters]}


def _extract_mem0_results(raw_response: Any) -> list[Any]:
    if isinstance(raw_response, list):
        return raw_response
    if isinstance(raw_response, dict):
        results = raw_response.get("results")
        if isinstance(results, list):
            return results
        if raw_response.get("id") or raw_response.get("memory"):
            return [raw_response]
    return []
