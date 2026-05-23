from totalrecall.cache.provider import TTLCache
from totalrecall.config.credentials import CredentialProvider
from totalrecall.config.feature_flags import FeatureFlagProvider
from totalrecall.config.settings import Settings
from totalrecall.memory.adapters.base import MemoryAdapter
from totalrecall.memory.adapters.mem0_v1.adapter import Mem0V1Adapter
from totalrecall.memory.adapters.null import NullMemoryAdapter
from totalrecall.memory.adapters.stub import StubMemoryAdapter
from totalrecall.memory.tombstone import TombstoneFilter
from totalrecall.memory.wrapper.service import MemoryWrapper


def build_memory_adapters(
    settings: Settings,
    credential_provider: CredentialProvider,
) -> dict[str, MemoryAdapter]:
    adapters: dict[str, MemoryAdapter] = {
        "stub": StubMemoryAdapter([]),
        "null": NullMemoryAdapter(),
    }
    if "mem0_api_key" in settings.credential_refs:
        adapters["mem0_v1"] = Mem0V1Adapter(
            credential_provider=credential_provider,
            credential_ref="mem0_api_key",
        )
    return adapters


def build_memory_wrapper(
    settings: Settings,
    feature_flags: FeatureFlagProvider,
    credential_provider: CredentialProvider,
    *,
    tombstone_filter: TombstoneFilter | None = None,
    cache: TTLCache | None = None,
) -> MemoryWrapper:
    return MemoryWrapper(
        feature_flags=feature_flags,
        adapters=build_memory_adapters(settings, credential_provider),
        tombstone_filter=tombstone_filter,
        cache=cache,
    )
