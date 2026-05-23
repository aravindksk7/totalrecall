"""Factory for building the RAG store from feature flags and credentials."""

from totalrecall.config.feature_flags import FeatureFlagProvider
from totalrecall.testgen.rag.store import NullRagStore, RagStoreProtocol, StubRagStore


def build_rag_store(
    feature_flags: FeatureFlagProvider,
    credential_provider=None,
    settings=None,
) -> RagStoreProtocol:
    """Return the appropriate RagStore based on feature flags.

    Flag: rag.enabled (bool) — when False, returns NullRagStore.
    Flag: rag.adapter — "pgvector" | "stub" | "null" (default "null").
    """
    if not feature_flags.get_bool("rag.enabled", False):
        return NullRagStore()

    adapter = feature_flags.get_string("rag.adapter", "null")

    if adapter == "stub":
        return StubRagStore()

    if adapter == "pgvector":
        dsn = feature_flags.get_string("rag.dsn", "")
        openai_key = ""
        if credential_provider is not None:
            try:
                openai_key = credential_provider.get("openai_api_key") or ""
            except Exception:
                pass

        from totalrecall.testgen.rag.embedder import OpenAIEmbedder
        from totalrecall.testgen.rag.store import PgvectorRagStore

        embedder = OpenAIEmbedder(api_key=openai_key)
        return PgvectorRagStore(dsn=dsn, embedder=embedder)

    return NullRagStore()
