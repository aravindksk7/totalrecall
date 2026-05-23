"""Factory for building a ReformulatorAdapter from feature flags."""

from totalrecall.config.feature_flags import FeatureFlagProvider
from totalrecall.providers.gateway import ProviderGateway
from totalrecall.providers.models import ProviderConfig
from totalrecall.testgen.reformulator import (
    KeywordReformulator,
    LLMReformulator,
    ReformulatorAdapter,
    StubReformulator,
)


def build_reformulator(
    feature_flags: FeatureFlagProvider,
    gateway: ProviderGateway | None = None,
) -> ReformulatorAdapter:
    adapter_name = feature_flags.get_string("reformulator.adapter", "keyword")
    if adapter_name == "stub":
        return StubReformulator()
    if adapter_name == "llm" and gateway is not None:
        provider_id = feature_flags.get_string("reformulator.provider_id", "stub")
        model = feature_flags.get_string("reformulator.model", "test")
        config = ProviderConfig(provider_id=provider_id, model=model, max_output_tokens=512)
        return LLMReformulator(gateway=gateway, provider_config=config)
    return KeywordReformulator()
