from totalrecall.config.credentials import (
    CredentialProvider,
    CredentialProviderChain,
    EnvLocalCredentialProvider,
    ExternalCredentialProvider,
)
from totalrecall.config.feature_flags import (
    ConfigFeatureFlagProvider,
    ExternalFeatureFlagProvider,
    FeatureFlagProvider,
)
from totalrecall.config.runtime_credentials import (
    RuntimeCredentialProvider,
    RuntimeCredentialStore,
)
from totalrecall.config.runtime_flags import RuntimeFeatureFlagProvider, RuntimeFeatureFlagStore
from totalrecall.config.settings import Settings


def build_feature_flag_provider(
    settings: Settings,
    runtime_store: RuntimeFeatureFlagStore | None = None,
) -> FeatureFlagProvider:
    config_provider = ConfigFeatureFlagProvider(settings.feature_flags)
    provider: FeatureFlagProvider
    if not settings.external_feature_flags_url:
        provider = config_provider
    else:
        provider = ExternalFeatureFlagProvider(
            settings.external_feature_flags_url,
            fallback=config_provider,
            auth_token=settings.external_feature_flags_auth_token,
            timeout_seconds=settings.external_feature_flags_timeout_seconds,
            cache_ttl_seconds=settings.external_feature_flags_cache_ttl_seconds,
        )
    if runtime_store is None:
        return provider
    return RuntimeFeatureFlagProvider(provider, runtime_store)


def build_credential_provider(
    settings: Settings,
    runtime_store: RuntimeCredentialStore | None = None,
) -> CredentialProvider:
    env_local_provider = EnvLocalCredentialProvider(
        credential_refs=settings.credential_refs,
        local_secrets_dir=settings.local_secrets_dir,
    )
    providers: list[CredentialProvider] = []
    if runtime_store is not None:
        providers.append(RuntimeCredentialProvider(runtime_store))
    providers.append(env_local_provider)
    if not settings.external_credential_base_url:
        return providers[0] if len(providers) == 1 else CredentialProviderChain(providers)

    providers.append(
        ExternalCredentialProvider(
            credential_refs=settings.credential_refs,
            base_url=settings.external_credential_base_url,
            auth_token=settings.external_credential_auth_token,
            timeout_seconds=settings.external_credential_timeout_seconds,
        )
    )
    return CredentialProviderChain(providers)
